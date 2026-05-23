"use client";

import { useEffect, useState, useRef } from "react";
import { Folder, File, ArrowLeft, Trash2, Upload, Plus, MoreVertical, HardDrive, Archive } from "lucide-react";
import { api, StorageItem, StorageList } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { formatBytes } from "@/lib/utils";
import { cn } from "@/lib/utils";

export function StorageExplorer() {
  const [data, setData] = useState<StorageList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = async (path: string = "") => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.storageList(path);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load storage");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("");
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length || !data) return;

    setUploading(true);
    try {
      await api.storageUpload(data.current_path, files);
      void load(data.current_path);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (path: string) => {
    if (!confirm(`Are you sure you want to delete ${path}?`)) return;
    try {
      await api.storageDelete(path);
      void load(data?.current_path || "");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleMkdir = async () => {
    const name = prompt("Enter directory name:");
    if (!name || !data) return;
    try {
      const newPath = data.current_path ? `${data.current_path}/${name}` : name;
      await api.storageMkdir(newPath);
      void load(data.current_path);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create directory");
    }
  };

  const handleExtract = async (path: string) => {
    if (!confirm(`Extract ${path}? Contents will be placed in the current folder.`)) return;
    setLoading(true);
    try {
      await api.storageExtract(path);
      void load(data?.current_path || "");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setLoading(false);
    }
  };

  const isArchive = (name: string) => {
    const n = name.toLowerCase();
    return n.endsWith(".zip") || n.endsWith(".tar") || n.endsWith(".tgz") || n.endsWith(".gz");
  };

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 overflow-hidden">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => load(data?.parent_path || "")}
            disabled={!data?.current_path}
          >
            <ArrowLeft size={18} />
          </Button>
          <div className="flex items-center gap-1 overflow-hidden">
            <HardDrive size={18} className="text-muted shrink-0" />
            <span className="text-sm font-medium truncate">
              {data?.current_path || "Media Root"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleMkdir}>
            <Plus size={16} className="mr-1" /> New Folder
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <Spinner size="sm" className="mr-1" />
            ) : (
              <Upload size={16} className="mr-1" />
            )}
            Upload
          </Button>
          <input
            type="file"
            multiple
            hidden
            ref={fileInputRef}
            onChange={handleUpload}
          />
        </div>
      </div>

      {error && <div className="text-sm text-error bg-error/10 p-3 rounded">{error}</div>}

      <Card className="divide-y divide-border overflow-hidden">
        {data?.items.length === 0 && (
          <div className="p-8 text-center text-muted text-sm">This directory is empty.</div>
        )}
        {data?.items.map((item) => (
          <div
            key={item.path}
            className="group flex items-center justify-between p-3 hover:bg-elevated transition-colors"
          >
            <div
              className="flex flex-1 items-center gap-3 cursor-pointer overflow-hidden"
              onClick={() => (item.is_dir ? load(item.path) : null)}
            >
              {item.is_dir ? (
                <Folder size={20} className="text-accent shrink-0" />
              ) : (
                <File size={20} className="text-muted shrink-0" />
              )}
              <div className="flex flex-col overflow-hidden">
                <span className="text-sm font-medium truncate">{item.name}</span>
                {!item.is_dir && (
                  <span className="text-[10px] text-muted">
                    {formatBytes(item.size || 0)} • {new Date(item.mtime).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {isArchive(item.name) && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => handleExtract(item.path)}
                  title="Extract archive"
                  className="text-accent"
                >
                  <Archive size={16} />
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => handleDelete(item.path)}
                className="text-muted hover:text-error"
              >
                <Trash2 size={16} />
              </Button>
            </div>
          </div>
        ))}
      </Card>
      
      <p className="text-[10px] text-muted italic">
        Tip: After uploading or moving files, start a new indexing job to see them in your gallery.
      </p>
    </div>
  );
}
