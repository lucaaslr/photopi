"""PhotoPi FastAPI application.

Wires together configuration, the database, the API routers and the
background job manager. The lifespan handler performs first-run setup:
directory creation, schema initialisation, admin bootstrap and recovery
of any indexing job left dangling by a restart.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal, healthcheck, init_db
from app.repositories.user import UserRepository
from app.workers import job_manager, takeout_job_manager

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("photopi")


async def _bootstrap_admin() -> None:
    """Create the initial admin account if the user table is empty."""
    async with SessionLocal() as session:
        repo = UserRepository(session)
        if await repo.count() == 0:
            await repo.create(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
            )
            await session.commit()
            logger.info(
                "Created bootstrap admin user '%s'. Change the password!",
                settings.admin_username,
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup / shutdown."""
    logger.info("Starting %s", settings.app_name)
    settings.ensure_dirs()
    await init_db()
    await _bootstrap_admin()
    await job_manager.recover_stale_jobs()
    await takeout_job_manager.recover_stale_jobs()
    logger.info("Startup complete. Media root: %s", settings.media_root)
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title="PhotoPi API",
    description=(
        "A lightweight, self-hosted photo management API designed for "
        "Raspberry Pi 3B+. Indexes Google Photos Takeout exports from an "
        "external HDD with a low memory footprint."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> JSONResponse:
    """Liveness/readiness probe used by Docker healthchecks."""
    db_ok = await healthcheck()
    payload = {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "version": "1.0.0",
        "database": "ok" if db_ok else "error",
        "indexing": job_manager.is_running(),
    }
    return JSONResponse(payload, status_code=200 if db_ok else 503)


@app.get("/", tags=["system"])
async def root() -> dict:
    """Friendly root payload pointing at the docs."""
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "api": "/api",
    }
