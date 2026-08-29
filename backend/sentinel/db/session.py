"""Async engine/session factory and schema bootstrap."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sentinel.core.config import Settings, get_settings
from sentinel.core.logging import get_logger
from sentinel.db.base import Base

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime | date):
        return o.isoformat()
    if isinstance(o, set | frozenset):
        return sorted(o)
    return str(o)


def json_dumps(o: Any) -> str:
    return json.dumps(o, default=_json_default)


def build_engine(settings: Settings | None = None) -> AsyncEngine:
    s = settings or get_settings()
    kwargs: dict = {"echo": s.database_echo, "pool_pre_ping": True, "json_serializer": json_dumps}
    if s.is_sqlite:
        # SQLite: single writer; keep pooling minimal and enable WAL for concurrent readers.
        kwargs["connect_args"] = {"timeout": 30}
    else:
        kwargs.update({"pool_size": s.db_pool_size, "max_overflow": s.db_max_overflow})
    engine = create_async_engine(s.database_url, **kwargs)
    if s.is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    return engine


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _session_factory


@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Unit-of-work: commit on success, rollback on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def init_schema(engine: AsyncEngine | None = None) -> None:
    """Create tables if missing. Used for SQLite/dev/tests; production uses Alembic."""
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("schema ready")


async def ping(engine: AsyncEngine | None = None) -> bool:
    eng = engine or get_engine()
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("database ping failed", error=str(exc))
        return False


async def dispose() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_for_tests(settings: Settings) -> None:
    """Rebuild engine/session factory against a fresh settings object (tests only)."""
    global _engine, _session_factory
    _engine = build_engine(settings)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
