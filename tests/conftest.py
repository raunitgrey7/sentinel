"""Shared fixtures.

Unit tests need nothing. Integration tests get an isolated SQLite database, an in-process
queue and the deterministic ``NullProvider`` so they run anywhere in seconds.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

SCRATCH = Path(os.environ.get("SENTINEL_TEST_DIR", Path(__file__).parent / ".tmp"))
SCRATCH.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    db = SCRATCH / f"test-{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("SENTINEL_DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("SENTINEL_ENV", "test")
    monkeypatch.setenv("SENTINEL_LLM_PROVIDER", "none")
    monkeypatch.setenv("SENTINEL_DETECTOR_ENABLED", "false")
    monkeypatch.setenv("SENTINEL_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("SENTINEL_BOOTSTRAP_INGEST_KEY", "test-ingest-key")
    monkeypatch.delenv("SENTINEL_REDIS_URL", raising=False)
    from sentinel.core.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    from sentinel.db import session as dbs
    from sentinel.llm import set_provider
    from sentinel.queue import set_queue

    dbs.reset_for_tests(s)
    set_provider(None)
    set_queue(None)
    yield s
    get_settings.cache_clear()
    set_provider(None)
    set_queue(None)


@pytest.fixture
async def db(settings_env) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    from sentinel.db.session import dispose, init_schema

    await init_schema()
    yield
    await dispose()


@pytest.fixture
async def client(db):  # type: ignore[no-untyped-def]
    from httpx import ASGITransport, AsyncClient

    from sentinel.api.app import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.fixture
async def admin_token(client) -> str:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/auth/login", json={"email": "admin@sentinel.local", "password": "admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def auth(admin_token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {admin_token}"}


@pytest.fixture
def ingest_headers() -> dict[str, str]:
    return {"x-api-key": "test-ingest-key"}
