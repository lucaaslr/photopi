"""Lightweight hashing utilities.

 * content_hash - fast exact-duplicate detection without reading whole files
 * dhash        - perceptual hash for near-duplicate image detection

No external imagehash dependency: dHash is ~15 lines with Pillow.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

# Bytes sampled from the head and tail of a file for the content hash.
_SAMPLE = 65536


def content_hash(path: str | Path, size_bytes: int) -> str:
    """SHA1 over file size + head + tail samples.

    Reading only two 64KB windows keeps disk IO tiny even for 4K videos,
    while still being collision-resistant enough for de-duplication.
    """
    h = hashlib.sha1()
    h.update(str(size_bytes).encode())
    p = Path(path)
    with p.open("rb") as fh:
        head = fh.read(_SAMPLE)
        h.update(head)
        if size_bytes > _SAMPLE * 2:
            fh.seek(-_SAMPLE, 2)
            h.update(fh.read(_SAMPLE))
    return h.hexdigest()


def dhash(path: str | Path, size: int = 8) -> str | None:
    """Difference hash of an image, returned as a hex string.

    Resizes to (size+1 x size) grayscale and compares adjacent pixels.
    Returns None if the image cannot be read.
    """
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("L").resize((size + 1, size), Image.BILINEAR)
            pixels = list(img.getdata())
    except Exception:  # noqa: BLE001
        return None

    bits = 0
    for row in range(size):
        for col in range(size):
            left = pixels[row * (size + 1) + col]
            right = pixels[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:0{size * size // 4}x}"


def hamming_distance(a: str, b: str) -> int:
    """Number of differing bits between two equal-length hex hashes."""
    if not a or not b or len(a) != len(b):
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")
