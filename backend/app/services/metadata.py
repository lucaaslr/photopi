"""Media metadata extraction.

Strategy (cheapest first, to spare the Pi's CPU):
  images : Pillow reads EXIF in-process    -> no subprocess
  videos : ffprobe (single subprocess)
  fallback: exiftool for anything Pillow cannot decode

All functions are synchronous and CPU-bound; the indexer runs them inside
a tiny thread pool so the event loop stays responsive.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import ExifTags, Image, ImageOps  # noqa: F401

    try:  # optional HEIC/HEIF support
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:  # pragma: no cover
        pass
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".heic", ".heif",
}
VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp", ".mpg", ".mpeg",
}

# Container -> MIME. ffprobe doesn't tell us the container MIME directly, and
# Python's `mimetypes` is patchy for video (no .mkv, .m4v often missing), so
# we map explicitly. Note: this reflects the CONTAINER only — codec support
# (e.g. HEVC inside an .mp4) is a separate concern handled by the player.
VIDEO_MIME = {
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".m4v":  "video/x-m4v",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",
    ".webm": "video/webm",
    ".3gp":  "video/3gpp",
    ".mpg":  "video/mpeg",
    ".mpeg": "video/mpeg",
}

# EXIF tag id lookups (resolved once).
_EXIF_TAGS = {
    "DateTimeOriginal": 36867,
    "DateTime": 306,
    "Make": 271,
    "Model": 272,
    "GPSInfo": 34853,
}


@dataclass
class MediaMeta:
    media_type: str = "image"
    mime_type: str = ""
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    taken_at: datetime | None = None
    taken_source: str = "mtime"
    camera_make: str | None = None
    camera_model: str | None = None
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    extras: dict = field(default_factory=dict)


def classify(ext: str) -> str | None:
    """Return 'image', 'video', or None for an extension (with leading dot)."""
    ext = ext.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def _parse_exif_datetime(value: str) -> datetime | None:
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _gps_to_decimal(coord, ref) -> float | None:
    """Convert EXIF GPS (degrees, minutes, seconds) tuple to a float."""
    try:
        d, m, s = (float(x) for x in coord)
        dec = d + m / 60.0 + s / 3600.0
        if ref in ("S", "W"):
            dec = -dec
        return round(dec, 7)
    except (TypeError, ValueError):
        return None


def extract_image_metadata(path: str | Path) -> MediaMeta:
    """Read dimensions + EXIF from an image using Pillow only."""
    meta = MediaMeta(media_type="image")
    if Image is None:
        return meta
    try:
        with Image.open(path) as img:
            meta.width, meta.height = img.size
            meta.mime_type = Image.MIME.get(img.format or "", "")
            exif = img.getexif()
    except Exception:  # noqa: BLE001
        return meta

    if not exif:
        return meta

    dt = exif.get(_EXIF_TAGS["DateTimeOriginal"]) or exif.get(_EXIF_TAGS["DateTime"])
    if dt:
        parsed = _parse_exif_datetime(str(dt))
        if parsed:
            meta.taken_at = parsed
            meta.taken_source = "exif"

    make = exif.get(_EXIF_TAGS["Make"])
    model = exif.get(_EXIF_TAGS["Model"])
    meta.camera_make = str(make).strip() if make else None
    meta.camera_model = str(model).strip() if model else None

    gps = exif.get_ifd(_EXIF_TAGS["GPSInfo"]) if hasattr(exif, "get_ifd") else None
    if gps:
        lat = _gps_to_decimal(gps.get(2), gps.get(1))
        lon = _gps_to_decimal(gps.get(4), gps.get(3))
        if lat is not None and lon is not None:
            meta.lat, meta.lon = lat, lon
        if gps.get(6) is not None:
            try:
                meta.altitude = float(gps.get(6))
            except (TypeError, ValueError):
                pass
    return meta


def extract_video_metadata(path: str | Path) -> MediaMeta:
    """Read duration / dimensions from a video using ffprobe."""
    ext = Path(path).suffix.lower()
    meta = MediaMeta(
        media_type="video",
        mime_type=VIDEO_MIME.get(ext, "video/mp4"),
    )
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return meta

    fmt = data.get("format", {})
    if "duration" in fmt:
        try:
            meta.duration = round(float(fmt["duration"]), 2)
        except (TypeError, ValueError):
            pass

    tags = fmt.get("tags", {})
    for key in ("creation_time", "com.apple.quicktime.creationdate"):
        if key in tags:
            raw = str(tags[key]).replace("Z", "+00:00")
            try:
                meta.taken_at = datetime.fromisoformat(raw).replace(tzinfo=None)
                meta.taken_source = "exif"
            except ValueError:
                pass
            break

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            meta.width = stream.get("width")
            meta.height = stream.get("height")
            break
    return meta


def extract_with_exiftool(path: str | Path) -> MediaMeta | None:
    """Fallback extractor using exiftool for formats Pillow cannot read."""
    try:
        proc = subprocess.run(
            ["exiftool", "-json", "-n", "-DateTimeOriginal", "-Make", "-Model",
             "-GPSLatitude", "-GPSLongitude", "-ImageWidth", "-ImageHeight",
             "-Duration", "-MIMEType", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        records = json.loads(proc.stdout or "[]")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None
    if not records:
        return None
    r = records[0]
    meta = MediaMeta(mime_type=r.get("MIMEType", ""))
    meta.media_type = "video" if meta.mime_type.startswith("video") else "image"
    meta.width = r.get("ImageWidth")
    meta.height = r.get("ImageHeight")
    meta.camera_make = r.get("Make")
    meta.camera_model = r.get("Model")
    meta.lat = r.get("GPSLatitude")
    meta.lon = r.get("GPSLongitude")
    if r.get("Duration"):
        try:
            meta.duration = float(r["Duration"])
        except (TypeError, ValueError):
            pass
    if r.get("DateTimeOriginal"):
        parsed = _parse_exif_datetime(str(r["DateTimeOriginal"]))
        if parsed:
            meta.taken_at, meta.taken_source = parsed, "exif"
    return meta


def extract_metadata(path: str | Path, media_type: str) -> MediaMeta:
    """Public entry point: pick the right extractor for the media type."""
    if media_type == "video":
        meta = extract_video_metadata(path)
        if meta.width is None:  # ffprobe failed -> try exiftool
            fallback = extract_with_exiftool(path)
            if fallback is not None:
                return fallback
        return meta

    meta = extract_image_metadata(path)
    if meta.width is None:  # Pillow failed -> try exiftool
        fallback = extract_with_exiftool(path)
        if fallback is not None:
            return fallback
    return meta
