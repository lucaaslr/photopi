"use client";

/**
 * Takeout import widget for the admin dashboard.
 *
 * Lets an admin upload Google Takeout .zip / .tgz archives into a staging
 * folder on the HDD, then kicks off a background job that extracts each
 * archive into the canonical "Google Photos/" library, deletes the
 * processed archive, and triggers a reindex.
 *
 * Polls /admin/takeout/status while a job is active.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Archive,
  Loader2,
  Play,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import {
  api,
  ApiError,
  type IndexJob,
  type StagedArchive,
} from "@/lib/api";
import { formatBytes, cn } from "@/lib/utils";

const ARCHIVE_EXTS = /\.(zip|tgz|tar\.gz|tar)$/i;
const RUNNING_STATES = new Set(["pending", "running"]);

function isArchive(file: File): boolean {
  return ARCHIVE_EXTS.test(file.name);
}

export function TakeoutImporter() {
  const [staged, setStaged] = useState<StagedArchive[]>([]);
  const [job, setJob] = useState<IndexJob | null>(null);
  const [uploads, setUploads] = useState<
    { id: number; name: string; size: number; loaded: number; error?: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const uploadIdRef = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([
        api.takeoutStaged(),
        api.takeoutStatus(),
      ]);
      setStaged(s.items);
      setJob(j);
    } catch {
      /* swallow - keep previous state */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll every 2s while a takeout job is active.
  useEffect(() => {
    const active = job ? RUNNING_STATES.has(job.status) : false;
    if (active && !pollRef.current) {
      pollRef.current = setInterval(refresh, 2000);
    } else if (!active && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [job?.status, refresh]);

  const handleFiles = async (files: FileList | File[]) => {
    setError(null);
    const list = Array.from(files).filter(isArchive);
    if (list.length === 0) {
      setError("Pick a .zip, .tgz, .tar.gz or .tar file.");
      return;
    }

    // Add a row for each file so the user sees individual progress.
    const rows = list.map((f) => ({
      id: ++uploadIdRef.current,
      name: f.name,
      size: f.size,
      loaded: 0,
    }));
    setUploads((u) => [...u, ...rows]);

    for (let i = 0; i < list.length; i++) {
      const file = list[i];
      const row = rows[i];
      try {
        await api.takeoutUpload([file], (loaded, total) => {
          setUploads((u) =>
            u.map((r) =>
              r.id === row.id
                ? { ...r, loaded, size: total || r.size }
                : r
            )
          );
        });
      } catch (err) {
        setUploads((u) =>
          u.map((r) =>
            r.id === row.id
              ? {
                  ...r,
                  error:
                    err instanceof ApiError
                      ? err.message
                      : "Upload failed",
                }
              : r
          )
        );
      }
    }
    await refresh();
    // Clear successfully-completed rows after a short delay.
    setTimeout(() => {
      setUploads((u) => u.filter((r) => r.error));
    }, 1500);
  };

  const onDeleteStaged = async (name: string) => {
    if (!window.confirm(`Delete ${name} from staging?`)) return;
    try {
      await api.takeoutDeleteStaged(name);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete");
    }
  };

  const onStart = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.takeoutImport({ delete_on_success: true, trigger_index: true });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start import");
    } finally {
      setBusy(false);
    }
  };

  const pct = job ? Math.round(job.progress * 100) : 0;
  const isRunning = job ? RUNNING_STATES.has(job.status) : false;

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Takeout import</h2>
        {job && (
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium capitalize",
              job.status === "running" && "bg-accent/15 text-accent",
              job.status === "completed" && "bg-emerald-500/15 text-emerald-500",
              job.status === "failed" && "bg-danger/15 text-danger",
              job.status === "cancelled" && "bg-elevated text-muted",
              job.status === "pending" && "bg-elevated text-muted"
            )}
          >
            {job.status}
          </span>
        )}
      </div>

      {/* In-flight uploads */}
      {uploads.length > 0 && (
        <div className="mb-4 space-y-2">
          {uploads.map((u) => {
            const upct = u.size > 0 ? Math.round((u.loaded / u.size) * 100) : 0;
            return (
              <div key={u.id} className="rounded-lg bg-elevated p-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="truncate">{u.name}</span>
                  <span className={cn("ml-2 shrink-0", u.error && "text-danger")}>
                    {u.error
                      ? u.error
                      : upct >= 100
                        ? "uploaded"
                        : `${upct}%`}
                  </span>
                </div>
                {!u.error && (
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-bg">
                    <div
                      className="h-full bg-accent transition-all"
                      style={{ width: `${upct}%` }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Active job progress */}
      {isRunning && job && (
        <div className="mb-4">
          <div className="mb-1.5 flex justify-between text-xs text-muted">
            <span>
              {job.processed_files.toLocaleString()} /{" "}
              {job.total_files.toLocaleString()} archives
            </span>
            <span>{pct}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-elevated">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          {job.current_path && (
            <p className="mt-1.5 truncate text-xs text-muted">
              {job.current_path}
            </p>
          )}
          {job.indexed_files > 0 && (
            <p className="mt-1 text-xs text-muted">
              {job.indexed_files.toLocaleString()} file(s) extracted so far
            </p>
          )}
        </div>
      )}

      {job && !isRunning && job.message && (
        <p className="mb-4 rounded-lg bg-elevated px-3 py-2 text-xs text-muted">
          {job.message}
        </p>
      )}

      {/* Staged archives */}
      <div className="mb-4">
        <p className="mb-2 text-xs font-medium text-muted">
          Staged ({staged.length})
        </p>
        {staged.length === 0 ? (
          <p className="rounded-lg bg-elevated px-3 py-4 text-center text-xs text-muted">
            No archives waiting. Upload one to get started.
          </p>
        ) : (
          <ul className="space-y-1">
            {staged.map((a) => (
              <li
                key={a.name}
                className="flex items-center gap-3 rounded-lg bg-elevated px-3 py-2 text-sm"
              >
                <Archive size={15} className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate">{a.name}</span>
                <span className="shrink-0 text-xs text-muted">
                  {formatBytes(a.size)}
                </span>
                <button
                  onClick={() => onDeleteStaged(a.name)}
                  disabled={isRunning}
                  className="shrink-0 rounded p-1 text-muted hover:text-danger disabled:opacity-50"
                  title="Remove from staging"
                  aria-label={`Remove ${a.name}`}
                >
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <p className="mb-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}

      {/* Actions */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".zip,.tgz,.tar.gz,.tar"
        className="hidden"
        onChange={(e) => {
          if (e.target.files) void handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={isRunning}
        >
          <Upload size={15} />
          Upload archives
        </Button>
        <Button
          onClick={onStart}
          disabled={busy || isRunning || staged.length === 0}
        >
          {busy || isRunning ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Play size={15} />
          )}
          Import {staged.length > 0 ? `(${staged.length})` : ""}
        </Button>
      </div>

      <p className="mt-3 text-xs text-muted">
        Archives are extracted into <code>Google Photos/</code>, the original
        .zip is deleted on success, and a reindex starts automatically.
      </p>
    </Card>
  );
}
