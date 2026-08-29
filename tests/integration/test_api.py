"""API surface: auth, RBAC, projects, ingestion, incidents, error envelope."""

import pytest

pytestmark = pytest.mark.integration


async def test_health_ready_metrics(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    r = await client.get("/ready")
    assert r.status_code == 200 and r.json()["database"] is True
    m = await client.get("/metrics")
    assert b"sentinel_http_requests_total" in m.content


async def test_login_and_me(client, auth):
    r = await client.get("/api/v1/auth/me", headers=auth)
    assert r.status_code == 200 and r.json()["role"] == "ADMIN"


async def test_unauthenticated_is_401_with_envelope(client):
    r = await client.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert "x-request-id" in r.headers


async def test_bad_login_is_audited(client, auth):
    r = await client.post("/api/v1/auth/login", json={"email": "admin@sentinel.local", "password": "wrong-password"})
    assert r.status_code == 401
    audit = await client.get("/api/v1/system/audit", headers=auth)
    assert any(a["action"] == "auth.login" and a["outcome"] == "failure" for a in audit.json())


async def test_rbac_viewer_cannot_inject_faults(client, auth):
    r = await client.post("/api/v1/auth/users", headers=auth, json={"email": "v@x.io", "password": "viewer-pass-1", "role": "VIEWER"})
    assert r.status_code == 201
    tok = (await client.post("/api/v1/auth/login", json={"email": "v@x.io", "password": "viewer-pass-1"})).json()["access_token"]
    vh = {"authorization": f"Bearer {tok}"}
    assert (await client.get("/api/v1/projects", headers=vh)).status_code == 200
    r = await client.post("/api/v1/faults", headers=vh, json={"target": "payment-service", "fault": "cpu_saturation"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_bootstrap_topology_and_rules(client, auth):
    svcs = (await client.get("/api/v1/projects/demo-shop/services", headers=auth)).json()
    assert {s["name"] for s in svcs} >= {"api-gateway", "payment-service", "postgres"}
    topo = (await client.get("/api/v1/projects/demo-shop/topology", headers=auth)).json()
    assert any(e["source"] == "payment-service" and e["target"] == "postgres" for e in topo["edges"])
    rules = (await client.get("/api/v1/projects/demo-shop/rules", headers=auth)).json()
    assert any(r["name"] == "HighErrorRate" for r in rules)


async def test_ingest_requires_scope_and_normalizes(client, ingest_headers, auth):
    r = await client.post("/api/v1/ingest/logs", headers=ingest_headers, json={"project": "demo-shop", "service": "payment-service", "records": [{"message": "failed to acquire database connection after 5012ms", "level": "error"}, {"bad": "row", "timestamp": "not-a-date"}]})
    assert r.status_code == 202
    assert r.json()["accepted"] == 1 and r.json()["rejected"] == 1
    r = await client.post("/api/v1/ingest/metrics", headers=ingest_headers, json={"project": "demo-shop", "records": [{"service.name": "payment-service", "name": "cpu_usage", "value": 33}]})
    assert r.json()["accepted"] == 1
    # a JWT user without the ingest scope would be a user → allowed (users have all scopes); an api key without scope is rejected
    key = (await client.post("/api/v1/auth/api-keys", headers=auth, json={"name": "noscope", "role": "VIEWER", "scopes": []})).json()["key"]
    r = await client.post("/api/v1/ingest/metrics", headers={"x-api-key": key}, json={"project": "demo-shop", "records": []})
    assert r.status_code == 403


async def test_manual_incident_lifecycle_and_transitions(client, auth):
    r = await client.post("/api/v1/incidents", headers=auth, json={"project": "demo-shop", "title": "Manual test incident", "primary_service": "payment-service", "investigate": False})
    assert r.status_code == 202
    inc = r.json()
    assert inc["key"].startswith("INC-") and inc["status"] == "DETECTED"
    allowed = (await client.get(f"/api/v1/incidents/{inc['id']}/transitions", headers=auth)).json()
    assert "INVESTIGATING" in allowed
    r = await client.post(f"/api/v1/incidents/{inc['id']}/transition", headers=auth, json={"status": "POSTMORTEM"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    r = await client.post(f"/api/v1/incidents/{inc['id']}/resolve", headers=auth, json={"notes": "false alarm"})
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED"
    tl = (await client.get(f"/api/v1/incidents/{inc['key']}/timeline", headers=auth)).json()
    assert any("RESOLVED" in e["message"] for e in tl)
    page = (await client.get("/api/v1/incidents?project=demo-shop&limit=1", headers=auth)).json()
    assert page["total"] >= 1 and len(page["items"]) == 1


async def test_deployment_webhook(client, ingest_headers, auth):
    r = await client.post("/api/v1/webhooks/deployments", headers=ingest_headers, json={"project": "demo-shop", "service": "payment-service", "version": "2.8.1", "commit_sha": "a81f2c9d", "commit_message": "increase concurrency", "changed_files": ["payment/db/pool.py"]})
    assert r.status_code == 202
    deps = (await client.get("/api/v1/projects/demo-shop/deployments", headers=auth)).json()
    assert deps[0]["version"] == "2.8.1" and deps[0]["previous_version"] in (None, "2.8.0")
    svcs = (await client.get("/api/v1/projects/demo-shop/services", headers=auth)).json()
    assert next(s for s in svcs if s["name"] == "payment-service")["current_version"] == "2.8.1"


async def test_alertmanager_webhook_opens_incident(client, ingest_headers, auth):
    payload = {"version": "4", "status": "firing", "alerts": [{"status": "firing", "labels": {"alertname": "PaymentErrorRateHigh", "service": "payment-service", "severity": "critical"}, "annotations": {"description": "5xx > 10%", "value": "0.31"}, "startsAt": "2026-08-29T14:13:17Z", "fingerprint": "abc123"}]}
    r = await client.post("/api/v1/webhooks/alerts?project=demo-shop", headers=ingest_headers, json=payload)
    assert r.status_code == 202 and r.json()["fired"] == ["PaymentErrorRateHigh@payment-service"]
    incs = (await client.get("/api/v1/incidents?project=demo-shop&open_only=true", headers=auth)).json()["items"]
    assert any(i["primary_service"] == "payment-service" and i["severity"] == "CRITICAL" for i in incs)
    # duplicate firing is idempotent
    r = await client.post("/api/v1/webhooks/alerts?project=demo-shop", headers=ingest_headers, json=payload)
    assert r.json()["fired"] == []


async def test_overview_and_config(client, auth):
    ov = (await client.get("/api/v1/system/overview?project=demo-shop", headers=auth)).json()
    assert ov["status"] in ("HEALTHY", "DEGRADED") and ov["llm"]["provider"] == "none"
    cfg = (await client.get("/api/v1/system/config", headers=auth)).json()
    assert cfg["queue"] == "inprocess" and cfg["database"] == "sqlite"


async def test_validation_error_envelope(client, auth):
    r = await client.post("/api/v1/projects", headers=auth, json={"slug": "Bad Slug!", "name": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
