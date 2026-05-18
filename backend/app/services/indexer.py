"""The indexing pipeline.

Turns a directory of (extracted) Google Photos Takeout files into rows in the
database. Built around four Raspberry-Pi-friendly principles:

  1. Chunked filesystem scan - one directory at a time, never a giant list.
  2. Batched DB writes      - one transaction per INDEX_BATCH_SIZE files.
  3. Sequential processing  - a single (configurable) worker thread does the
                              CPU-bound image work; the event loop stays free.
  4. Incremental & resumable - a file already indexed with the same size and
                              mtime is skipped, so re-running is cheap and a
                              cancelled job simply continues where it stopped.
"""
from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import job as job_model
from app.models.media import Media
from app.repositories.album import AlbumRepository
from app.repositories.media import MediaRepository
from app.services import metadata as meta_svc
from app.services import takeout as takeout_svc
from app.services import thumbnails as thumb_svc
from app.services.phash import content_hash, dhash

# One small pool: image decoding is the only thing we parallelise, and on a
# Pi 3B+ "parallel" usually means a single worker (see THUMB_WORKERS).
_executor = ThreadPoolExecutor(max_workers=max(1, settings.thumb_workers))


@dataclass
class FileProbe:
    """Result of the CPU-bound first pass over a file."""

    meta: meta_svc.MediaMeta
    chash: str


def _is_hidden(name: str) -> bool:
    return name.startswith(".") or name.startswith("_vframe_")


def count_media_files(root: Path) -> int:
    """Cheap pre-pass: count indexable files (readdir only, no stat())."""
    total = 0
    for _dir, _dirs, files in os.walk(root):
        for name in files:
            if _is_hidden(name):
                continue
            if meta_svc.classify(os.path.splitext(name)[1]) is not None:
                total += 1
    return total


def iter_directories(root: Path):
    """Yield (directory, media_filenames, json_filenames) chunk by chunk."""
    for dirpath, _dirs, files in os.walk(root):
        media_files: list[str] = []
        json_files: set[str] = set()
        for name in files:
            if _is_hidden(name):
                continue
            lower = name.lower()
            if lower.endswith(".json"):
                json_files.add(name)
            elif meta_svc.classify(os.path.splitext(name)[1]) is not None:
                media_files.append(name)
        if media_files:
            yield Path(dirpath), sorted(media_files), json_files


def _probe_file(path: str, media_type: str, size: int) -> FileProbe:
    """CPU-bound: metadata + content hash. Runs in the worker thread."""
    meta = meta_svc.extract_metadata(path, media_type)
    chash = content_hash(path, size)
    return FileProbe(meta=meta, chash=chash)


def _build_derivatives(path: str, media_id: int, media_type: str) -> tuple[bool, str | None]:
    """CPU-bound: thumbnails + perceptual hash. Runs in the worker thread."""
    ok = thumb_svc.generate_thumbnails(path, media_id, media_type)
    ph = None
    if ok and media_type == "image":
        ph = dhash(thumb_svc.preview_path(media_id))
    return ok, ph


