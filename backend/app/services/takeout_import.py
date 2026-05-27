"""Backend-integrated Takeout import.

A module version of ``scripts/organize-takeout.py`` callable from the API.
Same semantics: extract Takeout archives into a canonical 'Google Photos/'
tree, idempotent via a JSON manifest, normalising localised "Google Fotos"
folder names. Designed to run on a Pi: blocking work is dispatched to a
thread pool from the async wrapper.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tarfile
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

logger = logging.getLogger("photopi.takeout")

MANIFEST_NAME = ".photopi-organize-manifest.json"
CANONICAL_ROOT = "Google Photos"

JUNK_SEGMENTS = {
    "__macosx",
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "archive_browser.html",
}

ARCHIVE_SUFFIXES = (".zip", ".tgz", ".tar.gz", ".tar")


@dataclass
class ArchiveResult:
    archive: str
    status: str = "ok"  # ok | already_done | error
    files_written: int = 0
    files_skipped: int = 0
    bytes_written: int = 0
    error: str | None = None


@dataclass
class _Member:
    arcname: str
    size: int
    open: Callable[[], object]


def is_archive(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(ARCHIVE_SUFFIXES)


@contextmanager
def _open_archive(path: Path) -> Iterator[list[_Member]]:
    name = path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            members = [
                _Member(zi.filename, zi.file_size, lambda zi=zi: zf.open(zi))
                for zi in zf.infolist()
                if not zi.is_dir()
            ]
            yield members
    else:
        with tarfile.open(path, "r:*") as tf:
            members: list[_Member] = []
            for ti in tf.getmembers():
                if not ti.isfile():
                    continue
                members.append(
                    _Member(ti.name, ti.size, lambda ti=ti: tf.extractfile(ti))
                )
            yield members


def _classify_archive(members: list[_Member]) -> str:
    for m in members:
        first = PurePosixPath(m.arcname).parts[:1]
        if first and first[0].lower() == "takeout":
            return "takeout"
    return "other"


def _normalised_parts(arcname: str) -> tuple[str, ...] | None:
    """Map a Takeout member's archive path to dest path components.

    Returns ``None`` for members that should be skipped (junk, traversal,
    or non-Takeout-rooted entries).
    """
    raw = PurePosixPath(arcname)
    parts = [seg for seg in raw.parts if seg not in ("", "/", ".")]
    if not parts:
        return None
    if any(seg == ".." for seg in parts):
        return None
    if any(seg.lower() in JUNK_SEGMENTS for seg in parts):
        return None
    if parts[0].lower() != "takeout":
        return None
    parts = parts[1:]
    if not parts:
        return None
    if len(parts) == 1:
        # loose file directly under Takeout/ - keep it out of the way
        return (CANONICAL_ROOT, parts[0])
    # parts[0] is the (possibly localised) photos folder name; canonicalise.
    return (CANONICAL_ROOT, *parts[1:])


def _unique_path(target: Path) -> Path:
    stem, suf = target.stem, target.suffix
    n = 1
    while True:
        cand = target.with_name(f"{stem}({n}){suf}")
        if not cand.exists():
            return cand
        n += 1


def load_manifest(dest_root: Path) -> dict:
    p = dest_root / MANIFEST_NAME
    if not p.is_file():
        return {"version": 1, "processed": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("processed", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "processed": {}}


def save_manifest(dest_root: Path, manifest: dict) -> None:
    try:
        (dest_root / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("could not write manifest: %s", exc)


def _archive_signature(path: Path) -> dict:
    st = path.stat()
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


def _extract_one(archive: Path, dest_root: Path) -> ArchiveResult:
    """Synchronously extract one archive into dest_root/Google Photos/."""
    result = ArchiveResult(archive=archive.name)
    try:
        with _open_archive(archive) as members:
            if _classify_archive(members) != "takeout":
                result.status = "error"
                result.error = "not a Takeout archive (no 'Takeout/' root)"
                return result

            total_uncompressed = sum(m.size for m in members)
            try:
                free = shutil.disk_usage(dest_root).free
            except OSError:
                free = None
            if free is not None and total_uncompressed > free:
                result.status = "error"
                result.error = (
                    f"insufficient disk space "
                    f"(need {total_uncompressed} bytes, have {free})"
                )
                return result

            for m in members:
                rel = _normalised_parts(m.arcname)
                if rel is None:
                    result.files_skipped += 1
                    continue
                target = dest_root.joinpath(*rel)
                if target.exists():
                    if target.stat().st_size == m.size:
                        result.files_skipped += 1
                        continue
                    target = _unique_path(target)
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp = target.with_name(target.name + ".partial")
                    src = m.open()
                    if src is None:
                        result.files_skipped += 1
                        continue
                    with src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst, length=1 << 20)
                    os.replace(tmp, target)
                except OSError as exc:
                    logger.warning("extract failed %s: %s", m.arcname, exc)
                    result.files_skipped += 1
                    continue
                result.files_written += 1
                result.bytes_written += m.size
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def list_staged(staging_dir: Path) -> list[dict]:
    """Return metadata for archives currently in the staging folder."""
    if not staging_dir.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(staging_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or not is_archive(entry):
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        out.append(
            {
                "name": entry.name,
                "size": st.st_size,
                "mtime": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
            }
        )
    return out


async def import_archives(
    archives: list[Path],
    dest_root: Path,
    *,
    delete_on_success: bool = False,
    on_archive_start: Callable[[int, int, str], None] | None = None,
    on_archive_done: Callable[[ArchiveResult], None] | None = None,
) -> list[ArchiveResult]:
    """Process each archive in series. Returns one ArchiveResult per input.

    Heavy work runs in a thread; callbacks fire on the event loop.
    """
    dest_root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(dest_root)
    processed = manifest["processed"]

    results: list[ArchiveResult] = []
    for i, archive in enumerate(archives):
        if on_archive_start:
            on_archive_start(i + 1, len(archives), archive.name)

        if not archive.exists():
            r = ArchiveResult(archive=archive.name, status="error", error="missing")
            results.append(r)
            if on_archive_done:
                on_archive_done(r)
            continue

        sig = _archive_signature(archive)
        prev = processed.get(archive.name)
        if prev and prev.get("size") == sig["size"]:
            r = ArchiveResult(archive=archive.name, status="already_done")
            if delete_on_success:
                try:
                    archive.unlink()
                except OSError as exc:
                    logger.warning("could not delete %s: %s", archive, exc)
            results.append(r)
            if on_archive_done:
                on_archive_done(r)
            continue

        result = await asyncio.to_thread(_extract_one, archive, dest_root)
        if result.status == "ok":
            processed[archive.name] = {
                **sig,
                "files": result.files_written,
                "at": datetime.now().isoformat(timespec="seconds"),
            }
            save_manifest(dest_root, manifest)
            if delete_on_success:
                try:
                    archive.unlink()
                except OSError as exc:
                    logger.warning("could not delete %s: %s", archive, exc)

        results.append(result)
        if on_archive_done:
            on_archive_done(result)

    return results
