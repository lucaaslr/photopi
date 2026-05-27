"""Takeout import schemas."""
from __future__ import annotations

from pydantic import BaseModel


class StagedArchive(BaseModel):
    name: str
    size: int
    mtime: str


class StagedList(BaseModel):
    items: list[StagedArchive]
    staging_dir: str


class TakeoutImportRequest(BaseModel):
    # Archive filenames (basename only) to import. If empty, import every
    # archive currently in the staging dir.
    archives: list[str] = []
    delete_on_success: bool = True
    trigger_index: bool = True


class TakeoutUploadResult(BaseModel):
    uploaded: list[str]
    errors: list[dict] = []
