"""Media request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MediaOut(BaseModel):
    """Compact representation used in gallery / timeline listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    media_type: str
    taken_at: datetime
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    favorite: bool = False
    archived: bool = False
    thumb_status: str = "pending"
    is_duplicate: bool = False
    thumb_url: str = ""
    preview_url: str = ""
    file_url: str = ""


class MediaDetail(MediaOut):
    """Full representation used by the media viewer / metadata panel."""

    rel_path: str
    size_bytes: int
    mime_type: str
    taken_source: str
    camera_make: str | None = None
    camera_model: str | None = None
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    description: str | None = None
    content_hash: str | None = None
    phash: str | None = None
    duplicate_of: int | None = None
    indexed_at: datetime
    maps_url: str | None = None


class MediaUpdate(BaseModel):
    """Editable fields on a media item."""

    favorite: bool | None = None
    archived: bool | None = None
    description: str | None = Field(default=None, max_length=2000)


class MediaPage(BaseModel):
    """A keyset-paginated page of media items."""

    items: list[MediaOut]
    next_cursor: str | None = None
    count: int


class TimelineBucket(BaseModel):
    year: str
    month: str
    count: int
