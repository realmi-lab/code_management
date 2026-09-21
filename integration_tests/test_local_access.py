"""Patched upstream dependency with synthetic DB/auth doubles; not live JWT/PG evidence."""
import asyncio
import importlib.util
from pathlib import Path
import shutil
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from code_agent import local_access

ROOT = Path(__file__).resolve().parents[1]


def load_patch():
    spec = importlib.util.spec_from_file_location("local_access_patch", ROOT / "deploy/patch_local_access.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Base(DeclarativeBase):
    pass


class FakeUser(Base):
    __tablename__ = "synthetic_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean)
    name: Mapped[str] = mapped_column(String)
    hashed_password: Mapped[str] = mapped_column(String)


@pytest.fixture
def context(tmp_path, monkeypatch):
    for path in ("app/dependencies.py", "app/main.py", "app/api/auth.py"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "upstream/backend" / path, target)
    load_patch().apply(tmp_path)
    user = FakeUser(id=17, username="shared", role="admin", is_active=True, name="Synthetic", hashed_password="unchanged")

    class DB:
        current = user
        commits = 0
        async def execute(self, query):
            assert query.compile().params.get("username_1") == "shared" or query.compile().params.get("id_1") == 17
            return SimpleNamespace(scalar_one_or_none=lambda: self.current)
        def add(self, value):
            self.current = value
        async def commit(self):
            self.commits += 1
    db = DB()
    async def get_db():
        yield db
    async def not_blacklisted(jti):
        return False
    modules = {
        "app.config": {"get_settings": lambda: SimpleNamespace(admin_username="shared")},
        "app.models.database": {"User": FakeUser, "get_db": get_db},
        "app.services.auth": {"decode_token": lambda token: {"sub": "17", "type": "access"},
                              "is_token_blacklisted": not_blacklisted, "hash_password": lambda value: "hashed:" + value},
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("patched_dependencies", tmp_path / "app/dependencies.py")
    dependency = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dependency)
    return tmp_path, db, dependency


def test_local_original_dependency_and_guard(context, monkeypatch):
    _, db, dependency = context
    monkeypatch.setenv("CODE_AUTH_MODE", "local")
    app = FastAPI()
    @app.get("/api/auth/me", dependencies=[Depends(local_access.auth_route_guard)])
    async def me(user=Depends(dependency.get_current_user)):
        return {"id": user.id, "role": user.role}
    @app.post("/api/auth/login", dependencies=[Depends(local_access.auth_route_guard)])
    async def login():
        raise AssertionError("credential mutation must not execute")
    client = TestClient(app)
    assert client.get("/api/auth/me").json() == {"id": 17, "role": "admin"}
    assert client.post("/api/auth/login").status_code == 404
    db.current.is_active = False
    assert client.get("/api/auth/me").status_code == 503


def test_jwt_original_dependency_still_requires_token(context, monkeypatch):
    _, db, dependency = context
    monkeypatch.setenv("CODE_AUTH_MODE", "jwt")
    with pytest.raises(HTTPException) as error:
        asyncio.run(dependency.get_current_user(credentials=None, db=db))
    assert error.value.status_code == 401
    assert asyncio.run(dependency.get_current_user(credentials=SimpleNamespace(credentials="synthetic"), db=db)).id == 17


def test_bootstrap_reuses_identity_or_creates_without_admin_password(context, monkeypatch):
    _, db, _ = context
    monkeypatch.setenv("CODE_AUTH_MODE", "local")
    assert asyncio.run(local_access.ensure_local_user(db)).id == 17
    assert db.commits == 0
    assert db.current.hashed_password == "unchanged"
    db.current = None
    created = asyncio.run(local_access.ensure_local_user(db))
    assert created.username == "shared" and created.role == "admin" and created.is_active
    assert created.hashed_password.startswith("hashed:")
    assert db.commits == 1


def test_patch_fails_closed_on_repeat(context):
    root, _, _ = context
    before = (root / "app/dependencies.py").read_text()
    with pytest.raises(RuntimeError):
        load_patch().apply(root)
    assert (root / "app/dependencies.py").read_text() == before


def test_mode_rejects_unknown(monkeypatch):
    monkeypatch.setenv("CODE_AUTH_MODE", "unexpected")
    with pytest.raises(RuntimeError):
        local_access.auth_mode()
