"""Storage management endpoints.

Allows admins to manage files on the external HDD.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status

from app.core.deps import require_admin
from app.services.storage import StorageService
from app.schemas.storage import StorageItem, StorageList, MoveRequest, MkdirRequest

router = APIRouter(prefix="/admin/storage", tags=["storage"])


@router.get("/ls", response_model=StorageList)
async def list_directory(
    path: str = "",
    _admin=Depends(require_admin),
) -> StorageList:
    """List contents of a directory in the media root."""
    svc = StorageService()
    try:
        items = svc.list_dir(path)
        parent = str(Path(path).parent) if path and path != "." else None
        return StorageList(
            items=[StorageItem(**item) for item in items],
            current_path=path,
            parent_path=parent if parent != "." else ""
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_files(
    path: str = Form(""),
    files: List[UploadFile] = File(...),
    _admin=Depends(require_admin),
) -> dict:
    """Upload one or more files to a specific directory."""
    svc = StorageService()
    uploaded = []
    errors = []
    
    for file in files:
        try:
            saved_path = await svc.save_upload(path, file)
            uploaded.append(saved_path)
        except Exception as exc:
            errors.append({"filename": file.filename, "error": str(exc)})
            
    if errors and not uploaded:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"detail": "Upload failed", "errors": errors})
        
    return {
        "status": "partial_success" if errors else "success",
        "uploaded": uploaded,
        "errors": errors if errors else None
    }


@router.delete("/rm", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_item(
    path: str,
    _admin=Depends(require_admin),
) -> None:
    """Delete a file or directory (recursively)."""
    svc = StorageService()
    try:
        svc.delete(path)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/mv", response_model=dict)
async def move_item(
    body: MoveRequest,
    _admin=Depends(require_admin),
) -> dict:
    """Rename or move a file/directory."""
    svc = StorageService()
    try:
        new_path = svc.move(body.old_path, body.new_path)
        return {"status": "success", "path": new_path}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/mkdir", response_model=dict)
async def create_directory(
    body: MkdirRequest,
    _admin=Depends(require_admin),
) -> dict:
    """Create a new directory."""
    svc = StorageService()
    try:
        new_path = svc.mkdir(body.path)
        return {"status": "success", "path": new_path}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/extract", response_model=dict)
async def extract_archive(
    path: str,
    _admin=Depends(require_admin),
) -> dict:
    """Extract a ZIP or Tar archive."""
    svc = StorageService()
    try:
        dest_path = svc.extract(path)
        return {"status": "success", "destination": dest_path}
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
