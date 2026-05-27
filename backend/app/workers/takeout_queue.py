"""Takeout import queue.

Runs the takeout_import service in the background, persisting progress in
the existing ``IndexJob`` table (with ``kind='takeout'``). At most one
takeout job runs at a time; when one finishes, an index scan is queued so
newly extracted files become visible in PhotoPi.
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
from app.services import takeout_import as ti
from app.workers.queue import job_manager as index_job_manager

logger = logging.getLogger("photopi.takeout.queue")


class TakeoutJobManager:
    """Singleton coordinator for the takeout-import worker."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._job_id: int | None = None

    async def recover_stale_jobs(self) -> None:
        """On startup, mark interrupted takeout jobs as failed."""
        async with SessionLocal() as session:
            await session.execute(
                update(IndexJob)
                .where(IndexJob.kind == "takeout")
                .where(IndexJob.status.in_(
                    [job_model.STATUS_RUNNING, job_model.STATUS_PAUSED]
                ))
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

    async def start(
        self,
        archives: list[Path],
        dest_root: Path,
        *,
        delete_on_success: bool = True,
        trigger_index: bool = True,
    ) -> int:
        if self.is_running():
            raise RuntimeError("A takeout import job is already running.")
        if index_job_manager.is_running():
            raise RuntimeError(
                "An indexing job is already running. Wait for it to finish."
            )
        if not archives:
            raise ValueError("No archives selected for import.")

        async with SessionLocal() as session:
            job = IndexJob(
                kind="takeout",
                root_path=str(dest_root),
                status=job_model.STATUS_PENDING,
                total_files=len(archives),
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        self._job_id = job_id
        self._task = asyncio.create_task(
            self._run(job_id, archives, dest_root, delete_on_success, trigger_index)
        )
        logger.info(
            "Started takeout job %s with %d archive(s) -> %s",
            job_id, len(archives), dest_root,
        )
        return job_id

    async def _set_status(self, job_id: int, status: str, **fields) -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(IndexJob).where(IndexJob.id == job_id).values(
                    status=status, **fields
                )
            )
            await session.commit()

    async def _update_progress(
        self,
        job_id: int,
        *,
        processed: int | None = None,
        current_path: str | None = None,
        message: str | None = None,
        indexed: int | None = None,
        skipped: int | None = None,
        failed: int | None = None,
    ) -> None:
        values: dict = {}
        if processed is not None:
            values["processed_files"] = processed
        if current_path is not None:
            values["current_path"] = current_path
        if message is not None:
            values["message"] = message
        if indexed is not None:
            values["indexed_files"] = indexed
        if skipped is not None:
            values["skipped_files"] = skipped
        if failed is not None:
            values["failed_files"] = failed
        if not values:
            return
        async with SessionLocal() as session:
            await session.execute(
                update(IndexJob).where(IndexJob.id == job_id).values(**values)
            )
            await session.commit()

    async def _run(
        self,
        job_id: int,
        archives: list[Path],
        dest_root: Path,
        delete_on_success: bool,
        trigger_index: bool,
    ) -> None:
        try:
            await self._set_status(
                job_id, job_model.STATUS_RUNNING,
                message=f"Importing {len(archives)} archive(s)",
            )

            total_files = 0
            total_skipped = 0
            total_failed = 0
            processed_archives = 0
            loop = asyncio.get_running_loop()

            def on_start(i: int, total: int, name: str) -> None:
                # called from event loop (import_archives is async-aware)
                asyncio.ensure_future(
                    self._update_progress(
                        job_id,
                        current_path=name,
                        message=f"Extracting {i}/{total}: {name}",
                    )
                )

            results = []
            for i, archive in enumerate(archives, start=1):
                await self._update_progress(
                    job_id,
                    current_path=archive.name,
                    message=f"Extracting {i}/{len(archives)}: {archive.name}",
                )
                result = (await ti.import_archives(
                    [archive],
                    dest_root,
                    delete_on_success=delete_on_success,
                ))[0]
                results.append(result)
                processed_archives = i
                total_files += result.files_written
                total_skipped += result.files_skipped
                if result.status == "error":
                    total_failed += 1
                await self._update_progress(
                    job_id,
                    processed=processed_archives,
                    indexed=total_files,
                    skipped=total_skipped,
                    failed=total_failed,
                )

            error_count = sum(1 for r in results if r.status == "error")
            summary = (
                f"Imported {total_files} file(s) from {len(archives)} archive(s); "
                f"{error_count} archive(s) failed"
            )
            await self._set_status(
                job_id,
                job_model.STATUS_FAILED if error_count == len(archives)
                else job_model.STATUS_COMPLETED,
                message=summary,
                finished_at=datetime.now(timezone.utc),
                current_path=None,
            )

            if trigger_index and not index_job_manager.is_running():
                try:
                    await index_job_manager.start(str(dest_root))
                    logger.info("Triggered index job after takeout import %s", job_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not trigger index after takeout: %s", exc)

        except asyncio.CancelledError:  # pragma: no cover
            await self._set_status(
                job_id, job_model.STATUS_CANCELLED,
                message="Cancelled",
                finished_at=datetime.now(timezone.utc),
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Takeout job %s crashed", job_id)
            await self._set_status(
                job_id, job_model.STATUS_FAILED,
                message=f"Crashed: {exc}",
                finished_at=datetime.now(timezone.utc),
            )
        finally:
            self._task = None
            self._job_id = None
            logger.info("Takeout job %s finished", job_id)

    async def latest_job(self) -> IndexJob | None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(IndexJob)
                .where(IndexJob.kind == "takeout")
                .order_by(IndexJob.id.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()


takeout_job_manager = TakeoutJobManager()
