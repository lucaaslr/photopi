"""Aggregate API router.

All feature routers are mounted under a single ``/api`` prefix so the
nginx reverse proxy can forward one path cleanly to the backend.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api import admin, albums, auth, media, search, storage

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(media.router)
api_router.include_router(search.router)
api_router.include_router(albums.router)
api_router.include_router(admin.router)
api_router.include_router(storage.router)
