"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAsyncAction, usePoll, useRequireAuth } from "@/lib/hooks";
import { ago, titleCase } from "@/lib/format";
import { Badge, Button, Empty, ErrorNote, Panel, Skeleton, Table } from "@/components/ui";

const TARGETS = ["payment-service", "order-service", "inventory-service", "auth-service", "api-gateway", "frontend", "notification-worker"];

export default function ChaosPage() {
  const s = useRequireAuth();
  const enabled = s.ready && !!s.token;
  const catalog = usePoll(() => api.faultCatalog(), 60000, [], enabled);
  const faults = usePoll(() => api.faults(), 4000, [], enabled);
  const incidents = usePoll(() => api.incidents({ project: "demo-shop", limit: 30 }), 5000, [], enabled);
  const [target, setTarget] = useState("payment-service");
  const [fault, setFault] = useState("db_pool_exhaustion");
  const [duration, setDuration] = useState(180);
  const [severity, setSeverity] = useState("high");
  const { busy, error, run } = useAsyncAction();
  const canInject = s.user?.role === "SRE" || s.user?.role === "ADMIN";
  const inject = async () => {
    await run(() => api.injectFault({ target, fault, duration_s: duration, severity }));
    await faults.refresh();
  };
  const linkedIncident = (f: import("@/lib/types").Fault) => {
    if (!incidents.data) return null;
    const start = f.started_at ? new Date(f.started_at).getTime() : 0;
    return incidents.data.items.find((i) => new Date(i.detected_at).getTime() >= start - 5000 && i.affected_services.includes(f.target_service)) ?? null;
  };
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">Chaos Lab</h1>
        <p className="text-xs text-fg-muted">Inject controlled failures into the demo shop, then watch Sentinel detect, investigate and explain them. Every injection is audited.</p>
      </header>
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Inject a fault" className="lg:col-span-1">
          <div className="space-y-3 text-xs">
            <label className="block text-fg-muted">Target service
              <select value={target} onChange={(e) => setTarget(e.target.value)} className="mt-1 w-full rounded-md border border-border bg-bg px-2 py-2 text-sm text-fg">
                {TARGETS.map((t) => <option key={t}>{t}</option>)}
              </select>
            </label>
            <label className="block text-fg-muted">Fault
              <select value={fault} onChange={(e) => setFault(e.target.value)} className="mt-1 w-full rounded-md border border-border bg-bg px-2 py-2 text-sm text-fg">
                {Object.keys(catalog.data ?? { db_pool_exhaustion: 1 }).map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              {catalog.data?.[fault] && <p className="mt-1 text-fg-dim">{catalog.data[fault].description}. Expected root cause: <span className="text-fg">{titleCase(catalog.data[fault].expected)}</span></p>}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-fg-muted">Duration (s)
                <input type="number" min={5} max={3600} value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="mt-1 w-full rounded-md border border-border bg-bg px-2 py-2 text-sm text-fg mono" />
              </label>
              <label className="block text-fg-muted">Severity
                <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="mt-1 w-full rounded-md border border-border bg-bg px-2 py-2 text-sm text-fg">
                  {["low", "medium", "high", "critical"].map((x) => <option key={x}>{x}</option>)}
                </select>
              </label>
            </div>
            {error && <ErrorNote>{error}</ErrorNote>}
            {!canInject && <p className="text-warn">Your role ({s.user?.role}) cannot inject faults — SRE or ADMIN required.</p>}
            <div className="flex gap-2">
              <Button variant="danger" onClick={inject} disabled={busy || !canInject} className="flex-1 justify-center py-2">{busy ? "Injecting…" : "⚡ Inject failure"}</Button>
              <Button onClick={async () => { await run(() => api.clearFaults()); await faults.refresh(); }} disabled={busy || !canInject}>Clear all</Button>
            </div>
            <p className="text-fg-dim">Then open <Link href="/" className="text-accent">Overview</Link> and watch the blast radius; the incident opens once the error ratio is sustained above 10% for 30s.</p>
          </div>
        </Panel>
        <Panel title="Experiments" className="lg:col-span-2" padded={false}>
          {!faults.data ? (
            <div className="p-4"><Skeleton className="h-24" /></div>
          ) : faults.data.length === 0 ? (
            <div className="p-4"><Empty>No experiments yet.</Empty></div>
          ) : (
            <Table>
              <thead><tr><th>Fault</th><th>Target</th><th>Severity</th><th>Status</th><th>Expected root cause</th><th>Incident</th><th>Started</th><th></th></tr></thead>
              <tbody>
                {faults.data.map((f) => {
                  const inc = linkedIncident(f);
                  return (
                    <tr key={f.id}>
                      <td className="mono text-xs">{f.fault_type}</td>
                      <td className="text-sm">{f.target_service}</td>
                      <td><Badge tone={f.severity === "critical" || f.severity === "high" ? "crit" : "warn"}>{f.severity}</Badge></td>
                      <td><Badge tone={f.status === "active" ? "crit" : f.status === "cleared" ? "ok" : f.status === "failed" ? "warn" : "muted"} dot>{f.status}</Badge></td>
                      <td className="text-xs">{titleCase(f.expected_root_cause)}</td>
                      <td className="text-xs">
                        {inc ? (
                          <Link href={`/incidents/${inc.id}`} className="text-accent hover:underline">
                            {inc.key} {inc.root_cause_category ? <span className={inc.root_cause_category === f.expected_root_cause ? "text-ok" : "text-warn"}>· {inc.root_cause_category === f.expected_root_cause ? "✓ matched" : "✗ " + titleCase(inc.root_cause_category)}</span> : <span className="text-fg-muted">· {inc.status.toLowerCase()}</span>}
                          </Link>
                        ) : f.status === "active" ? <span className="text-fg-muted">waiting for detection…</span> : <span className="text-fg-dim">—</span>}
                      </td>
                      <td className="text-xs text-fg-muted">{ago(f.started_at)}</td>
                      <td>{f.status === "active" && canInject && <Button variant="ghost" onClick={async () => { await run(() => api.clearFault(f.id)); await faults.refresh(); }}>clear</Button>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </div>
  );
}
