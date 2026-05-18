"""Admin endpoints: dashboard statistics and indexing job control.

Every route here requires an authenticated admin user. The indexing
controls are thin wrappers around the process-wide ``job_manager``.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import require_admin
from app.api.serializers import job_to_out
from app.database import get_session
from app.repositories.album import AlbumRepository
from app.repositories.media import MediaRepository
from app.schemas.admin import (
    CameraStat,
    DashboardOut,
    IndexJobOut,
    IndexStartRequest,
    StorageStats,
)
from app.workers import job_manager

router = APIRouter(prefix="/admin", tags=["admin"])


def _dir_size(path: Path) -> int:
    """Recursively sum file sizes under ``path`` (blocking; run in a thread)."""
    total = 0
    if not path.exists():
        return 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


async def _build_stats(session: AsyncSession) -> StorageStats:
    media_repo = MediaRepository(session)
    album_repo = AlbumRepository(session)

    total = await media_repo.count()
    images = await media_repo.count(media_type="image")
    videos = await media_repo.count(media_type="video")
    albums = await album_repo.count()
    library_bytes = await media_repo.total_size()
    oldest, newest = await media_repo.date_range()

    # Filesystem inspection is blocking - keep the event loop responsive.
    thumb_bytes = await asyncio.to_thread(_dir_size, settings.thumb_dir)
    preview_bytes = await asyncio.to_thread(_dir_size, settings.preview_dir)

    db_bytes = 0
    if settings.database_url.startswith("sqlite"):
        db_file = settings.database_url.split("///")[-1]
        db_path = Path(db_file)
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        if db_path.exists():
            db_bytes = db_path.stat().st_size

    return StorageStats(
        media_total=total,
        image_count=images,
        video_count=videos,
        album_count=albums,
        library_bytes=library_bytes,
        thumbnail_bytes=thumb_bytes + preview_bytes,
        database_bytes=db_bytes,
        data_free_bytes=_free_bytes(settings.data_path),
        media_free_bytes=_free_bytes(settings.media_path),
        oldest=oldest,
        newest=newest,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    _admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DashboardOut:
    """Aggregate everything the admin dashboard needs in one call."""
    stats = await _build_stats(session)
    job = await job_manager.latest_job()
    cameras = await MediaRepository(session).camera_models()
    return DashboardOut(
        stats=stats,
        job=job_to_out(job) if job else None,
        job_running=job_manager.is_running(),
        cameras=[CameraStat(model=c["model"], count=c["count"]) for c in cameras[:25]],
    )


@router.get("/index/status", response_model=IndexJobOut | None)
async def index_status(
    _admin=Depends(require_admin),
) -> IndexJobOut | None:
    """Current (or most recent) indexing job, or null if none has ever run."""
    job = await job_manager.latest_job()
    return job_to_out(job) if job else None


@router.post("/index/start", response_model=IndexJobOut, status_code=status.HTTP_202_ACCEPTED)
async def index_start(
    body: IndexStartRequest,
    _admin=Depends(require_admin),
) -> IndexJobOut:
    """Start a new indexing job over the media root (or a sub-path)."""
    try:
        await job_manager.start(body.root_path)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    job = await job_manager.latest_job()
    if job is None:  # pragma: no cover - defensive
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Job not created")
    return job_to_out(job)


@router.post("/index/pause", status_code=status.HTTP_200_OK)
async def index_pause(_admin=Depends(require_admin)) -> dict:
    """Pause the running indexing job (cooperative; takes effect shortly)."""
    if not job_manager.pause():
        raise HTTPException(status.HTTP_409_CONFLICT, "No indexing job is running")
    return {"status": "pausing"}


@router.post("/index/resume", status_code=status.HTTP_200_OK)
async def index_resume(_admin=Depends(require_admin)) -> dict:
    """Resume a paused indexing job."""
    if not job_manager.resume():
        raise HTTPException(status.HTTP_409_CONFLICT, "No indexing job is running")
    return {"status": "resuming"}


@router.post("/index/cancel", status_code=status.HTTP_200_OK)
async def index_cancel(_admin=Depends(require_admin)) -> dict:
    """Cancel the running indexing job."""
    if not job_manager.cancel():
        raise HTTPException(status.HTTP_409_CONFLICT, "No indexing job is running")
    return {"status": "cancelling"}
