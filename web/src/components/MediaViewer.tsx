"use client";

/**
 * MediaViewer
 *
 * Full-screen lightbox for browsing a media list. Shows the preview-size
 * image (or the original video), keyboard navigation, and a collapsible
 * metadata / EXIF panel. Detailed metadata is fetched lazily per item.
 */
import { useCallback, useEffect, useState } from "react";
import {
  X,
  ChevronLeft,
  ChevronRight,
  Heart,
  Info,
  Download,
  MapPin,
  Trash2,
  Loader2,
} from "lucide-react";
import { api, mediaUrl, type MediaDetail, type MediaItem } from "@/lib/api";
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  cn,
} from "@/lib/utils";

interface MediaViewerProps {
  items: MediaItem[];
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
  /** Called after a favourite toggle so parent lists can stay in sync. */
  onPatch?: (id: number, patch: Partial<MediaItem>) => void;
  /** When provided, a delete (remove-from-index) action is shown. */
  onDelete?: (id: number) => void;
  /** Hide edit actions for read-only / guest views. */
  readOnly?: boolean;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="text-right text-fg break-words">{value}</span>
    </div>
  );
}

export function MediaViewer({
  items,
  index,
  onClose,
  onIndexChange,
  onPatch,
  onDelete,
  readOnly = false,
}: MediaViewerProps) {
  const current = items[index];
  const [detail, setDetail] = useState<MediaDetail | null>(null);
  const [showInfo, setShowInfo] = useState(false);
  const [busy, setBusy] = useState(false);

  const hasPrev = index > 0;
  const hasNext = index < items.length - 1;

  // Lazily load full metadata for the visible item.
  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    if (!current) return;
    api
      .media(current.id)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        /* metadata panel simply stays minimal */
      });
    return () => {
      cancelled = true;
    };
  }, [current]);

  const go = useCallback(
    (delta: number) => {
      const next = index + delta;
      if (next >= 0 && next < items.length) onIndexChange(next);
    },
    [index, items.length, onIndexChange]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
      else if (e.key.toLowerCase() === "i") setShowInfo((s) => !s);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [go, onClose]);

  if (!current) return null;

  const toggleFavorite = async () => {
    if (readOnly || busy) return;
    setBusy(true);
    try {
      const updated = await api.updateMedia(current.id, {
        favorite: !current.favorite,
      });
      onPatch?.(current.id, { favorite: updated.favorite });
      setDetail(updated);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (readOnly || busy || !onDelete) return;
    if (!window.confirm("Remove this item from the library index? The original file on the HDD is kept.")) {
      return;
    }
    setBusy(true);
    try {
      await api.deleteMedia(current.id);
      onDelete(current.id);
      if (items.length <= 1) onClose();
      else if (hasNext) onIndexChange(index);
      else go(-1);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex bg-black animate-fade-in">
      {/* --- Stage --- */}
      <div className="relative flex flex-1 items-center justify-center">
        {/* Top controls */}
        <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-1 bg-gradient-to-b from-black/70 to-transparent p-3">
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-2 text-white/90 transition hover:bg-white/10"
          >
            <X size={20} />
          </button>
          <span className="ml-1 truncate text-sm text-white/80">
            {current.filename}
          </span>
          <div className="ml-auto flex items-center gap-1">
            {!readOnly && (
              <button
                onClick={toggleFavorite}
                disabled={busy}
                aria-label="Toggle favourite"
                className="rounded-lg p-2 text-white/90 transition hover:bg-white/10"
              >
                <Heart
                  size={20}
                  className={current.favorite ? "fill-red-500 text-red-500" : ""}
                />
              </button>
            )}
            <a
              href={mediaUrl(current.file_url)}
              download={current.filename}
              aria-label="Download original"
              className="rounded-lg p-2 text-white/90 transition hover:bg-white/10"
            >
              <Download size={20} />
            </a>
            {!readOnly && onDelete && (
              <button
                onClick={handleDelete}
                disabled={busy}
                aria-label="Remove from index"
                className="rounded-lg p-2 text-white/90 transition hover:bg-white/10"
              >
                <Trash2 size={20} />
              </button>
            )}
            <button
              onClick={() => setShowInfo((s) => !s)}
              aria-label="Toggle info"
              className={cn(
                "rounded-lg p-2 transition hover:bg-white/10",
                showInfo ? "text-accent" : "text-white/90"
              )}
            >
              <Info size={20} />
            </button>
          </div>
        </div>

        {/* Prev / next */}
        {hasPrev && (
          <button
            onClick={() => go(-1)}
            aria-label="Previous"
            className="absolute left-2 z-10 rounded-full bg-black/40 p-2 text-white transition hover:bg-black/70"
          >
            <ChevronLeft size={26} />
          </button>
        )}
        {hasNext && (
          <button
            onClick={() => go(1)}
            aria-label="Next"
            className="absolute right-2 z-10 rounded-full bg-black/40 p-2 text-white transition hover:bg-black/70"
          >
            <ChevronRight size={26} />
          </button>
        )}

        {/* The media itself */}
        {current.media_type === "video" ? (
          <video
            key={current.id}
            src={mediaUrl(current.file_url)}
            controls
            autoPlay
            className="max-h-full max-w-full"
          />
        ) : (
          <img
            key={current.id}
            src={mediaUrl(current.preview_url)}
            alt={current.filename}
            className="max-h-full max-w-full object-contain"
          />
        )}
      </div>

      {/* --- Info panel --- */}
      {showInfo && (
        <aside className="w-72 shrink-0 overflow-y-auto border-l border-border bg-surface p-5 text-fg">
          <h3 className="mb-3 text-sm font-semibold">Details</h3>
          {!detail ? (
            <div className="flex items-center gap-2 text-sm text-muted">
              <Loader2 size={14} className="animate-spin" /> Loading…
            </div>
          ) : (
            <div className="divide-y divide-border">
              <Row label="File" value={detail.filename} />
              <Row label="Taken" value={formatDateTime(detail.taken_at)} />
              <Row
                label="Capture source"
                value={detail.taken_source}
              />
              {detail.width && detail.height && (
                <Row
                  label="Dimensions"
                  value={`${detail.width} × ${detail.height}`}
                />
              )}
              {detail.media_type === "video" && detail.duration && (
                <Row
                  label="Duration"
                  value={formatDuration(detail.duration)}
                />
              )}
              <Row label="Size" value={formatBytes(detail.size_bytes)} />
              <Row label="Type" value={detail.mime_type} />
              {detail.camera_make && (
                <Row
                  label="Camera"
                  value={`${detail.camera_make} ${detail.camera_model ?? ""}`.trim()}
                />
              )}
              {detail.description && (
                <Row label="Description" value={detail.description} />
              )}
              {detail.is_duplicate && (
                <Row
                  label="Duplicate of"
                  value={`#${detail.duplicate_of}`}
                />
              )}
              <Row label="Path" value={detail.rel_path} />
              <Row label="Indexed" value={formatDateTime(detail.indexed_at)} />
            </div>
          )}

          {detail?.maps_url && detail.lat != null && detail.lon != null && (
            <a
              href={detail.maps_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 flex items-center gap-2 rounded-lg border border-border bg-elevated px-3 py-2 text-sm transition hover:bg-surface"
            >
              <MapPin size={15} className="text-accent" />
              {detail.lat.toFixed(5)}, {detail.lon.toFixed(5)}
            </a>
          )}
        </aside>
      )}
    </div>
  );
}
