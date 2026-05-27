"""Centralised application configuration.

All values can be overridden through environment variables (see .env.example).
Defaults are tuned for a Raspberry Pi 3B+ (1GB RAM, ARM64, DietPi).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- General -----------------------------------------------------------
    app_name: str = "PhotoPi"
    environment: str = "production"
    debug: bool = False

    # --- Storage paths -----------------------------------------------------
    # External USB HDD with the extracted Google Photos Takeout export.
    media_root: str = "/mnt/google-photos"
    # Local app data (database, thumbnails, cache). Docker volume.
    data_dir: str = "/data"
    # Where uploaded Takeout archives are staged before extraction. Lives
    # OUTSIDE media_root so the indexer never walks raw .zip files.
    takeout_staging_dir: str = "/mnt/google-photos/backup_google_photos"

    # --- Database ----------------------------------------------------------
    # SQLite by default; set to a postgresql+asyncpg:// URL to use Postgres.
    database_url: str = "sqlite+aiosqlite:///./data/photopi.db"

    # --- Security ----------------------------------------------------------
    jwt_secret: str = "change-me-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    # Bootstrap admin account, created on first start if no users exist.
    admin_username: str = "admin"
    admin_password: str = "changeme"
    allow_guest: bool = False  # public read-only browsing of shared albums

    # --- CORS --------------------------------------------------------------
    cors_origins: str = "*"

    # --- Indexing / Pi performance tuning ---------------------------------
    # Files committed to the DB per transaction (batched writes).
    index_batch_size: int = 50
    # Directory entries pulled per os.scandir chunk (chunked FS scanning).
    scan_chunk_size: int = 250
    # Sleep (milliseconds) between processing each file -> CPU throttle.
    index_throttle_ms: int = 0
    # Threads used for blocking image/video work. Keep tiny on a Pi.
    thumb_workers: int = 1

    # --- Thumbnails / previews --------------------------------------------
    thumb_size: int = 320          # grid thumbnail longest edge (px)
    preview_size: int = 1280       # viewer preview longest edge (px)
    thumb_quality: int = 75        # JPEG quality for generated images
    enable_video_thumbs: bool = True

    # --- API pagination ----------------------------------------------------
    default_page_size: int = 60
    max_page_size: int = 200

    @field_validator("media_root", "data_dir")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/") or "/"

    # --- Derived paths -----------------------------------------------------
    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def thumb_dir(self) -> Path:
        return self.data_path / "thumbnails"

    @property
    def preview_dir(self) -> Path:
        return self.data_path / "previews"

    @property
    def cache_dir(self) -> Path:
        return self.data_path / "cache"

    @property
    def media_path(self) -> Path:
        return Path(self.media_root)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        """Create all local storage directories if they do not exist."""
        for p in (self.data_path, self.thumb_dir, self.preview_dir, self.cache_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
