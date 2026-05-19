#!/usr/bin/env python3
"""
organize-takeout.py
===================
Consolidate Google Photos Takeout archives into a single tidy library
folder that PhotoPi (or any photo indexer) can scan.

Google Takeout hands you a pile of ``takeout-*.zip`` / ``.tgz`` files. Each
one contains a ``Takeout/<Google Photos>/...`` tree, and the same photo
often appears across several archives. This script extracts every archive
into ONE merged ``Google Photos/`` directory:

    <dest>/
      Google Photos/
        Photos from 2023/
        Photos from 2024/
        Trip to Italy/
        ...

Design goals / safety
---------------------
* It ONLY touches archive files (.zip/.tgz/.tar.gz/.tar). Folders you
  already extracted by hand, or a folder where you gathered loose photos,
  are left exactly as they are - point your indexer at the HDD and it will
  pick those up too. Nothing you have already organised is reorganised.
* Originals are never deleted. Processed archives can optionally be MOVED
  to a "done" folder so you can see at a glance what is left to do.
* Idempotent and resumable. A manifest records processed archives, and any
  file that already exists at the destination with the same size is
  skipped - so re-running after an interruption is cheap and safe.
* The (possibly localised) "Google Fotos" / "Google 相册" wrapper folder is
  normalised to the literal "Google Photos", so album reconstruction works
  regardless of the language your Takeout export was generated in.
* Standard library only - no `pip install` required.

Usage
-----
    python3 organize-takeout.py --source /mnt/hdd/zips --dest /mnt/hdd
    python3 organize-takeout.py --source /mnt/hdd --dry-run
    python3 organize-takeout.py --source /mnt/hdd --move-done /mnt/hdd/_done

Then point PhotoPi's PHOTOS_DIR (or any indexer's media root) at <dest>.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

MANIFEST_NAME = ".photopi-organize-manifest.json"
CANONICAL_ROOT = "Google Photos"

# Files/folders that are noise inside a Takeout archive - never extracted.
JUNK_SEGMENTS = {
    "__macosx",
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "archive_browser.html",
}


# ---------------------------------------------------------------------------
# Logging - plain text, SSH-friendly, no colour codes.
# ---------------------------------------------------------------------------
class Log:
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet

    def info(self, msg: str) -> None:
        if not self.quiet:
            print(msg, flush=True)

    @staticmethod
    def warn(msg: str) -> None:
        print(f"  ! {msg}", file=sys.stderr, flush=True)

    @staticmethod
    def step(msg: str) -> None:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@dataclass
class Stats:
    archives_found: int = 0
    archives_processed: int = 0
    archives_already_done: int = 0
    archives_skipped: int = 0
    files_written: int = 0
    files_skipped_identical: int = 0
    files_skipped_junk: int = 0
    files_renamed: int = 0
    files_overwritten: int = 0
    bytes_written: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Archive member abstraction (unifies zip and tar handling)
# ---------------------------------------------------------------------------
@dataclass
class Member:
    """One file inside an archive."""

    arcname: str                       # path as stored in the archive
    size: int                          # uncompressed size in bytes
    mtime: float | None                # modification time (epoch) if known
    open: Callable[[], object]         # -> binary file-like object


def _is_archive(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".zip", ".tgz", ".tar.gz", ".tar"))


def _zip_mtime(info: zipfile.ZipInfo) -> float | None:
    """Convert a ZipInfo date_time tuple to an epoch timestamp."""
    try:
        # date_time is (year, month, day, hour, minute, second)
        return time.mktime((*info.date_time, 0, 0, -1))
    except (ValueError, OverflowError):
        return None


@contextmanager
def open_archive(path: Path) -> Iterator[list[Member]]:
    """Yield the list of file members in *path* (zip or tar)."""
    name = path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            members = [
                Member(
                    arcname=zi.filename,
                    size=zi.file_size,
                    mtime=_zip_mtime(zi),
                    # default-arg binds the current zi for the closure
                    open=lambda zi=zi: zf.open(zi),
                )
                for zi in zf.infolist()
                if not zi.is_dir()
            ]
            yield members
    else:
        # tarfile autodetects gzip via the 'r:*' mode.
        with tarfile.open(path, "r:*") as tf:
            members = []
            for ti in tf.getmembers():
                if not ti.isfile():
                    continue
                members.append(
                    Member(
                        arcname=ti.name,
                        size=ti.size,
                        mtime=float(ti.mtime) if ti.mtime else None,
                        open=lambda ti=ti: tf.extractfile(ti),
                    )
                )
            yield members


# ---------------------------------------------------------------------------
# Path normalisation - the core of the "merge into one tree" logic
# ---------------------------------------------------------------------------
def classify_archive(members: list[Member]) -> str:
    """Return 'takeout' if the archive is rooted at a 'Takeout' folder."""
    for m in members:
        first = PurePosixPath(m.arcname).parts[:1]
        if first and first[0].lower() == "takeout":
            return "takeout"
    return "other"


def detected_wrapper_names(members: list[Member]) -> set[str]:
    """Collect the (possibly localised) photos-folder names seen, for logs.

    Only members that are *inside* a subfolder of the photos wrapper count;
    loose files sitting directly under ``Takeout/`` (an html index, junk)
    must not be mistaken for the wrapper.
    """
    names: set[str] = set()
    for m in members:
        parts = PurePosixPath(m.arcname).parts
        # Need Takeout / <wrapper> / <something> / ... for it to be a real
        # wrapper folder rather than a loose file under Takeout/.
        if len(parts) >= 3 and parts[0].lower() == "takeout":
            if parts[1].lower() not in JUNK_SEGMENTS:
                names.add(parts[1])
    return names


def normalized_parts(
    arcname: str, archive_stem: str, loose: bool
) -> tuple[str, ...] | None:
    """Map an archive member path to its destination path components.

    Real Takeout archives look like ``Takeout/<Google Photos>/...``. We drop
    the ``Takeout`` prefix and replace the localised photos-folder name with
    the literal ``Google Photos`` so the tree is uniform and album detection
    works. Returns ``None`` for members that should be skipped.
    """
    raw = PurePosixPath(arcname)
    parts = [seg for seg in raw.parts if seg not in ("", "/", ".")]
    if not parts:
        return None
    # Reject path-traversal and junk outright.
    if any(seg == ".." for seg in parts):
        return None
    if any(seg.lower() in JUNK_SEGMENTS for seg in parts):
        return None

    if parts[0].lower() == "takeout":
        parts = parts[1:]
        if not parts:
            return None
        if len(parts) == 1:
            # A loose file directly under Takeout/ - keep it, out of the way.
            return (CANONICAL_ROOT, parts[0])
        # parts[0] is the localised "Google Photos" wrapper -> canonicalise.
        return (CANONICAL_ROOT, *parts[1:])

    # No 'Takeout' root. Either a pre-modified archive or not a Takeout zip.
    if not loose:
        return None
    # In --loose mode, stash such archives in their own subfolder so their
    # contents cannot collide with the real merged library.
    return (CANONICAL_ROOT, "_imported", archive_stem, *parts)


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------
def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_path(target: Path) -> Path:
    """Return a non-existing path by inserting a Takeout-style (n) suffix."""
    stem, suffix = target.stem, target.suffix
    n = 1
    while True:
        candidate = target.with_name(f"{stem}({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def extract_archive(
    archive: Path,
    dest_root: Path,
    *,
    on_conflict: str,
    verify_hash: bool,
    loose: bool,
    dry_run: bool,
    log: Log,
    stats: Stats,
) -> int:
    """Extract one archive into ``dest_root/Google Photos/...``.

    Returns the number of files written (0 if the archive was skipped).
    """
    archive_stem = archive.stem
    if archive_stem.lower().endswith(".tar"):  # foo.tar.gz -> stem 'foo.tar'
        archive_stem = archive_stem[:-4]

    with open_archive(archive) as members:
        kind = classify_archive(members)
        if kind != "takeout" and not loose:
            log.warn(
                f"{archive.name}: does not look like a Takeout archive "
                f"(no 'Takeout/' root) - skipped. Use --loose to include it."
            )
            stats.archives_skipped += 1
            return 0

        if kind == "takeout":
            wrappers = detected_wrapper_names(members)
            localised = sorted(w for w in wrappers if w != CANONICAL_ROOT)
            if localised:
                log.info(
                    f"    photos folder detected as {localised} "
                    f"-> normalised to '{CANONICAL_ROOT}'"
                )

        # --- Disk space check (uncompressed) ------------------------------
        total_uncompressed = sum(m.size for m in members)
        try:
            free = shutil.disk_usage(dest_root).free
        except OSError:
            free = None
        if free is not None and total_uncompressed > free:
            log.warn(
                f"{archive.name}: needs {human(total_uncompressed)} but only "
                f"{human(free)} is free at the destination - skipped."
            )
            stats.archives_skipped += 1
            stats.errors.append(f"{archive.name}: insufficient disk space")
            return 0

        written = 0
        for m in members:
            rel = normalized_parts(m.arcname, archive_stem, loose)
            if rel is None:
                stats.files_skipped_junk += 1
                continue

            target = dest_root.joinpath(*rel)

            # --- Decide what to do if something is already there ----------
            action = "write"
            if target.exists():
                same_size = target.stat().st_size == m.size
                identical = same_size
                if same_size and verify_hash:
                    # Confirm by content hash (slower, but certain).
                    src = m.open()
                    if src is None:
                        stats.files_skipped_junk += 1
                        continue
                    h = hashlib.sha1()
                    for chunk in iter(lambda: src.read(1 << 20), b""):
                        h.update(chunk)
                    src.close()
                    identical = h.hexdigest() == _sha1(target)

                if identical:
                    stats.files_skipped_identical += 1
                    continue
                # Same name, different content.
                if on_conflict == "skip":
                    stats.files_skipped_identical += 1
                    continue
                if on_conflict == "overwrite":
                    action = "overwrite"
                else:  # rename (default)
                    target = unique_path(target)
                    action = "rename"

            if dry_run:
                written += 1
                stats.bytes_written += m.size
                if action == "rename":
                    stats.files_renamed += 1
                elif action == "overwrite":
                    stats.files_overwritten += 1
                continue

            # --- Write the file -------------------------------------------
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".partial")
                src = m.open()
                if src is None:  # tar can return None for odd members
                    stats.files_skipped_junk += 1
                    continue
                with src, open(tmp, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1 << 20)
                os.replace(tmp, target)
                if m.mtime:
                    os.utime(target, (m.mtime, m.mtime))
            except OSError as exc:
                stats.errors.append(f"{archive.name}:{m.arcname}: {exc}")
                log.warn(f"failed to extract {m.arcname}: {exc}")
                continue

            written += 1
            stats.bytes_written += m.size
            if action == "rename":
                stats.files_renamed += 1
            elif action == "overwrite":
                stats.files_overwritten += 1

        stats.files_written += written
        return written


# ---------------------------------------------------------------------------
# Manifest (records which archives have been processed)
# ---------------------------------------------------------------------------
def load_manifest(dest_root: Path) -> dict:
    path = dest_root / MANIFEST_NAME
    if not path.is_file():
        return {"version": 1, "processed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("processed", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "processed": {}}


def save_manifest(dest_root: Path, manifest: dict) -> None:
    path = dest_root / MANIFEST_NAME
    try:
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except OSError as exc:
        Log.warn(f"could not write manifest: {exc}")


def archive_signature(path: Path) -> dict:
    st = path.stat()
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def human(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} TB"


def find_archives(source: Path, exclude: set[Path]) -> list[Path]:
    """Recursively collect archive files under *source*, skipping *exclude*."""
    found: list[Path] = []
    for root, dirs, files in os.walk(source):
        root_path = Path(root)
        # Do not descend into excluded directories (our own output, etc.).
        dirs[:] = [
            d for d in dirs if (root_path / d).resolve() not in exclude
        ]
        for name in files:
            p = root_path / name
            if _is_archive(p):
                found.append(p)
    return sorted(found)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidate Google Photos Takeout archives into one "
        "merged library folder. Only archive files are touched; anything "
        "you already extracted is left untouched.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.cwd(),
        help="Folder to search (recursively) for Takeout archives. "
        "Default: current directory.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Where to extract. A 'Google Photos/' folder is created here. "
        "Default: same as --source.",
    )
    parser.add_argument(
        "--on-conflict",
        choices=["rename", "skip", "overwrite"],
        default="rename",
        help="What to do when a different file with the same name already "
        "exists. Identical files are always skipped. Default: rename.",
    )
    parser.add_argument(
        "--verify-hash",
        action="store_true",
        help="Compare file contents (SHA-1) instead of just sizes when "
        "deciding whether two same-named files are identical. Slower.",
    )
    parser.add_argument(
        "--move-done",
        type=Path,
        default=None,
        help="After an archive is fully processed, move it into this folder "
        "so you can see what is left. Archives are never deleted.",
    )
    parser.add_argument(
        "--loose",
        action="store_true",
        help="Also process archives that are not rooted at a 'Takeout/' "
        "folder (placed under 'Google Photos/_imported/'). Off by default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing anything.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process archives even if the manifest marks them as done.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print warnings and the final summary.",
    )
    args = parser.parse_args()

    log = Log(quiet=args.quiet)

    source: Path = args.source.expanduser().resolve()
    dest_root: Path = (args.dest or args.source).expanduser().resolve()
    move_done: Path | None = (
        args.move_done.expanduser().resolve() if args.move_done else None
    )

    if not source.is_dir():
        log.warn(f"source folder does not exist: {source}")
        return 2

    if not args.dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)
        if move_done:
            move_done.mkdir(parents=True, exist_ok=True)

    # Never let the scan pick up files inside our own output / done folders.
    exclude = {(dest_root / CANONICAL_ROOT).resolve()}
    if move_done:
        exclude.add(move_done)

    log.step("=== PhotoPi Takeout organiser ===")
    log.info(f"Source:      {source}")
    log.info(f"Destination: {dest_root / CANONICAL_ROOT}")
    if args.dry_run:
        log.step("DRY RUN - nothing will be written.\n")

    archives = find_archives(source, exclude)
    stats = Stats(archives_found=len(archives))

    if not archives:
        log.step("No .zip / .tgz archives found under the source folder.")
        log.step(
            "If your photos are already extracted, you are done - just point "
            "PhotoPi's PHOTOS_DIR at the HDD."
        )
        return 0

    manifest = load_manifest(dest_root)
    processed = manifest["processed"]

    log.step(f"Found {len(archives)} archive(s).\n")

    try:
        for idx, archive in enumerate(archives, start=1):
            sig = archive_signature(archive)
            key = archive.name
            done = processed.get(key)
            if done and not args.force and done.get("size") == sig["size"]:
                log.info(f"[{idx}/{len(archives)}] {archive.name} - already done, skipping")
                stats.archives_already_done += 1
                continue

            log.step(f"[{idx}/{len(archives)}] {archive.name} ({human(sig['size'])})")
            try:
                written = extract_archive(
                    archive,
                    dest_root,
                    on_conflict=args.on_conflict,
                    verify_hash=args.verify_hash,
                    loose=args.loose,
                    dry_run=args.dry_run,
                    log=log,
                    stats=stats,
                )
            except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
                log.warn(f"{archive.name}: could not read archive ({exc}) - skipped")
                stats.archives_skipped += 1
                stats.errors.append(f"{archive.name}: {exc}")
                continue

            if written >= 0 and not args.dry_run:
                # Mark done only when we actually extracted from it.
                if written > 0 or done is None:
                    processed[key] = {
                        **sig,
                        "files": written,
                        "at": datetime.now().isoformat(timespec="seconds"),
                    }
                    save_manifest(dest_root, manifest)

                if move_done and written >= 0:
                    try:
                        target = move_done / archive.name
                        if target.exists():
                            target = unique_path(target)
                        shutil.move(str(archive), str(target))
                        log.info(f"    moved processed archive -> {target}")
                    except OSError as exc:
                        log.warn(f"could not move {archive.name}: {exc}")

            stats.archives_processed += 1
            log.info(f"    extracted {written} file(s)")

    except KeyboardInterrupt:
        log.step("\nInterrupted - progress has been saved; re-run to resume.")
        if not args.dry_run:
            save_manifest(dest_root, manifest)

    # --- Summary -----------------------------------------------------------
    log.step("\n=== Summary ===")
    log.step(f"Archives found:        {stats.archives_found}")
    log.step(f"  processed:           {stats.archives_processed}")
    log.step(f"  already done:        {stats.archives_already_done}")
    log.step(f"  skipped:             {stats.archives_skipped}")
    log.step(f"Files written:         {stats.files_written:,}  ({human(stats.bytes_written)})")
    log.step(f"  skipped (identical): {stats.files_skipped_identical:,}")
    log.step(f"  renamed (conflict):  {stats.files_renamed:,}")
    if stats.files_overwritten:
        log.step(f"  overwritten:         {stats.files_overwritten:,}")
    log.step(f"  skipped (junk):      {stats.files_skipped_junk:,}")

    if stats.errors:
        log.step(f"\n{len(stats.errors)} error(s):")
        for err in stats.errors[:20]:
            log.step(f"  - {err}")
        if len(stats.errors) > 20:
            log.step(f"  ... and {len(stats.errors) - 20} more")

    if not args.dry_run and stats.files_written:
        log.step(
            f"\nDone. Your consolidated library is at:\n  {dest_root / CANONICAL_ROOT}"
        )
        log.step(
            "Point PhotoPi's PHOTOS_DIR (in .env) at:\n  "
            f"{dest_root}\n"
            "Any folders you extracted earlier will also be indexed as long "
            "as they live under that path."
        )

    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
