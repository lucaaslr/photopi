import pytest
from httpx import AsyncClient
from fastapi import status
from pathlib import Path
import os
import shutil

@pytest.mark.asyncio
async def test_storage_list(admin_client: AsyncClient, tmp_path: Path, monkeypatch):
    # Mock media_path to tmp_path
    monkeypatch.setattr("app.config.settings.media_root", str(tmp_path))
    
    # Create some dummy files
    (tmp_path / "folder1").mkdir()
    (tmp_path / "file1.txt").write_text("hello")
    
    resp = await admin_client.get("/api/admin/storage/ls")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["items"]) == 2
    assert any(item["name"] == "folder1" and item["is_dir"] for item in data["items"])
    assert any(item["name"] == "file1.txt" and not item["is_dir"] for item in data["items"])

@pytest.mark.asyncio
async def test_storage_upload(admin_client: AsyncClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.config.settings.media_root", str(tmp_path))
    
    files = [
        ("files", ("test.jpg", b"fake jpeg data", "image/jpeg")),
    ]
    resp = await admin_client.post("/api/admin/storage/upload", data={"path": ""}, files=files)
    assert resp.status_code == status.HTTP_201_CREATED
    assert (tmp_path / "test.jpg").exists()

@pytest.mark.asyncio
async def test_storage_mkdir(admin_client: AsyncClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.config.settings.media_root", str(tmp_path))
    
    resp = await admin_client.post("/api/admin/storage/mkdir", json={"path": "new_dir"})
    assert resp.status_code == status.HTTP_200_OK
    assert (tmp_path / "new_dir").is_dir()

@pytest.mark.asyncio
async def test_storage_rm(admin_client: AsyncClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.config.settings.media_root", str(tmp_path))
    
    target = tmp_path / "to_delete.txt"
    target.write_text("delete me")
    
    resp = await admin_client.delete("/api/admin/storage/rm", params={"path": "to_delete.txt"})
    assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert not target.exists()

@pytest.mark.asyncio
async def test_path_traversal_protection(admin_client: AsyncClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.config.settings.media_root", str(tmp_path))
    
    resp = await admin_client.get("/api/admin/storage/ls", params={"path": "../../"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "Path traversal" in resp.json()["detail"]
