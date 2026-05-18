"use client";

/**
 * Gallery
 *
 * A responsive thumbnail grid grouped into month sections. Off-screen rows
 * are culled by CSS `content-visibility` (see globals.css) so scrolling
 * stays smooth on a Raspberry Pi without any JS windowing library.
 */
import { useState } from "react";
import { Play, Star, Heart } from "lucide-react";
import type { MediaItem } from "@/lib/api";
import { mediaUrl } from "@/lib/api";
import { formatDuration, groupByMonth } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface GalleryProps {
  items: MediaItem[];
  onSelect: (index: number) => void;
  /** When false, items are not split into month headings (e.g. search). */
  grouped?: boolean;
  /** Optional selection state for album-building / multi-select. */
  selectedIds?: Set<number>;
  onToggleSelect?: (id: number) => void;
}

function Thumb({
  item,
  onClick,
  selected,
  onToggleSelect,
}: {
  item: MediaItem;
  onClick: () => void;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const pending = item.thumb_status !== "done";

  return (
    <div
      className={cn(
        "group relative aspect-square cursor-pointer overflow-hidden rounded-lg bg-elevated",
        selected && "ring-2 ring-accent ring-offset-2 ring-offset-bg"
      )}
      onClick={onClick}
    >
      {pending || failed ? (
        <div className="flex h-full w-full items-center justify-center text-[10px] text-muted">
          {failed ? "Unavailable" : "Processing…"}
        </div>
      ) : (
        <img
          src={mediaUrl(item.thumb_url)}
          alt={item.filename}
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={cn(
            "h-full w-full object-cover thumb-img",
            loaded && "loaded"
          )}
        />
      )}

      {/* Video duration / play badge */}
      {item.media_type === "video" && (
        <span className="absolute bottom-1.5 right-1.5 flex items-center gap-1 rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-medium text-white">
          <Play size={9} className="fill-white" />
          {formatDuration(item.duration) || "Video"}
        </span>
      )}

      {/* Favourite marker */}
      {item.favorite && (
        <Heart
          size={15}
          className="absolute left-1.5 top-1.5 fill-white text-white drop-shadow"
        />
      )}

      {/* Multi-select checkbox (appears on hover or when selecting) */}
      {onToggleSelect && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect(item.id);
          }}
          aria-label={selected ? "Deselect" : "Select"}
          className={cn(
            "absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full border transition",
            selected
              ? "border-accent bg-accent text-accent-fg"
              : "border-white/80 bg-black/40 text-transparent opacity-0 group-hover:opacity-100"
          )}
        >
          <Star size={11} className={selected ? "fill-current" : ""} />
        </button>
      )}
    </div>
  );
}

export function Gallery({
  items,
  onSelect,
  grouped = true,
  selectedIds,
  onToggleSelect,
}: GalleryProps) {
  // A flat index map lets a section thumbnail open the right viewer slide.
  const indexOf = new Map(items.map((m, i) => [m.id, i]));

  const gridClass =
    "grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8";

  if (!grouped) {
    return (
      <div className={gridClass}>
        {items.map((item) => (
          <Thumb
            key={item.id}
            item={item}
            onClick={() => onSelect(indexOf.get(item.id) ?? 0)}
            selected={selectedIds?.has(item.id)}
            onToggleSelect={onToggleSelect}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-7">
      {groupByMonth(items).map((group) => (
        <section key={group.key} className="cv-auto">
          <h2 className="mb-2.5 text-sm font-semibold text-fg">
            {group.label}
            <span className="ml-2 font-normal text-muted">
              {group.items.length}
            </span>
          </h2>
          <div className={gridClass}>
            {group.items.map((item) => (
              <Thumb
                key={item.id}
                item={item}
                onClick={() => onSelect(indexOf.get(item.id) ?? 0)}
                selected={selectedIds?.has(item.id)}
                onToggleSelect={onToggleSelect}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
