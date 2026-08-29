"""FastAPI dependencies: DB session, authentication (JWT or API key), RBAC."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.core.errors import Forbidden, Unauthorized
from sentinel.core.security import decode_access_token, hash_api_key
from sentinel.core.timeutil import utcnow
from sentinel.db.models import ApiKey, User
from sentinel.db.session import get_session_factory
from sentinel.domain.enums import ROLE_RANK, Role


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(get_db)]


@dataclass
class Principal:
    id: str
    kind: str  # user | api_key
    role: str
    email: str | None = None
    scopes: tuple[str, ...] = ()

    def has_role(self, minimum: Role) -> bool:
        return ROLE_RANK[Role(self.role)] >= ROLE_RANK[minimum]

    def has_scope(self, scope: str) -> bool:
        return self.kind == "user" or scope in self.scopes or "*" in self.scopes


async def _principal_from_request(request: Request, session: AsyncSession, authorization: str | None, x_api_key: str | None) -> Principal | None:
    raw_key = x_api_key
    token = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            # JWTs have exactly two dots; anything else on a Bearer header is an API key
            # (Alertmanager / collectors can only send Bearer credentials).
            if value.startswith("snt_") or value.count(".") != 2:
                raw_key = value
            else:
                token = value
    if raw_key:
        row = (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw_key), ApiKey.revoked.is_(False)))).scalar_one_or_none()
        if row is None:
            raise Unauthorized("invalid API key")
        row.last_used_at = utcnow()
        return Principal(id=row.id, kind="api_key", role=row.role, scopes=tuple(row.scopes or ()))
    if token:
        try:
            payload = decode_access_token(token)
        except jwt.PyJWTError as exc:
            raise Unauthorized("invalid or expired token") from exc
        user = await session.get(User, payload["sub"])
        if user is None or not user.is_active:
            raise Unauthorized("user not found or inactive")
        return Principal(id=user.id, kind="user", role=user.role, email=user.email)
    return None


async def current_principal(
    request: Request,
    session: DB,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Principal:
    p = await _principal_from_request(request, session, authorization, x_api_key)
    if p is None:
        raise Unauthorized("authentication required")
    request.state.principal = p
    return p


async def optional_principal(
    request: Request,
    session: DB,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Principal | None:
    return await _principal_from_request(request, session, authorization, x_api_key)


Auth = Annotated[Principal, Depends(current_principal)]


def require_role(minimum: Role):  # type: ignore[no-untyped-def]
    async def _dep(p: Auth) -> Principal:
        if not p.has_role(minimum):
            raise Forbidden(f"requires role {minimum} (you are {p.role})")
        return p

    return Depends(_dep)


def require_scope(scope: str):  # type: ignore[no-untyped-def]
    async def _dep(p: Auth) -> Principal:
        if not p.has_scope(scope):
            raise Forbidden(f"API key lacks scope '{scope}'")
        return p

    return Depends(_dep)


Viewer = Annotated[Principal, require_role(Role.VIEWER)]
Engineer = Annotated[Principal, require_role(Role.ENGINEER)]
Sre = Annotated[Principal, require_role(Role.SRE)]
Admin = Annotated[Principal, require_role(Role.ADMIN)]
Ingestor = Annotated[Principal, require_scope("ingest")]
