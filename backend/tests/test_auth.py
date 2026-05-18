"""Tests for authentication endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["is_admin"] is True


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, admin_headers: dict):
    resp = await client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "adminpass", "new_password": "newpass123"},
    )
    assert resp.status_code == 204

    # Old password should now fail, new one should work.
    bad = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass"},
    )
    assert bad.status_code == 401
    good = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "newpass123"},
    )
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_admin_route_rejects_anonymous(client: AsyncClient):
    resp = await client.get("/api/admin/dashboard")
    assert resp.status_code == 401