class Indexer:
    """Runs a single indexing job. One instance per job."""

    def __init__(
        self,
        job_id: int,
        root: Path,
        pause_event: asyncio.Event,
        cancel_event: asyncio.Event,
    ) -> None:
        self.job_id = job_id
        self.root = root
        self.pause_event = pause_event  # set -> paused
        self.cancel_event = cancel_event
        self._loop = asyncio.get_event_loop()

    async def run(self) -> None:
        """Execute the full pipeline. Updates the IndexJob row throughout."""
        await self._set_status(
            job_model.STATUS_RUNNING, started_at=datetime.now(timezone.utc)
        )

        # --- Phase 1: count (for the progress bar) ------------------------
        try:
            total = await asyncio.to_thread(count_media_files, self.root)
        except OSError as exc:
            await self._fail(f"Cannot read media root: {exc}")
            return
        await self._patch(total_files=total, message="Scanning library...")

        # --- Phase 2: walk + process -------------------------------------
        counters = dict(processed=0, indexed=0, updated=0, skipped=0, failed=0)
        batch_pending = 0

        async with SessionLocal() as session:
            media_repo = MediaRepository(session)
            album_repo = AlbumRepository(session)

            try:
                for directory, media_files, json_files in iter_directories(self.root):
                    album_id = await self._resolve_album(album_repo, directory)

                    for name in media_files:
                        if self.cancel_event.is_set():
                            await session.commit()
                            await self._set_status(job_model.STATUS_CANCELLED)
                            return
                        await self._wait_if_paused()

                        outcome = await self._process_file(
                            media_repo, album_repo, directory, name,
                            json_files, album_id,
                        )
                        counters["processed"] += 1
                        counters[outcome] = counters.get(outcome, 0) + 1
                        batch_pending += 1

                        if batch_pending >= settings.index_batch_size:
                            await session.commit()
                            await self._patch(
                                processed_files=counters["processed"],
                                indexed_files=counters["indexed"],
                                updated_files=counters["updated"],
                                skipped_files=counters["skipped"],
                                failed_files=counters["failed"],
                                current_path=str(directory),
                            )
                            batch_pending = 0

                        if settings.index_throttle_ms > 0:
                            await asyncio.sleep(settings.index_throttle_ms / 1000.0)

                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                await self._fail(f"Indexing error: {exc}")
                return

        await self._patch(
            processed_files=counters["processed"],
            indexed_files=counters["indexed"],
            updated_files=counters["updated"],
            skipped_files=counters["skipped"],
            failed_files=counters["failed"],
        )
        await self._set_status(
            job_model.STATUS_COMPLETED,
            finished_at=datetime.now(timezone.utc),
            message=(
                f"Done. {counters['indexed']} new, {counters['updated']} updated, "
                f"{counters['skipped']} unchanged, {counters['failed']} failed."
            ),
        )

    # --- Per-file processing ---------------------------------------------
    async def _process_file(
        self,
        media_repo: MediaRepository,
        album_repo: AlbumRepository,
        directory: Path,
        name: str,
        json_files: set[str],
        album_id: int | None,
    ) -> str:
        """Index one file. Returns 'indexed' | 'updated' | 'skipped' | 'failed'."""
        full = directory / name
        try:
            st = full.stat()
        except OSError:
            return "failed"

        media_type = meta_svc.classify(full.suffix) or "image"
        existing = await media_repo.get_by_path(str(full))

        # Incremental skip: same size + mtime -> nothing to do.
        if (
            existing is not None
            and existing.size_bytes == st.st_size
            and abs(existing.mtime - st.st_mtime) < 1.0
        ):
            if existing.thumb_status != "done" or not thumb_svc.thumbnails_exist(
                existing.id
            ):
                ok, ph = await self._loop.run_in_executor(
                    _executor, _build_derivatives, str(full), existing.id, media_type
                )
                existing.thumb_status = "done" if ok else "failed"
                if ph:
                    existing.phash = ph
            if album_id is not None:
                await album_repo.add_item(album_id, existing.id)
            return "skipped"

        # --- CPU-bound probe (worker thread) ------------------------------
        try:
            probe: FileProbe = await self._loop.run_in_executor(
                _executor, _probe_file, str(full), media_type, st.st_size
            )
        except Exception:  # noqa: BLE001
            return "failed"

        # --- Sidecar JSON metadata ---------------------------------------
        sidecar_name = takeout_svc.find_sidecar(name, json_files)
        takeout = (
            takeout_svc.parse_sidecar(directory / sidecar_name)
            if sidecar_name
            else takeout_svc.TakeoutMeta()
        )

        # --- Capture time priority: Takeout > EXIF > file mtime ----------
        if takeout.taken_at:
            taken_at, taken_source = takeout.taken_at, "takeout"
        elif probe.meta.taken_at:
            taken_at, taken_source = probe.meta.taken_at, "exif"
        else:
            taken_at = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(
                tzinfo=None
            )
            taken_source = "mtime"

        is_update = existing is not None
        media = existing or Media(path=str(full))

        media.rel_path = str(full.relative_to(self.root)) \
            if str(full).startswith(str(self.root)) else name
        media.filename = name
        media.ext = full.suffix.lower()
        media.mtime = st.st_mtime
        media.size_bytes = st.st_size
        media.media_type = media_type
        media.mime_type = probe.meta.mime_type
        media.width = probe.meta.width
        media.height = probe.meta.height
        media.duration = probe.meta.duration
        media.taken_at = taken_at
        media.taken_source = taken_source
        media.camera_make = probe.meta.camera_make
        media.camera_model = probe.meta.camera_model
        media.lat = takeout.lat if takeout.lat is not None else probe.meta.lat
        media.lon = takeout.lon if takeout.lon is not None else probe.meta.lon
        media.altitude = (
            takeout.altitude if takeout.altitude is not None else probe.meta.altitude
        )
        media.description = takeout.description
        media.favorite = media.favorite or takeout.favorite
        media.content_hash = probe.chash
        media.takeout_json = takeout.json_path
        media.indexed_at = datetime.now(timezone.utc)
        media.thumb_status = "pending"

        if not is_update:
            media_repo.add(media)

        # --- Duplicate detection -----------------------------------------
        dup = await media_repo.find_content_duplicate(probe.chash, str(full))
        media.duplicate_of = dup.id if dup else None

        # Need the primary key before naming thumbnail files.
        await media_repo.flush()

        # --- Derivatives (worker thread) ---------------------------------
        ok, ph = await self._loop.run_in_executor(
            _executor, _build_derivatives, str(full), media.id, media_type
        )
        media.thumb_status = "done" if ok else "failed"
        if ph:
            media.phash = ph

        # --- Album reconstruction ----------------------------------------
        if album_id is not None:
            await album_repo.add_item(album_id, media.id)

        return "updated" if is_update else ("indexed" if ok else "failed")

    async def _resolve_album(
        self, album_repo: AlbumRepository, directory: Path
    ) -> int | None:
        """Return the album id for a Takeout album folder, creating it once."""
        name = takeout_svc.album_name_for(directory)
        if not name:
            return None
        album = await album_repo.get_or_create_takeout(name)
        return album.id

    # --- Job-row helpers --------------------------------------------------
    async def _wait_if_paused(self) -> None:
        if not self.pause_event.is_set():
            return
        await self._set_status(job_model.STATUS_PAUSED)
        while self.pause_event.is_set() and not self.cancel_event.is_set():
            await asyncio.sleep(0.5)
        if not self.cancel_event.is_set():
            await self._set_status(job_model.STATUS_RUNNING)

    async def _patch(self, **fields) -> None:
        async with SessionLocal() as session:
            job = await session.get(job_model.IndexJob, self.job_id)
            if job:
                for key, value in fields.items():
                    setattr(job, key, value)
                await session.commit()

    async def _set_status(self, status: str, **fields) -> None:
        await self._patch(status=status, **fields)

    async def _fail(self, message: str) -> None:
        await self._set_status(
            job_model.STATUS_FAILED,
            message=message,
            finished_at=datetime.now(timezone.utc),
        )
