"""Albums and the album <-> media association."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    slug: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "manual" = created in the UI, "takeout" = reconstructed from an export.
    source: Mapped[str] = mapped_column(String(16), default="manual")
    cover_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    share_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    items: Mapped[list["AlbumItem"]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
        order_by="AlbumItem.position",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Album id={self.id} {self.name!r}>"


class AlbumItem(Base):
    __tablename__ = "album_items"
    __table_args__ = (
        UniqueConstraint("album_id", "media_id", name="uq_album_media"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_id: Mapped[int] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"), index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    album: Mapped["Album"] = relationship(back_populates="items")
    media: Mapped["Media"] = relationship(back_populates="album_items")  # noqa: F821
