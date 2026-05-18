"""Indexing jobs - tracks the progress of a Takeout scan."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Status values used by the indexer state machine.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


class IndexJob(Base):
    __tablename__ = "index_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="index")
    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING, index=True)
    root_path: Mapped[str] = mapped_column(String(1024))

    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    indexed_files: Mapped[int] = mapped_column(Integer, default=0)
    updated_files: Mapped[int] = mapped_column(Integer, default=0)
    skipped_files: Mapped[int] = mapped_column(Integer, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, default=0)

    current_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IndexJob id={self.id} status={self.status}>"
