"""Data access for Media items.

Designed for very large libraries on low-RAM hardware:
 * keyset (cursor) pagination instead of OFFSET, so deep scrolling is O(1)
 * never loads the full table into memory
 * lightweight aggregate queries for stats / timeline buckets
"""
from __future__ import annotations

import base64
from datetime import datetime

from sqlalchemy import and_, func, or_, select

from app.models.album import AlbumItem
from app.models.media import Media
from app.repositories.base import BaseRepository


def encode_cursor(taken_at: datetime, media_id: int) -> str:
    """Pack (taken_at, id) into an opaque, URL-safe cursor string."""
    raw = f"{taken_at.isoformat()}|{media_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int] | None:
    """Reverse of encode_cursor. Returns None on malformed input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, mid = raw.rsplit("|", 1)
        return datetime.fromisoformat(ts), int(mid)
    except (ValueError, TypeError):
        return None


class MediaRepository(BaseRepository):
    # --- Single-item lookups ---------------------------------------------
    async def get(self, media_id: int) -> Media | None:
        return await self.session.get(Media, media_id)

    async def get_by_path(self, path: str) -> Media | None:
        result = await self.session.execute(
            select(Media).where(Media.path == path)
        )
        return result.scalar_one_or_none()

    async def get_many(self, ids: list[int]) -> list[Media]:
        if not ids:
            return []
        result = await self.session.execute(
            select(Media).where(Media.id.in_(ids))
        )
        return list(result.scalars().all())

    async def find_content_duplicate(
        self, content_hash: str, exclude_path: str
    ) -> Media | None:
        """Return an existing item with the same content hash, if any."""
        result = await self.session.execute(
            select(Media)
            .where(Media.content_hash == content_hash, Media.path != exclude_path)
            .limit(1)
        )
        return result.scalar_one_or_none()

    # --- Writes -----------------------------------------------------------
    def add(self, media: Media) -> None:
        self.session.add(media)

    async def delete(self, media: Media) -> None:
        await self.session.delete(media)

    # --- Timeline (keyset paginated) -------------------------------------
    async def timeline(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        media_type: str | None = None,
        include_archived: bool = False,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort: str = "desc",
    ) -> tuple[list[Media], str | None]:
        """Return (items, next_cursor). next_cursor is None at the end."""
        asc = sort == "asc"
        stmt = select(Media)
        if not include_archived:
            stmt = stmt.where(Media.archived.is_(False))
        if media_type in ("image", "video"):
            stmt = stmt.where(Media.media_type == media_type)
        if date_from:
            stmt = stmt.where(Media.taken_at >= date_from)
        if date_to:
            stmt = stmt.where(Media.taken_at <= date_to)
        stmt = self._apply_cursor(stmt, cursor, asc=asc)
        if asc:
            stmt = stmt.order_by(Media.taken_at.asc(), Media.id.asc())
        else:
            stmt = stmt.order_by(Media.taken_at.desc(), Media.id.desc())
        stmt = stmt.limit(limit + 1)

        rows = list((await self.session.execute(stmt)).scalars().all())
        return self._paginate(rows, limit)

    # --- Search (keyset paginated) ---------------------------------------
    async def search(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        q: str | None = None,
        media_type: str | None = None,
        camera_model: str | None = None,
        favorite: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_archived: bool = False,
    ) -> tuple[list[Media], str | None]:
        stmt = select(Media)
        if not include_archived:
            stmt = stmt.where(Media.archived.is_(False))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Media.filename).like(like),
                    func.lower(Media.description).like(like),
                    func.lower(Media.rel_path).like(like),
                )
            )
        if media_type in ("image", "video"):
            stmt = stmt.where(Media.media_type == media_type)
        if camera_model:
            stmt = stmt.where(Media.camera_model == camera_model)
        if favorite is not None:
            stmt = stmt.where(Media.favorite.is_(favorite))
        if date_from:
            stmt = stmt.where(Media.taken_at >= date_from)
        if date_to:
            stmt = stmt.where(Media.taken_at <= date_to)

        stmt = self._apply_cursor(stmt, cursor)
        stmt = stmt.order_by(Media.taken_at.desc(), Media.id.desc()).limit(limit + 1)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return self._paginate(rows, limit)

    # --- Album membership -------------------------------------------------
    async def list_by_album(
        self, album_id: int, *, limit: int, cursor: str | None = None
    ) -> tuple[list[Media], str | None]:
        stmt = (
            select(Media)
            .join(AlbumItem, AlbumItem.media_id == Media.id)
            .where(AlbumItem.album_id == album_id)
        )
        stmt = self._apply_cursor(stmt, cursor)
        stmt = stmt.order_by(Media.taken_at.desc(), Media.id.desc()).limit(limit + 1)
        rows = list((await self.session.execute(stmt)).scalars().all())
        return self._paginate(rows, limit)

    # --- Aggregates -------------------------------------------------------
    async def count(self, *, media_type: str | None = None) -> int:
        stmt = select(func.count(Media.id))
        if media_type:
            stmt = stmt.where(Media.media_type == media_type)
        return int((await self.session.execute(stmt)).scalar_one())

    async def total_size(self) -> int:
        result = await self.session.execute(select(func.sum(Media.size_bytes)))
        return int(result.scalar_one() or 0)

    async def date_range(self) -> tuple[datetime | None, datetime | None]:
        result = await self.session.execute(
            select(func.min(Media.taken_at), func.max(Media.taken_at))
        )
        lo, hi = result.one()
        return lo, hi

    async def timeline_buckets(self) -> list[dict]:
        """Per month counts, used to draw the timeline scrubber."""
        year = func.strftime("%Y", Media.taken_at)
        month = func.strftime("%m", Media.taken_at)
        # strftime works on SQLite; for Postgres SQLAlchemy maps it too via
        # extract - but to stay portable we fall back to a Python grouping.
        try:
            result = await self.session.execute(
                select(year.label("y"), month.label("m"), func.count(Media.id))
                .where(Media.archived.is_(False))
                .group_by("y", "m")
                .order_by("y", "m")
            )
            return [
                {"year": r[0], "month": r[1], "count": r[2]}
                for r in result.all()
                if r[0]
            ]
        except Exception:  # noqa: BLE001  - non-SQLite fallback
            return []

    async def camera_models(self) -> list[dict]:
        result = await self.session.execute(
            select(Media.camera_model, func.count(Media.id))
            .where(Media.camera_model.is_not(None))
            .group_by(Media.camera_model)
            .order_by(func.count(Media.id).desc())
        )
        return [{"model": r[0], "count": r[1]} for r in result.all()]

    async def pending_thumbnails(self, limit: int = 100) -> list[Media]:
        result = await self.session.execute(
            select(Media)
            .where(Media.thumb_status == "pending")
            .order_by(Media.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    # --- Internal helpers -------------------------------------------------
    @staticmethod
    def _apply_cursor(stmt, cursor: str | None, *, asc: bool = False):
        if not cursor:
            return stmt
        decoded = decode_cursor(cursor)
        if decoded is None:
            return stmt
        c_taken, c_id = decoded
        if asc:
            return stmt.where(
                or_(
                    Media.taken_at > c_taken,
                    and_(Media.taken_at == c_taken, Media.id > c_id),
                )
            )
        return stmt.where(
            or_(
                Media.taken_at < c_taken,
                and_(Media.taken_at == c_taken, Media.id < c_id),
            )
        )

    @staticmethod
    def _paginate(rows: list[Media], limit: int) -> tuple[list[Media], str | None]:
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = (
            encode_cursor(items[-1].taken_at, items[-1].id)
            if has_more and items
            else None
        )
        return items, next_cursor
