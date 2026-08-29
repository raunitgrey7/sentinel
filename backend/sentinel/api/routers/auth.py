from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from sentinel.api.deps import DB, Admin, Auth
from sentinel.api.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
)
from sentinel.core.errors import Conflict, NotFound, Unauthorized
from sentinel.core.security import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from sentinel.db.models import ApiKey, User
from sentinel.domain.enums import Role
from sentinel.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: DB, request: Request) -> TokenResponse:
    user = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        await audit.record(session, action="auth.login", resource_type="user", resource_id=None, actor_id=body.email, outcome="failure", ip=request.client.host if request.client else None)
        await session.commit()  # keep the audit row even though the request fails
        raise Unauthorized("invalid credentials")
    token = create_access_token(user.id, user.role)
    await audit.record(session, action="auth.login", resource_type="user", resource_id=user.id, actor_id=user.id, ip=request.client.host if request.client else None)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id, email=user.email)


@router.get("/me", response_model=UserOut)
async def me(p: Auth, session: DB) -> User:
    if p.kind != "user":
        raise NotFound("API keys have no user profile")
    user = await session.get(User, p.id)
    assert user is not None
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(_: Admin, session: DB) -> list[User]:
    return list((await session.execute(select(User).order_by(User.created_at))).scalars().all())


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, p: Admin, session: DB) -> User:
    Role(body.role)
    existing = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if existing:
        raise Conflict("email already registered")
    user = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password), role=body.role)
    session.add(user)
    await session.flush()
    await audit.record(session, action="user.create", resource_type="user", resource_id=user.id, actor_id=p.id, detail={"role": body.role})
    return user


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(_: Admin, session: DB) -> list[ApiKey]:
    return list((await session.execute(select(ApiKey).order_by(ApiKey.created_at))).scalars().all())


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(body: ApiKeyCreate, p: Admin, session: DB) -> ApiKeyCreated:
    Role(body.role)
    raw = generate_api_key()
    row = ApiKey(name=body.name, key_hash=hash_api_key(raw), prefix=raw[:10], role=body.role, scopes=body.scopes, created_by=p.id)
    session.add(row)
    await session.flush()
    await audit.record(session, action="api_key.create", resource_type="api_key", resource_id=row.id, actor_id=p.id, detail={"scopes": body.scopes, "role": body.role})
    return ApiKeyCreated(id=row.id, name=row.name, prefix=row.prefix, role=row.role, scopes=row.scopes, created_at=row.created_at, last_used_at=None, revoked=False, key=raw)


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, p: Admin, session: DB) -> None:
    row = await session.get(ApiKey, key_id)
    if row is None:
        raise NotFound("api key not found")
    row.revoked = True
    await audit.record(session, action="api_key.revoke", resource_type="api_key", resource_id=key_id, actor_id=p.id)
