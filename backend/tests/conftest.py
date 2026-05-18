"""Pytest fixtures for the PhotoPi backend.

Environment variables are set *before* the application is imported so the
settings singleton and the database engine bind to an isolated, temporary
SQLite database. Each test gets a fresh schema.
"""
from __future__ import annotations

import os
import tempfile

# --- Isolate the test environment (must run before importing `app`) -------
_TMPDIR = tempfile.mkdtemp(prefix="photopi-test-")
os.environ.setdefault("DATA_DIR", _TMPDIR)
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMPDIR}/test.db")
os.environ.setdefault("MEDIA_ROOT", _TMPDIR)
os.environ.setdefault("JWT_SECRET", "pytest-secret-not-for-production")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adminpass")
os.environ.setdefault("ALLOW_GUEST", "false")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402
from app import models  # noqa: F401,E402  - register ORM models


@pytest_asyncio.fixture()
async def db():
    """Create a fresh schema for each test, dropping it afterwards."""
    settings.ensure_dirs()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # Seed the bootstrap admin account.
    async with SessionLocal() as session:
        repo = UserRepository(session)
        await repo.create(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            is_admin=True,
        )
        await session.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client(db):
    """An HTTPX client wired directly to the ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture()
async def admin_headers(client: AsyncClient):
    """Authorization headers for the bootstrap admin user."""
    resp = await client.post(
        "/api/auth/login",
        json={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
