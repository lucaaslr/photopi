"""Tests for media browsing, search and album endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.database import SessionLocal
from app.models.media import Media


async def _seed_media(count: int = 5) -> list[int]:
    """Insert `count` fake media rows and return their ids (newest last)."""
    ids: list[int] = []
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    async with SessionLocal() as session:
        for i in range(count):
            media = Media(
                path=f"/mnt/google-photos/photo_{i}.jpg",
                rel_path=f"photo_{i}.jpg",
                filename=f"photo_{i}.jpg",
                ext=".jpg",
                mtime=1700000000.0 + i,
                size_bytes=1024 * (i + 1),
                media_type="image",
                mime_type="image/jpeg",
                width=1920,
                height=1080,
                taken_at=base + timedelta(days=i),
                taken_source="exif",
                camera_make="Canon" if i % 2 == 0 else "Nikon",
                camera_model="EOS 80D" if i % 2 == 0 else "D750",
                thumb_status="done",
            )
            session.add(media)
        await session.commit()
        from sqlalchemy import select

        rows = await session.execute(select(Media.id).order_by(Media.id))
        ids = [r[0] for r in rows.all()]
    return ids


@pytest.mark.asyncio
async def test_timeline_empty(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/media", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_timeline_lists_media(client: AsyncClient, admin_headers: dict):
    await _seed_media(5)
    resp = await client.get("/api/media", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 5
    # Newest first.
    takens = [item["taken_at"] for item in body["items"]]
    assert takens == sorted(takens, reverse=True)


@pytest.mark.asyncio
async def test_timeline_pagination(client: AsyncClient, admin_headers: dict):
    await _seed_media(5)
    page1 = await client.get("/api/media?limit=2", headers=admin_headers)
    assert page1.status_code == 200
    b1 = page1.json()
    assert b1["count"] == 2
    assert b1["next_cursor"] is not None

    page2 = await client.get(
        f"/api/media?limit=2&cursor={b1['next_cursor']}", headers=admin_headers
    )
    b2 = page2.json()
    assert b2["count"] == 2
    # No overlap between pages.
    ids1 = {i["id"] for i in b1["items"]}
    ids2 = {i["id"] for i in b2["items"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_media_detail(client: AsyncClient, admin_headers: dict):
    ids = await _seed_media(3)
    resp = await client.get(f"/api/media/{ids[0]}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ids[0]
    assert body["mime_type"] == "image/jpeg"
    assert "thumb_url" in body


@pytest.mark.asyncio
async def test_media_detail_404(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/media/999999", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_media_favorite(client: AsyncClient, admin_headers: dict):
    ids = await _seed_media(2)
    resp = await client.patch(
        f"/api/media/{ids[0]}",
        headers=admin_headers,
        json={"favorite": True, "description": "A nice photo"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["favorite"] is True
    assert body["description"] == "A nice photo"


@pytest.mark.asyncio
async def test_search_by_filename(client: AsyncClient, admin_headers: dict):
    await _seed_media(5)
    resp = await client.get("/api/search?q=photo_2", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert "photo_2" in body["items"][0]["filename"]


@pytest.mark.asyncio
async def test_search_by_camera(client: AsyncClient, admin_headers: dict):
    await _seed_media(6)
    resp = await client.get(
        "/api/search?camera_model=D750", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3  # odd indices -> Nikon D750


@pytest.mark.asyncio
async def test_album_lifecycle(client: AsyncClient, admin_headers: dict):
    ids = await _seed_media(4)

    # Create.
    created = await client.post(
        "/api/albums",
        headers=admin_headers,
        json={"name": "Holiday 2024", "description": "Trip photos"},
    )
    assert created.status_code == 201
    album = created.json()
    album_id = album["id"]
    assert album["slug"] == "holiday-2024"

    # Add items.
    add = await client.post(
        f"/api/albums/{album_id}/items",
        headers=admin_headers,
        json={"media_ids": ids[:3]},
    )
    assert add.status_code == 200
    assert add.json()["item_count"] == 3

    # Detail lists members.
    detail = await client.get(f"/api/albums/{album_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert len(detail.json()["items"]) == 3

    # Remove one.
    remove = await client.request(
        "DELETE",
        f"/api/albums/{album_id}/items",
        headers=admin_headers,
        json={"media_ids": [ids[0]]},
    )
    assert remove.status_code == 200
    assert remove.json()["item_count"] == 2

    # Delete album.
    deleted = await client.delete(
        f"/api/albums/{album_id}", headers=admin_headers
    )
    assert deleted.status_code == 204
    gone = await client.get(f"/api/albums/{album_id}", headers=admin_headers)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_album_sharing(client: AsyncClient, admin_headers: dict):
    ids = await _seed_media(2)
    created = await client.post(
        "/api/albums", headers=admin_headers, json={"name": "Shared"}
    )
    album_id = created.json()["id"]
    await client.post(
        f"/api/albums/{album_id}/items",
        headers=admin_headers,
        json={"media_ids": ids},
    )

    # Enable sharing -> a token is minted.
    shared = await client.patch(
        f"/api/albums/{album_id}",
        headers=admin_headers,
        json={"is_shared": True},
    )
    token = shared.json()["share_token"]
    assert token

    # The shared endpoint is reachable without auth.
    public = await client.get(f"/api/albums/shared/{token}")
    assert public.status_code == 200
    assert len(public.json()["items"]) == 2


@pytest.mark.asyncio
async def test_admin_dashboard(client: AsyncClient, admin_headers: dict):
    await _seed_media(4)
    resp = await client.get("/api/admin/dashboard", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["media_total"] == 4
    assert body["stats"]["image_count"] == 4
    assert body["job_running"] is False
