# Photopi Project Instructions

Photopi is a lightweight, self-hosted photo management platform optimized for Raspberry Pi. It indexes Google Photos Takeout exports.

## Core Architecture

### Backend (Python/FastAPI)
- **Location:** `./backend`
- **Framework:** FastAPI with Uvicorn worker.
- **Database:** SQLAlchemy with `aiosqlite` (default) or `asyncpg` (Postgres).
- **Migrations:** Alembic (`./backend/alembic`).
- **Core Logic:**
    - `Indexer` (`./backend/app/services/indexer.py`): Incremental scanning of `PHOTOS_DIR`. Uses a `ThreadPoolExecutor` for CPU-bound tasks (thumbnails, phash).
    - `Metadata` (`./backend/app/services/metadata.py`): Extraction of EXIF and media info.
    - `Takeout` (`./backend/app/services/takeout.py`): Parsing of Google Photos JSON sidecar files.
- **Security:** JWT-based authentication with a bootstrap admin account created on first run.

### Frontend (Next.js/TypeScript)
- **Location:** `./web`
- **Framework:** Next.js 14 (App Router).
- **Styling:** Tailwind CSS.
- **API Client:** `./web/src/lib/api.ts` (Typed wrapper around backend REST API).
- **Key Views:**
    - Timeline (Infinite scroll gallery).
    - Media Viewer (Metadata, full-screen, video support).
    - Albums (Manual and Takeout-reconstructed).
    - Admin (Storage stats, live indexing control).

### Infrastructure
- **Docker:** `docker-compose.yml` (SQLite) and `docker-compose.postgres.yml` (Postgres override).
- **Storage:** Host path `PHOTOS_DIR` is mounted at `/mnt/google-photos`. Admins can manage files (upload, move, delete) via the UI.

### New Features
- **Storage Manager:** Admin-only interface for manipulating files on the HDD.
- **Uploads:** Support for direct media and Takeout file uploads.

## Project Conventions

- **Surgical Updates:** When modifying code, prioritize minimal changes that maintain architectural consistency.
- **Performance:** Keep Raspberry Pi constraints in mind (low RAM, single-threaded indexing preference).
- **Testing:** Backend tests use `pytest` in `./backend/tests`.
- **Environment:** Config via `.env` files. `backend/app/config.py` centralizes settings.

## Important Files
- `backend/app/models/media.py`: Primary media schema.
- `backend/app/services/indexer.py`: Main indexing pipeline.
- `web/src/lib/api.ts`: Frontend/Backend contract.
- `docker-compose.yml`: Deployment blueprint.
