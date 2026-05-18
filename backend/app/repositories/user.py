"""Data access for User accounts."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar_one())

    async def list_all(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.id))
        return list(result.scalars().all())

    async def create(
        self, *, username: str, password_hash: str, is_admin: bool = False
    ) -> User:
        user = User(
            username=username, password_hash=password_hash, is_admin=is_admin
        )
        self.session.add(user)
        await self.session.flush()
        return user
