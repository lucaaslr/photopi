"""Tests for the Google Takeout sidecar matcher and parser."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.takeout import (
    album_name_for,
    find_sidecar,
    is_album_folder,
    parse_sidecar,
)


def test_find_sidecar_classic():
    names = {"IMG_1234.JPG.json", "IMG_5678.JPG.json"}
    assert find_sidecar("IMG_1234.JPG", names) == "IMG_1234.JPG.json"


def test_find_sidecar_supplemental_metadata():
    names = {"IMG_1234.JPG.supplemental-metadata.json"}
    assert (
        find_sidecar("IMG_1234.JPG", names)
        == "IMG_1234.JPG.supplemental-metadata.json"
    )


def test_find_sidecar_dedup_counter():
    # name(1).jpg pairs with name.jpg(1).json
    names = {"IMG_1234.JPG(1).json"}
    assert find_sidecar("IMG_1234(1).JPG", names) == "IMG_1234.JPG(1).json"


def test_find_sidecar_edited_reuses_original():
    names = {"IMG_1234.JPG.json"}
    assert find_sidecar("IMG_1234-edited.JPG", names) == "IMG_1234.JPG.json"


def test_find_sidecar_truncated_fuzzy():
    # Google truncates very long sidecar names.
    names = {"a_very_long_photo_name_1234.JPG.supplemental-met.json"}
    match = find_sidecar("a_very_long_photo_name_1234.JPG", names)
    assert match == "a_very_long_photo_name_1234.JPG.supplemental-met.json"


def test_find_sidecar_no_match():
    assert find_sidecar("IMG_0001.JPG", {"OTHER.JPG.json"}) is None
    assert find_sidecar("IMG_0001.JPG", set()) is None


def test_is_album_folder_rejects_date_buckets(tmp_path: Path):
    gp = tmp_path / "Takeout" / "Google Photos"
    date_folder = gp / "Photos from 2024"
    date_folder.mkdir(parents=True)
    assert is_album_folder(date_folder) is False

    year_folder = gp / "2023"
    year_folder.mkdir()
    assert is_album_folder(year_folder) is False


def test_is_album_folder_accepts_named_album(tmp_path: Path):
    gp = tmp_path / "Takeout" / "Google Photos"
    album = gp / "Summer Trip"
    album.mkdir(parents=True)
    assert is_album_folder(album) is True


def test_album_name_prefers_metadata_json(tmp_path: Path):
    gp = tmp_path / "Takeout" / "Google Photos"
    album = gp / "folder-slug"
    album.mkdir(parents=True)
    (album / "metadata.json").write_text(
        json.dumps({"title": "My Real Album"}), encoding="utf-8"
    )
    assert album_name_for(album) == "My Real Album"


def test_album_name_falls_back_to_folder(tmp_path: Path):
    gp = tmp_path / "Takeout" / "Google Photos"
    album = gp / "Beach Days"
    album.mkdir(parents=True)
    assert album_name_for(album) == "Beach Days"


def test_parse_sidecar_full(tmp_path: Path):
    sidecar = tmp_path / "IMG_1234.JPG.json"
    sidecar.write_text(
        json.dumps(
            {
                "title": "IMG_1234.JPG",
                "description": "  A sunset  ",
                "photoTakenTime": {"timestamp": "1704067200"},  # 2024-01-01 UTC
                "geoData": {
                    "latitude": 48.8584,
                    "longitude": 2.2945,
                    "altitude": 35.0,
                },
                "people": [{"name": "Alice"}, {"name": "Bob"}],
                "favorited": True,
            }
        ),
        encoding="utf-8",
    )
    meta = parse_sidecar(sidecar)
    assert meta.title == "IMG_1234.JPG"
    assert meta.description == "A sunset"
    assert meta.taken_at is not None
    assert meta.taken_at.year == 2024
    assert meta.lat == pytest.approx(48.8584)
    assert meta.lon == pytest.approx(2.2945)
    assert meta.altitude == pytest.approx(35.0)
    assert meta.people == ["Alice", "Bob"]
    assert meta.favorite is True


def test_parse_sidecar_ignores_zero_gps(tmp_path: Path):
    sidecar = tmp_path / "x.json"
    sidecar.write_text(
        json.dumps(
            {"geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0}}
        ),
        encoding="utf-8",
    )
    meta = parse_sidecar(sidecar)
    assert meta.lat is None
    assert meta.lon is None


def test_parse_sidecar_handles_bad_json(tmp_path: Path):
    sidecar = tmp_path / "broken.json"
    sidecar.write_text("{ not valid json", encoding="utf-8")
    meta = parse_sidecar(sidecar)
    # Should degrade gracefully rather than raise.
    assert meta.taken_at is None
    assert meta.title is None
