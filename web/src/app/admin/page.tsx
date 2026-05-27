"use client";

/**
 * Admin dashboard.
 *
 * Surfaces library statistics and drives the indexing job. While a job is
 * running the page polls the status endpoint so progress updates live
 * without a manual refresh.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Play,
  Pause,
  Square,
  RotateCw,
  HardDrive,
  Image as ImageIcon,
  Film,
  FolderOpen,
  Database,
  KeyRound,
  Loader2,
} from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Dialog } from "@/components/ui/Dialog";
import { Spinner } from "@/components/ui/Spinner";
import { useRequireAuth } from "@/lib/auth";
import { api, type Dashboard, type IndexJob } from "@/lib/api";
import { formatBytes, formatDateTime, cn } from "@/lib/utils";
import { StorageExplorer } from "@/components/StorageExplorer";
import { TakeoutImporter } from "@/components/TakeoutImporter";

const RUNNING_STATES = new Set(["pending", "running", "paused"]);

function StatTile({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ImageIcon;
  label: string;
  value: string;
}) {
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-elevated text-accent">
        <Icon size={18} />
      </span>
      <div className="min-w-0">
        <p className="truncate text-lg font-semibold">{value}</p>
        <p className="text-xs text-muted">{label}</p>
      </div>
    </Card>
  );
}

function JobPanel({
  job,
  running,
  onAction,
  busy,
}: {
  job: IndexJob | null;
  running: boolean;
  onAction: (action: "start" | "pause" | "resume" | "cancel") => void;
  busy: boolean;
}) {
  const pct = job ? Math.round(job.progress * 100) : 0;
  const paused = job?.status === "paused";

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Library indexing</h2>
        {job && (
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium capitalize",
              job.status === "running" && "bg-accent/15 text-accent",
              job.status === "paused" && "bg-amber-500/15 text-amber-500",
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

      {job && RUNNING_STATES.has(job.status) && (
        <div className="mb-4">
          <div className="mb-1.5 flex justify-between text-xs text-muted">
            <span>
              {job.processed_files.toLocaleString()} /{" "}
              {job.total_files.toLocaleString()} files
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
        </div>
      )}

      {job && !RUNNING_STATES.has(job.status) && (
        <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
          <Stat label="Indexed" value={job.indexed_files} />
          <Stat label="Updated" value={job.updated_files} />
          <Stat label="Skipped" value={job.skipped_files} />
          <Stat label="Failed" value={job.failed_files} />
        </div>
      )}

      {job?.message && (
        <p className="mb-4 rounded-lg bg-elevated px-3 py-2 text-xs text-muted">
          {job.message}
        </p>
      )}

      {job?.finished_at && !RUNNING_STATES.has(job.status) && (
        <p className="mb-4 text-xs text-muted">
          Finished {formatDateTime(job.finished_at)}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {!running ? (
          <Button onClick={() => onAction("start")} disabled={busy}>
            {busy ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Play size={15} />
            )}
            {job && !RUNNING_STATES.has(job.status)
              ? "Re-index library"
              : "Start indexing"}
          </Button>
        ) : (
          <>
            {paused ? (
              <Button onClick={() => onAction("resume")} disabled={busy}>
                <Play size={15} />
                Resume
              </Button>
            ) : (
              <Button
                variant="secondary"
                onClick={() => onAction("pause")}
                disabled={busy}
              >
                <Pause size={15} />
                Pause
              </Button>
            )}
            <Button
              variant="danger"
              onClick={() => onAction("cancel")}
              disabled={busy}
            >
              <Square size={15} />
              Cancel
            </Button>
          </>
        )}
      </div>

      <p className="mt-3 text-xs text-muted">
        Indexing scans your Takeout export incrementally - already-indexed
        files are skipped, so re-running after adding photos is cheap.
      </p>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="font-semibold">{value.toLocaleString()}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
}

export default function AdminPage() {
  const { loading: authLoading } = useRequireAuth(true);

  const [data, setData] = useState<Dashboard | null>(null);
  const [busy, setBusy] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await api.dashboard());
    } catch {
      /* keep last good data */
    }
  }, []);

  // Initial load.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll every 2s while a job is active; stop when it settles.
  useEffect(() => {
    const active = data?.job_running ?? false;
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
  }, [data?.job_running, refresh]);

  const handleAction = async (
    action: "start" | "pause" | "resume" | "cancel"
  ) => {
    setBusy(true);
    try {
      if (action === "start") await api.startIndex();
      else if (action === "pause") await api.pauseIndex();
      else if (action === "resume") await api.resumeIndex();
      else if (action === "cancel") await api.cancelIndex();
      await refresh();
    } catch (err) {
      window.alert(
        err instanceof Error ? err.message : "The action could not be completed."
      );
    } finally {
      setBusy(false);
    }
  };

  if (authLoading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  const s = data?.stats;

  return (
    <div className="min-h-screen pb-16 sm:pb-0">
      <Navbar />

      <main className="mx-auto max-w-6xl space-y-5 px-3 py-5 sm:px-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">Admin</h1>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setPwOpen(true)}>
              <KeyRound size={15} />
              Password
            </Button>
            <Button variant="secondary" size="sm" onClick={refresh}>
              <RotateCw size={15} />
              Refresh
            </Button>
          </div>
        </div>

        {!data ? (
          <div className="grid place-items-center py-24">
            <Spinner className="h-8 w-8" />
          </div>
        ) : (
          <>
            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <StatTile
                icon={ImageIcon}
                label="Photos"
                value={(s?.image_count ?? 0).toLocaleString()}
              />
              <StatTile
                icon={Film}
                label="Videos"
                value={(s?.video_count ?? 0).toLocaleString()}
              />
              <StatTile
                icon={FolderOpen}
                label="Albums"
                value={(s?.album_count ?? 0).toLocaleString()}
              />
              <StatTile
                icon={HardDrive}
                label="Library size"
                value={formatBytes(s?.library_bytes ?? 0)}
              />
              <StatTile
                icon={Database}
                label="Thumbnail cache"
                value={formatBytes(s?.thumbnail_bytes ?? 0)}
              />
              <StatTile
                icon={Database}
                label="Database"
                value={formatBytes(s?.database_bytes ?? 0)}
              />
              <StatTile
                icon={HardDrive}
                label="Free on data volume"
                value={formatBytes(s?.data_free_bytes ?? 0)}
              />
              <StatTile
                icon={HardDrive}
                label="Free on photo HDD"
                value={formatBytes(s?.media_free_bytes ?? 0)}
              />
            </div>

            {/* Indexing */}
            <JobPanel
              job={data.job}
              running={data.job_running}
              onAction={handleAction}
              busy={busy}
            />

            {/* Takeout import */}
            <TakeoutImporter />

            {/* Storage Manager */}
            <div className="space-y-3">
              <h2 className="text-sm font-semibold">Storage manager</h2>
              <StorageExplorer />
            </div>

            {/* Date span + cameras */}
            <div className="grid gap-3 lg:grid-cols-2">
              <Card>
                <h2 className="mb-3 text-sm font-semibold">Library span</h2>
                {s?.oldest && s?.newest ? (
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted">Oldest photo</span>
                      <span>{formatDateTime(s.oldest)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Newest photo</span>
                      <span>{formatDateTime(s.newest)}</span>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted">
                    No media indexed yet.
                  </p>
                )}
              </Card>

              <Card>
                <h2 className="mb-3 text-sm font-semibold">Top cameras</h2>
                {data.cameras.length === 0 ? (
                  <p className="text-sm text-muted">
                    No camera metadata found.
                  </p>
                ) : (
                  <ul className="space-y-1.5 text-sm">
                    {data.cameras.slice(0, 8).map((c) => (
                      <li
                        key={c.model}
                        className="flex justify-between gap-4"
                      >
                        <span className="truncate">{c.model}</span>
                        <span className="shrink-0 text-muted">
                          {c.count.toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </>
        )}
      </main>

      <ChangePasswordDialog open={pwOpen} onClose={() => setPwOpen(false)} />
    </div>
  );
}

// --- Change password dialog ----------------------------------------------
function ChangePasswordDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    if (next.length < 6) {
      setError("New password must be at least 6 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
      setTimeout(() => {
        setDone(false);
        onClose();
      }, 1500);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not change the password."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Change password" wide>
      {done ? (
        <p className="py-4 text-center text-sm text-emerald-500">
          Password updated.
        </p>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Current password
            </label>
            <Input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              New password
            </label>
            <Input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Confirm new password
            </label>
            <Input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          {error && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy || !current || !next}>
              {busy && <Loader2 size={15} className="animate-spin" />}
              Update
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
