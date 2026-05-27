"""Media endpoints: timeline browsing, detail, edits and file serving."""
from __future__ import annotations

import mimetypes
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import require_admin, require_reader
from app.database import get_session
from app.api.serializers import media_to_detail, media_to_out
from app.repositories.media import MediaRepository
from app.schemas.media import MediaDetail, MediaPage, MediaUpdate, TimelineBucket
from app.services import thumbnails as thumb_svc
from app.services.metadata import VIDEO_MIME

router = APIRouter(prefix="/media", tags=["media"])

# Long-lived caching for immutable derivatives.
_IMG_CACHE = {"Cache-Control": "public, max-age=2592000, immutable"}


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, settings.max_page_size))


@router.get("", response_model=MediaPage)
async def list_timeline(
    cursor: str | None = Query(None, description="Opaque keyset cursor"),
    limit: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    media_type: str | None = Query(None, pattern="^(image|video)$"),
    include_archived: bool = Query(False),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    sort: str = Query("desc", pattern="^(asc|desc)$"),
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> MediaPage:
    """Reverse-chronological timeline with keyset pagination."""
    repo = MediaRepository(session)
    items, next_cursor = await repo.timeline(
        limit=_clamp_limit(limit),
        cursor=cursor,
        media_type=media_type,
        include_archived=include_archived,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
    )
    return MediaPage(
        items=[media_to_out(m) for m in items],
        next_cursor=next_cursor,
        count=len(items),
    )


@router.get("/timeline/buckets", response_model=list[TimelineBucket])
async def timeline_buckets(
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> list[TimelineBucket]:
    """Per-month counts used to render the timeline scrubber."""
    repo = MediaRepository(session)
    buckets = await repo.timeline_buckets()
    return [TimelineBucket(**b) for b in buckets]


@router.get("/{media_id}", response_model=MediaDetail)
async def get_media(
    media_id: int,
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> MediaDetail:
    media = await MediaRepository(session).get(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    return media_to_detail(media)


@router.patch("/{media_id}", response_model=MediaDetail)
async def update_media(
    media_id: int,
    body: MediaUpdate,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MediaDetail:
    repo = MediaRepository(session)
    media = await repo.get(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    if body.favorite is not None:
        media.favorite = body.favorite
    if body.archived is not None:
        media.archived = body.archived
    if body.description is not None:
        media.description = body.description
    await session.commit()
    return media_to_detail(media)


@router.delete(
    "/{media_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def remove_from_index(
    media_id: int,
    _user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove an item from the index. The original file on the HDD is kept."""
    repo = MediaRepository(session)
    media = await repo.get(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    thumb_svc.delete_thumbnails(media_id)
    await repo.delete(media)
    await session.commit()


# --- File serving ---------------------------------------------------------
@router.get("/{media_id}/thumb")
async def get_thumbnail(
    media_id: int,
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    await _ensure_exists(session, media_id)
    path = thumb_svc.thumb_path(media_id)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thumbnail not generated")
    return FileResponse(path, media_type="image/jpeg", headers=_IMG_CACHE)


@router.get("/{media_id}/preview")
async def get_preview(
    media_id: int,
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    await _ensure_exists(session, media_id)
    path = thumb_svc.preview_path(media_id)
    if not path.exists():
        # Fall back to the thumbnail so the viewer still shows something.
        path = thumb_svc.thumb_path(media_id)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Preview not generated")
    return FileResponse(path, media_type="image/jpeg", headers=_IMG_CACHE)


@router.get("/{media_id}/file")
async def get_original(
    media_id: int,
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Stream the original file from the HDD (supports HTTP Range)."""
    media = await MediaRepository(session).get(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    from pathlib import Path

    path = Path(media.path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Original file missing on disk")
    # Older rows have `video/mp4` baked in for every container; derive from
    # the extension so .mov/.mkv/.avi/etc are served with the correct MIME
    # without requiring a full reindex.
    ext_mime = VIDEO_MIME.get(path.suffix.lower())
    mime = ext_mime or media.mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # FileResponse handles Range requests, enabling video seeking.
    return FileResponse(path, media_type=mime, filename=media.filename)


async def _ensure_exists(session: AsyncSession, media_id: int) -> None:
    if await MediaRepository(session).get(media_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
