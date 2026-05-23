"""Filesystem management for the media root.

Allows admins to list, upload, move and delete files directly on the
external HDD. All paths are strictly validated to stay within MEDIA_ROOT.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.config import settings


class StorageService:
    def __init__(self, root: Path = settings.media_path) -> None:
        self.root = root.resolve()

    def _safe_path(self, rel_path: str) -> Path:
        """Resolve a relative path and ensure it stays under root."""
        # Strip leading slashes to ensure it's treated as relative to root.
        rel_path = rel_path.lstrip("/")
        target = (self.root / rel_path).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError("Path traversal detected")
        return target

    def list_dir(self, rel_path: str = "") -> list[dict[str, Any]]:
        target = self._safe_path(rel_path)
        if not target.is_dir():
            raise ValueError("Not a directory")

        items = []
        with os.scandir(target) as it:
            for entry in it:
                st = entry.stat()
                items.append({
                    "name": entry.name,
                    "path": str(Path(entry.path).relative_to(self.root)),
                    "is_dir": entry.is_dir(),
                    "size": st.st_size if entry.is_file() else None,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                })
        # Folders first, then alphabetical.
        return sorted(items, key=lambda x: (not x["is_dir"], x["name"].lower()))

    async def save_upload(self, rel_path: str, file: UploadFile) -> str:
        target_dir = self._safe_path(rel_path)
        if not target_dir.is_dir():
            target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / file.filename
        # Avoid overwriting existing files by appending a suffix if needed.
        if target_file.exists():
            stem = target_file.stem
            ext = target_file.suffix
            counter = 1
            while (target_dir / f"{stem}_{counter}{ext}").exists():
                counter += 1
            target_file = target_dir / f"{stem}_{counter}{ext}"

        # Write in chunks to keep memory flat.
        with target_file.open("wb") as f:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                f.write(content)

        return str(target_file.relative_to(self.root))

    def delete(self, rel_path: str) -> None:
        target = self._safe_path(rel_path)
        if target == self.root:
            raise ValueError("Cannot delete the media root")
        
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def move(self, old_rel_path: str, new_rel_path: str) -> str:
        source = self._safe_path(old_rel_path)
        dest = self._safe_path(new_rel_path)
        
        if dest.exists():
            raise ValueError("Destination already exists")
        
        # Ensure parent of destination exists.
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.move(source, dest)
        return str(dest.relative_to(self.root))

    def mkdir(self, rel_path: str) -> str:
        target = self._safe_path(rel_path)
        target.mkdir(parents=True, exist_ok=True)
        return str(target.relative_to(self.root))

    def extract(self, rel_path: str) -> str:
        """Extract a zip or tar archive into its parent directory."""
        source = self._safe_path(rel_path)
        if not source.is_file():
            raise ValueError("Not a file")

        target_dir = source.parent
        
        if source.suffix.lower() == ".zip":
            import zipfile
            with zipfile.ZipFile(source, "r") as zip_ref:
                zip_ref.extractall(target_dir)
        elif source.suffix.lower() in (".tar", ".gz", ".tgz"):
            import tarfile
            with tarfile.open(source, "r:*") as tar_ref:
                tar_ref.extractall(target_dir)
        else:
            raise ValueError("Unsupported archive format")
            
        return str(target_dir.relative_to(self.root))
