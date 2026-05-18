"""Search endpoint: filename, date range, camera and metadata filters.

All filtering happens in SQLite using indexed columns, and results are
keyset-paginated so memory usage stays flat regardless of library size.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import require_reader
from app.api.serializers import media_to_out
from app.database import get_session
from app.repositories.media import MediaRepository
from app.schemas.media import MediaPage

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=MediaPage)
async def search_media(
    q: str | None = Query(None, description="Free text: filename / path / description"),
    media_type: str | None = Query(None, pattern="^(image|video)$"),
    camera_model: str | None = Query(None, description="Exact camera model match"),
    favorite: bool | None = Query(None),
    date_from: datetime | None = Query(None, description="Taken on/after (ISO 8601)"),
    date_to: datetime | None = Query(None, description="Taken on/before (ISO 8601)"),
    include_archived: bool = Query(False),
    cursor: str | None = Query(None, description="Opaque keyset cursor"),
    limit: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> MediaPage:
    """Filtered, keyset-paginated media search."""
    repo = MediaRepository(session)
    items, next_cursor = await repo.search(
        limit=max(1, min(limit, settings.max_page_size)),
        cursor=cursor,
        q=q.strip() if q else None,
        media_type=media_type,
        camera_model=camera_model,
        favorite=favorite,
        date_from=date_from,
        date_to=date_to,
        include_archived=include_archived,
    )
    return MediaPage(
        items=[media_to_out(m) for m in items],
        next_cursor=next_cursor,
        count=len(items),
    )


@router.get("/cameras", response_model=list[dict])
async def list_cameras(
    _user=Depends(require_reader),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Distinct camera models with counts, for building a filter dropdown."""
    return await MediaRepository(session).camera_models()
