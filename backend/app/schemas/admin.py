"""Admin / dashboard schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndexStartRequest(BaseModel):
    root_path: str | None = None  # defaults to MEDIA_ROOT


class IndexJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    root_path: str
    total_files: int
    processed_files: int
    indexed_files: int
    updated_files: int
    skipped_files: int
    failed_files: int
    current_path: str | None = None
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    progress: float = 0.0  # 0..1


class StorageStats(BaseModel):
    media_total: int
    image_count: int
    video_count: int
    album_count: int
    library_bytes: int          # size of originals on the HDD
    thumbnail_bytes: int        # local thumbnail cache size
    database_bytes: int
    data_free_bytes: int        # free space on the app data volume
    media_free_bytes: int       # free space on the HDD
    oldest: datetime | None = None
    newest: datetime | None = None


class CameraStat(BaseModel):
    model: str
    count: int


class DashboardOut(BaseModel):
    stats: StorageStats
    job: IndexJobOut | None = None
    job_running: bool
    cameras: list[CameraStat] = []
