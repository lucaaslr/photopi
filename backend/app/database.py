"""Database engine and session management.

Uses SQLAlchemy 2.0 async. SQLite is the default and is tuned with WAL mode
so that the indexer can write while the API reads concurrently. PostgreSQL
works transparently by changing DATABASE_URL.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine() -> AsyncEngine:
    url = settings.database_url
    is_sqlite = url.startswith("sqlite")

    connect_args: dict = {}
    engine_kwargs: dict = {
        "echo": settings.debug,
        "future": True,
        "pool_pre_ping": True,
    }
    if is_sqlite:
        # Allow the connection to wait on a locked DB instead of failing fast.
        connect_args["timeout"] = 30  # seconds
        # aiosqlite uses NullPool, which does not accept pool sizing kwargs.
    else:
        # Keep the pool small: a Pi cannot afford many open connections.
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 5

    engine = create_async_engine(url, connect_args=connect_args, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            # WAL: concurrent reader + single writer, far less locking.
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA foreign_keys=ON")
            # ~8MB page cache is plenty and keeps RAM usage predictable.
            cur.execute("PRAGMA cache_size=-8000")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()

    return engine


engine: AsyncEngine = _make_engine()

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, expire_on_commit=False, autoflush=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables if they do not exist (used for first-run / tests)."""
    from app import models  # noqa: F401  (ensure models are registered)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def healthcheck() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
