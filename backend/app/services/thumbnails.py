"""Thumbnail and preview generation.

Two derivatives are produced per item:
  * thumbnail  - small grid image (THUMB_SIZE, default 320px)
  * preview    - medium image for the viewer (PREVIEW_SIZE, default 1280px)

Memory notes for the Raspberry Pi:
  * JPEG draft mode decodes large photos at 1/2..1/8 resolution, slashing
    peak RAM before the image is ever fully loaded.
  * The preview is generated first and the thumbnail derived from it, so a
    source photo is decoded only once.
  * Files are sharded into sub-directories (1000 per dir) to keep ext4
    directory lookups fast on the external HDD's app volume.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import settings

try:
    from PIL import Image, ImageOps

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:  # pragma: no cover
        pass
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


def _shard(base: Path, media_id: int) -> Path:
    sub = base / f"{media_id // 1000:04d}"
    sub.mkdir(parents=True, exist_ok=True)
    return sub / f"{media_id}.jpg"


def thumb_path(media_id: int) -> Path:
    return _shard(settings.thumb_dir, media_id)


def preview_path(media_id: int) -> Path:
    return _shard(settings.preview_dir, media_id)


def thumbnails_exist(media_id: int) -> bool:
    return thumb_path(media_id).exists() and preview_path(media_id).exists()


def _save_jpeg(img: "Image.Image", dest: Path) -> None:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=settings.thumb_quality, optimize=True)


def generate_image_thumbs(src: str | Path, media_id: int) -> bool:
    """Generate preview + thumbnail for an image. Returns True on success."""
    if Image is None:
        return False
    try:
        with Image.open(src) as img:
            # draft() lets the JPEG decoder skip resolution we won't use.
            img.draft("RGB", (settings.preview_size, settings.preview_size))
            img = ImageOps.exif_transpose(img)  # honour rotation
            img = img.convert("RGB")

            preview = img.copy()
            preview.thumbnail(
                (settings.preview_size, settings.preview_size), Image.LANCZOS
            )
            _save_jpeg(preview, preview_path(media_id))

            thumb = preview.copy()
            thumb.thumbnail((settings.thumb_size, settings.thumb_size), Image.LANCZOS)
            _save_jpeg(thumb, thumb_path(media_id))
        return True
    except Exception:  # noqa: BLE001
        return False


def generate_video_thumbs(src: str | Path, media_id: int) -> bool:
    """Extract a representative frame from a video and build thumbs from it."""
    if Image is None or not settings.enable_video_thumbs:
        return False
    tmp = settings.cache_dir / f"_vframe_{media_id}.jpg"
    try:
        ok = False
        for seek in ("00:00:01", "00:00:00"):
            proc = subprocess.run(
                ["ffmpeg", "-y", "-ss", seek, "-i", str(src),
                 "-frames:v", "1", "-q:v", "3", "-vf",
                 f"scale={settings.preview_size}:-2:force_original_aspect_ratio="
                 "decrease", str(tmp)],
                capture_output=True, timeout=60,
            )
            if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                ok = True
                break
        if not ok:
            return False
        return generate_image_thumbs(tmp, media_id)
    except (subprocess.SubprocessError, OSError):
        return False
    finally:
        tmp.unlink(missing_ok=True)


def generate_thumbnails(src: str | Path, media_id: int, media_type: str) -> bool:
    """Dispatch to the image or video generator based on media type."""
    if media_type == "video":
        return generate_video_thumbs(src, media_id)
    return generate_image_thumbs(src, media_id)


def delete_thumbnails(media_id: int) -> None:
    """Remove generated derivatives for a media item."""
    for p in (thumb_path(media_id), preview_path(media_id)):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
