"""Data access for Albums and album membership."""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.album import Album, AlbumItem
from app.repositories.base import BaseRepository


def slugify(name: str) -> str:
    """Filesystem/URL-safe slug derived from an album name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "album"


class AlbumRepository(BaseRepository):
    async def get(self, album_id: int) -> Album | None:
        return await self.session.get(Album, album_id)

    async def get_with_items(self, album_id: int) -> Album | None:
        result = await self.session.execute(
            select(Album)
            .where(Album.id == album_id)
            .options(selectinload(Album.items))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Album | None:
        result = await self.session.execute(
            select(Album).where(Album.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_share_token(self, token: str) -> Album | None:
        result = await self.session.execute(
            select(Album).where(Album.share_token == token, Album.is_shared.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[tuple[Album, int]]:
        """Return (album, item_count) tuples ordered by name."""
        count_sq = (
            select(AlbumItem.album_id, func.count(AlbumItem.id).label("n"))
            .group_by(AlbumItem.album_id)
            .subquery()
        )
        result = await self.session.execute(
            select(Album, func.coalesce(count_sq.c.n, 0))
            .outerjoin(count_sq, count_sq.c.album_id == Album.id)
            .order_by(Album.name)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def create(
        self, *, name: str, description: str | None = None, source: str = "manual"
    ) -> Album:
        base = slugify(name)
        slug = base
        suffix = 1
        while await self.get_by_slug(slug) is not None:
            suffix += 1
            slug = f"{base}-{suffix}"
        album = Album(name=name, slug=slug, description=description, source=source)
        self.session.add(album)
        await self.session.flush()
        return album

    async def get_or_create_takeout(self, name: str) -> Album:
        """Idempotently fetch/create a Takeout-reconstructed album by name."""
        result = await self.session.execute(
            select(Album).where(Album.name == name, Album.source == "takeout")
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        return await self.create(name=name, source="takeout")

    async def add_item(self, album_id: int, media_id: int) -> bool:
        """Add media to an album. Returns False if it was already present."""
        existing = await self.session.execute(
            select(AlbumItem.id).where(
                AlbumItem.album_id == album_id, AlbumItem.media_id == media_id
            )
        )
        if existing.scalar_one_or_none() is not None:
            return False
        pos_result = await self.session.execute(
            select(func.coalesce(func.max(AlbumItem.position), -1)).where(
                AlbumItem.album_id == album_id
            )
        )
        position = int(pos_result.scalar_one()) + 1
        self.session.add(
            AlbumItem(album_id=album_id, media_id=media_id, position=position)
        )
        await self.session.flush()
        return True

    async def remove_item(self, album_id: int, media_id: int) -> None:
        result = await self.session.execute(
            select(AlbumItem).where(
                AlbumItem.album_id == album_id, AlbumItem.media_id == media_id
            )
        )
        item = result.scalar_one_or_none()
        if item:
            await self.session.delete(item)

    async def item_count(self, album_id: int) -> int:
        result = await self.session.execute(
            select(func.count(AlbumItem.id)).where(AlbumItem.album_id == album_id)
        )
        return int(result.scalar_one())

    async def delete(self, album: Album) -> None:
        await self.session.delete(album)

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Album.id)))
        return int(result.scalar_one())
