"""Repository pattern base class.

Repositories encapsulate all database access so that services and API
routes never build queries directly.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Holds the active session for a unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def flush(self) -> None:
        await self.session.flush()
