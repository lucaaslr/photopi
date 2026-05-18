"""Album endpoints: CRUD, membership management and guest sharing.

Albums come from two sources:
  * ``manual``  - created by a user in the UI.
  * ``takeout`` - reconstructed automatically from Takeout folder names.

Shared albums can be browsed without authentication via an opaque token
when ALLOW_GUEST is enabled.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import require_admin, require_reader
from app.api.serializers import album_to_out, media_to_out
from app.database import get_session
from app.repositories.album import AlbumRepository
from app.repositories.media import MediaRepository
from app.schemas.album import (
    AlbumCreate,
    AlbumDetail,
    AlbumItemAction,
    AlbumOut,
    AlbumUpdate,
)

router = APIRouter(prefix="/albums", tags=["albums"])


def _clamp(limit: int) -> int:
    return max(1, min(limit, settings.max_page_size))


@router.get("", response_model=list[AlbumOut])
async def list_albums(
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> list[AlbumOut]:
    """List every album with its item count."""
    rows = await AlbumRepository(session).list_all()
    return [album_to_out(album, count) for album, count in rows]


@router.post("", response_model=AlbumOut, status_code=status.HTTP_201_CREATED)
async def create_album(
    body: AlbumCreate,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AlbumOut:
    """Create a new manual album."""
    repo = AlbumRepository(session)
    album = await repo.create(name=body.name, description=body.description)
    await session.commit()
    return album_to_out(album, 0)


@router.get("/{album_id}", response_model=AlbumDetail)
async def get_album(
    album_id: int,
    cursor: str | None = Query(None),
    limit: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> AlbumDetail:
    """Album metadata plus a keyset-paginated page of its media."""
    album_repo = AlbumRepository(session)
    album = await album_repo.get(album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")

    media_repo = MediaRepository(session)
    items, next_cursor = await media_repo.list_by_album(
        album_id, limit=_clamp(limit), cursor=cursor
    )
    count = await album_repo.item_count(album_id)
    base = album_to_out(album, count)
    return AlbumDetail(
        **base.model_dump(),
        items=[media_to_out(m) for m in items],
        next_cursor=next_cursor,
    )


@router.patch("/{album_id}", response_model=AlbumOut)
async def update_album(
    album_id: int,
    body: AlbumUpdate,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AlbumOut:
    """Edit album name, description, cover image or sharing flag."""
    repo = AlbumRepository(session)
    album = await repo.get(album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")

    if body.name is not None:
        album.name = body.name
    if body.description is not None:
        album.description = body.description
    if body.cover_media_id is not None:
        album.cover_media_id = body.cover_media_id
    if body.is_shared is not None:
        album.is_shared = body.is_shared
        # Mint a token the first time an album is shared; keep it afterwards.
        if body.is_shared and not album.share_token:
            album.share_token = secrets.token_urlsafe(16)

    await session.commit()
    count = await repo.item_count(album_id)
    return album_to_out(album, count)


@router.delete(
    "/{album_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_album(
    album_id: int,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an album. Media items themselves are not affected."""
    repo = AlbumRepository(session)
    album = await repo.get(album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")
    await repo.delete(album)
    await session.commit()


@router.post("/{album_id}/items", response_model=AlbumOut)
async def add_items(
    album_id: int,
    body: AlbumItemAction,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AlbumOut:
    """Add one or more media items to an album (idempotent per item)."""
    album_repo = AlbumRepository(session)
    album = await album_repo.get(album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")

    media_repo = MediaRepository(session)
    found = await media_repo.get_many(body.media_ids)
    found_ids = {m.id for m in found}
    missing = set(body.media_ids) - found_ids
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown media ids: {sorted(missing)}",
        )

    for media_id in body.media_ids:
        await album_repo.add_item(album_id, media_id)
    # Auto-assign a cover from the first added item if none is set yet.
    if album.cover_media_id is None and body.media_ids:
        album.cover_media_id = body.media_ids[0]

    await session.commit()
    count = await album_repo.item_count(album_id)
    return album_to_out(album, count)


@router.delete("/{album_id}/items", response_model=AlbumOut)
async def remove_items(
    album_id: int,
    body: AlbumItemAction,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AlbumOut:
    """Remove one or more media items from an album."""
    repo = AlbumRepository(session)
    album = await repo.get(album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")

    for media_id in body.media_ids:
        await repo.remove_item(album_id, media_id)
    await session.commit()
    count = await repo.item_count(album_id)
    return album_to_out(album, count)


# --- Guest sharing --------------------------------------------------------
@router.get("/shared/{token}", response_model=AlbumDetail)
async def get_shared_album(
    token: str,
    cursor: str | None = Query(None),
    limit: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    session: AsyncSession = Depends(get_session),
) -> AlbumDetail:
    """Public, unauthenticated view of a shared album via its token."""
    album_repo = AlbumRepository(session)
    album = await album_repo.get_by_share_token(token)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shared album not found")

    media_repo = MediaRepository(session)
    items, next_cursor = await media_repo.list_by_album(
        album.id, limit=_clamp(limit), cursor=cursor
    )
    count = await album_repo.item_count(album.id)
    base = album_to_out(album, count)
    return AlbumDetail(
        **base.model_dump(),
        items=[media_to_out(m) for m in items],
        next_cursor=next_cursor,
    )
