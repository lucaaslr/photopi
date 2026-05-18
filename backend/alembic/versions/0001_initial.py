"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users ------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # --- media ------------------------------------------------------------
    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("rel_path", sa.String(length=1024), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("ext", sa.String(length=16), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("taken_at", sa.DateTime(), nullable=False),
        sa.Column("taken_source", sa.String(length=16), nullable=False),
        sa.Column("camera_make", sa.String(length=128), nullable=True),
        sa.Column("camera_model", sa.String(length=128), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("phash", sa.String(length=32), nullable=True),
        sa.Column("duplicate_of", sa.Integer(), nullable=True),
        sa.Column("thumb_status", sa.String(length=16), nullable=False),
        sa.Column("takeout_json", sa.String(length=1024), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["duplicate_of"], ["media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_path", "media", ["path"], unique=True)
    op.create_index("ix_media_filename", "media", ["filename"])
    op.create_index("ix_media_media_type", "media", ["media_type"])
    op.create_index("ix_media_taken_at", "media", ["taken_at"])
    op.create_index("ix_media_camera_model", "media", ["camera_model"])
    op.create_index("ix_media_favorite", "media", ["favorite"])
    op.create_index("ix_media_archived", "media", ["archived"])
    op.create_index("ix_media_content_hash", "media", ["content_hash"])
    op.create_index("ix_media_phash", "media", ["phash"])
    op.create_index("ix_media_timeline", "media", ["archived", "taken_at", "id"])
    op.create_index("ix_media_type_taken", "media", ["media_type", "taken_at"])

    # --- albums -----------------------------------------------------------
    op.create_table(
        "albums",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("slug", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("cover_media_id", sa.Integer(), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("share_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cover_media_id"], ["media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_albums_name", "albums", ["name"])
    op.create_index("ix_albums_slug", "albums", ["slug"], unique=True)
    op.create_index("ix_albums_share_token", "albums", ["share_token"], unique=True)

    # --- album_items ------------------------------------------------------
    op.create_table(
        "album_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("album_id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("album_id", "media_id", name="uq_album_media"),
    )
    op.create_index("ix_album_items_album_id", "album_items", ["album_id"])
    op.create_index("ix_album_items_media_id", "album_items", ["media_id"])

    # --- index_jobs -------------------------------------------------------
    op.create_table(
        "index_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("root_path", sa.String(length=1024), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False),
        sa.Column("processed_files", sa.Integer(), nullable=False),
        sa.Column("indexed_files", sa.Integer(), nullable=False),
        sa.Column("updated_files", sa.Integer(), nullable=False),
        sa.Column("skipped_files", sa.Integer(), nullable=False),
        sa.Column("failed_files", sa.Integer(), nullable=False),
        sa.Column("current_path", sa.String(length=1024), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_index_jobs_status", "index_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("index_jobs")
    op.drop_table("album_items")
    op.drop_table("albums")
    op.drop_table("media")
    op.drop_table("users")
