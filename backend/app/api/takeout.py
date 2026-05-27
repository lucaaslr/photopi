"""Takeout import endpoints.

Upload Takeout archives into a staging folder on the HDD, list/delete
them, and kick off a background job that extracts them into the canonical
``Google Photos/`` tree and (optionally) triggers a reindex afterwards.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.serializers import job_to_out
from app.config import settings
from app.core.deps import require_admin
from app.schemas.admin import IndexJobOut
from app.schemas.takeout import (
    StagedArchive,
    StagedList,
    TakeoutImportRequest,
    TakeoutUploadResult,
)
from app.services import takeout_import as ti
from app.workers import takeout_job_manager

router = APIRouter(prefix="/admin/takeout", tags=["takeout"])
logger = logging.getLogger("photopi.takeout.api")


def _staging_dir() -> Path:
    p = Path(settings.takeout_staging_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_name(name: str) -> str:
    """Reject path traversal in user-supplied filenames."""
    base = Path(name).name
    if not base or base in (".", ".."):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid filename")
    return base


@router.get("/staged", response_model=StagedList)
async def list_staged(_admin=Depends(require_admin)) -> StagedList:
    staging = _staging_dir()
    items = [StagedArchive(**i) for i in ti.list_staged(staging)]
    return StagedList(items=items, staging_dir=str(staging))


@router.delete("/staged/{name}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_staged(name: str, _admin=Depends(require_admin)) -> None:
    safe = _safe_name(name)
    target = _staging_dir() / safe
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Archive not found")
    if not ti.is_archive(target):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not an archive")
    try:
        target.unlink()
    except OSError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc


@router.post(
    "/upload",
    response_model=TakeoutUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_archives(
    files: list[UploadFile] = File(...),
    _admin=Depends(require_admin),
) -> TakeoutUploadResult:
    """Stream one or more Takeout archives into the staging folder."""
    staging = _staging_dir()
    uploaded: list[str] = []
    errors: list[dict] = []

    for f in files:
        try:
            base = _safe_name(f.filename or "")
            target = staging / base
            if target.exists():
                stem, ext = target.stem, target.suffix
                n = 1
                while (staging / f"{stem}_{n}{ext}").exists():
                    n += 1
                target = staging / f"{stem}_{n}{ext}"
            tmp = target.with_name(target.name + ".partial")
            try:
                with tmp.open("wb") as out:
                    while chunk := await f.read(1024 * 1024):  # 1MB
                        out.write(chunk)
                tmp.replace(target)
            except OSError:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                raise
            if not ti.is_archive(target):
                # Reject non-archive uploads after the fact.
                target.unlink()
                errors.append({"filename": base, "error": "not a supported archive"})
                continue
            uploaded.append(target.name)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            errors.append({"filename": f.filename or "", "error": str(exc)})

    if not uploaded and errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"errors": errors})
    return TakeoutUploadResult(uploaded=uploaded, errors=errors)


@router.get("/status", response_model=IndexJobOut | None)
async def takeout_status(_admin=Depends(require_admin)) -> IndexJobOut | None:
    job = await takeout_job_manager.latest_job()
    return job_to_out(job) if job else None


@router.post(
    "/import",
    response_model=IndexJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_import(
    body: TakeoutImportRequest,
    _admin=Depends(require_admin),
) -> IndexJobOut:
    staging = _staging_dir()

    if body.archives:
        targets: list[Path] = []
        for name in body.archives:
            safe = _safe_name(name)
            p = staging / safe
            if not p.is_file() or not ti.is_archive(p):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Not a staged archive: {safe}",
                )
            targets.append(p)
    else:
        targets = [
            staging / item["name"] for item in ti.list_staged(staging)
        ]
        if not targets:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "No archives in staging folder",
            )

    try:
        await takeout_job_manager.start(
            targets,
            Path(settings.media_root),
            delete_on_success=body.delete_on_success,
            trigger_index=body.trigger_index,
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    job = await takeout_job_manager.latest_job()
    if job is None:  # pragma: no cover
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Job not created")
    return job_to_out(job)
