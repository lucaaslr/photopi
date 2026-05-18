"""Helpers that convert ORM models into Pydantic response schemas.

Keeping URL construction in one place means the routes stay thin.
"""
from __future__ import annotations

from app.models.album import Album
from app.models.job import IndexJob
from app.models.media import Media
from app.schemas.admin import IndexJobOut
from app.schemas.album import AlbumOut
from app.schemas.media import MediaDetail, MediaOut

API_PREFIX = "/api"


def media_urls(media_id: int) -> dict[str, str]:
    base = f"{API_PREFIX}/media/{media_id}"
    return {
        "thumb_url": f"{base}/thumb",
        "preview_url": f"{base}/preview",
        "file_url": f"{base}/file",
    }


def media_to_out(media: Media) -> MediaOut:
    return MediaOut(
        id=media.id,
        filename=media.filename,
        media_type=media.media_type,
        taken_at=media.taken_at,
        width=media.width,
        height=media.height,
        duration=media.duration,
        favorite=media.favorite,
        archived=media.archived,
        thumb_status=media.thumb_status,
        is_duplicate=media.duplicate_of is not None,
        **media_urls(media.id),
    )


def media_to_detail(media: Media) -> MediaDetail:
    maps_url = None
    if media.lat is not None and media.lon is not None:
        maps_url = (
            f"https://www.openstreetmap.org/?mlat={media.lat}"
            f"&mlon={media.lon}#map=15/{media.lat}/{media.lon}"
        )
    return MediaDetail(
        id=media.id,
        filename=media.filename,
        media_type=media.media_type,
        taken_at=media.taken_at,
        width=media.width,
        height=media.height,
        duration=media.duration,
        favorite=media.favorite,
        archived=media.archived,
        thumb_status=media.thumb_status,
        is_duplicate=media.duplicate_of is not None,
        rel_path=media.rel_path,
        size_bytes=media.size_bytes,
        mime_type=media.mime_type,
        taken_source=media.taken_source,
        camera_make=media.camera_make,
        camera_model=media.camera_model,
        lat=media.lat,
        lon=media.lon,
        altitude=media.altitude,
        description=media.description,
        content_hash=media.content_hash,
        phash=media.phash,
        duplicate_of=media.duplicate_of,
        indexed_at=media.indexed_at,
        maps_url=maps_url,
        **media_urls(media.id),
    )


def album_to_out(album: Album, item_count: int = 0) -> AlbumOut:
    cover_url = (
        f"{API_PREFIX}/media/{album.cover_media_id}/thumb"
        if album.cover_media_id
        else None
    )
    return AlbumOut(
        id=album.id,
        name=album.name,
        slug=album.slug,
        description=album.description,
        source=album.source,
        cover_media_id=album.cover_media_id,
        is_shared=album.is_shared,
        share_token=album.share_token,
        created_at=album.created_at,
        item_count=item_count,
        cover_url=cover_url,
    )


def job_to_out(job: IndexJob) -> IndexJobOut:
    progress = 0.0
    if job.total_files > 0:
        progress = min(1.0, job.processed_files / job.total_files)
    return IndexJobOut(
        id=job.id,
        status=job.status,
        root_path=job.root_path,
        total_files=job.total_files,
        processed_files=job.processed_files,
        indexed_files=job.indexed_files,
        updated_files=job.updated_files,
        skipped_files=job.skipped_files,
        failed_files=job.failed_files,
        current_path=job.current_path,
        message=job.message,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        progress=round(progress, 4),
    )
