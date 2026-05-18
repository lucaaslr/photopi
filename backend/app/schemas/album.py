"""Album request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.media import MediaOut


class AlbumCreate(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=2000)


class AlbumUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=2000)
    cover_media_id: int | None = None
    is_shared: bool | None = None


class AlbumOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None = None
    source: str
    cover_media_id: int | None = None
    is_shared: bool = False
    share_token: str | None = None
    created_at: datetime
    item_count: int = 0
    cover_url: str | None = None


class AlbumDetail(AlbumOut):
    items: list[MediaOut] = []
    next_cursor: str | None = None


class AlbumItemAction(BaseModel):
    media_ids: list[int] = Field(min_length=1, max_length=500)
