"""Storage management schemas."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class StorageItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    mtime: datetime | None = None


class StorageList(BaseModel):
    items: list[StorageItem]
    current_path: str
    parent_path: str | None


class MoveRequest(BaseModel):
    old_path: str
    new_path: str


class MkdirRequest(BaseModel):
    path: str
