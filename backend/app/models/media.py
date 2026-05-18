"""Media items (photos and videos) discovered on the external HDD."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Filesystem location ---------------------------------------------
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    rel_path: Mapped[str] = mapped_column(String(1024))
    filename: Mapped[str] = mapped_column(String(512), index=True)
    ext: Mapped[str] = mapped_column(String(16))
    mtime: Mapped[float] = mapped_column(Float, default=0.0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # --- Classification ---------------------------------------------------
    media_type: Mapped[str] = mapped_column(String(16), index=True)  # image|video
    mime_type: Mapped[str] = mapped_column(String(64), default="")

    # --- Dimensions / duration -------------------------------------------
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Capture metadata -------------------------------------------------
    taken_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=_utcnow)
    taken_source: Mapped[str] = mapped_column(String(16), default="mtime")
    camera_make: Mapped[str | None] = mapped_column(String(128), nullable=True)
    camera_model: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Flags ------------------------------------------------------------
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # --- Deduplication ----------------------------------------------------
    # Fast content hash (size + sampled bytes) for exact-ish dedup.
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # Perceptual hash (dHash) for near-duplicate detection of images.
    phash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    duplicate_of: Mapped[int | None] = mapped_column(
        ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )

    # --- Thumbnails / import ---------------------------------------------
    thumb_status: Mapped[str] = mapped_column(String(16), default="pending")
    takeout_json: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    album_items: Mapped[list["AlbumItem"]] = relationship(  # noqa: F821
        back_populates="media", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_media_timeline", "archived", "taken_at", "id"),
        Index("ix_media_type_taken", "media_type", "taken_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Media id={self.id} {self.filename!r}>"
