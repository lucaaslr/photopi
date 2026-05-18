"""A deliberately tiny job queue.

PhotoPi runs at most ONE indexing job at a time. That is by design: a
Raspberry Pi 3B+ cannot afford competing CPU/IO workloads, and a single
sequential worker keeps memory usage flat and predictable.

The manager owns the background asyncio task plus two control events
(pause / cancel) that the Indexer polls cooperatively.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

from app.config import settings
from app.database import SessionLocal
from app.models import job as job_model
from app.models.job import IndexJob
from app.services.indexer import Indexer

logger = logging.getLogger("photopi.jobs")


class JobManager:
    """Singleton coordinator for the one-at-a-time indexer."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._job_id: int | None = None
        self._pause = asyncio.Event()   # set -> indexer pauses
        self._cancel = asyncio.Event()  # set -> indexer stops

    # --- Lifecycle --------------------------------------------------------
    async def recover_stale_jobs(self) -> None:
        """On startup, fail any job left RUNNING/PAUSED by a crash/restart."""
        async with SessionLocal() as session:
            await session.execute(
                update(IndexJob)
                .where(
                    IndexJob.status.in_(
                        [job_model.STATUS_RUNNING, job_model.STATUS_PAUSED]
                    )
                )
                .values(
                    status=job_model.STATUS_FAILED,
                    message="Interrupted by a restart.",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def current_job_id(self) -> int | None:
        return self._job_id

    # --- Controls ---------------------------------------------------------
    async def start(self, root: str | None = None) -> int:
        """Start a new indexing job. Raises RuntimeError if one is active."""
        if self.is_running():
            raise RuntimeError("An indexing job is already running.")

        root_path = Path(root or settings.media_root)
        if not root_path.is_dir():
            raise FileNotFoundError(f"Media path not found: {root_path}")

        async with SessionLocal() as session:
            job = IndexJob(root_path=str(root_path), status=job_model.STATUS_PENDING)
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        self._job_id = job_id
        self._pause.clear()
        self._cancel.clear()
        self._task = asyncio.create_task(self._run(job_id, root_path))
        logger.info("Started indexing job %s on %s", job_id, root_path)
        return job_id

    def pause(self) -> bool:
        if not self.is_running():
            return False
        self._pause.set()
        return True

    def resume(self) -> bool:
        if not self.is_running():
            return False
        self._pause.clear()
        return True

    def cancel(self) -> bool:
        if not self.is_running():
            return False
        self._cancel.set()
        self._pause.clear()  # release a paused loop so it can observe cancel
        return True

    # --- Internal ---------------------------------------------------------
    async def _run(self, job_id: int, root: Path) -> None:
        try:
            indexer = Indexer(job_id, root, self._pause, self._cancel)
            await indexer.run()
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Indexing job %s crashed", job_id)
        finally:
            self._task = None
            self._job_id = None
            logger.info("Indexing job %s finished", job_id)

    async def latest_job(self) -> IndexJob | None:
        """Return the most recent job row (running or historical)."""
        async with SessionLocal() as session:
            result = await session.execute(
                select(IndexJob).order_by(IndexJob.id.desc()).limit(1)
            )
            return result.scalar_one_or_none()


# Process-wide singleton.
job_manager = JobManager()
