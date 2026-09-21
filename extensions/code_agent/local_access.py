"""Explicit local shared-workspace identity; JWT mode remains the default."""
import os
import secrets

from fastapi import HTTPException, Request


def auth_mode() -> str:
    mode = os.environ.get("CODE_AUTH_MODE", "jwt").strip().lower()
    if mode not in {"local", "jwt"}:
        raise RuntimeError("CODE_AUTH_MODE must be local or jwt")
    return mode


async def local_user(db):
    from sqlalchemy import select
    from app.config import get_settings
    from app.models.database import User
    result = await db.execute(select(User).where(User.username == get_settings().admin_username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.role != "admin":
        raise HTTPException(status_code=503, detail="공유 작업실 계정이 준비되지 않았습니다.")
    return user


async def ensure_local_user(db):
    from sqlalchemy import select
    from app.config import get_settings
    from app.models.database import User
    from app.services.auth import hash_password
    username = get_settings().admin_username
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(username=username, name="공유 작업실", role="admin", is_active=True,
                    hashed_password=hash_password(secrets.token_urlsafe(32)))
        db.add(user)
        await db.commit()
    return await local_user(db)


async def auth_route_guard(request: Request):
    if auth_mode() == "local" and not (
        request.method == "GET" and request.url.path.rstrip("/").endswith(("/auth/me", "/auth/mode"))
    ):
        raise HTTPException(status_code=404, detail="로컬 작업실에서는 계정 로그인을 사용하지 않습니다.")
