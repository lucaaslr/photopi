"use client";

/**
 * Search page - filename, date range, type and camera filters.
 *
 * Filters are applied on submit (not per keystroke) to avoid hammering the
 * Pi with a request on every character.
 */
import { useCallback, useEffect, useState } from "react";
import { Search as SearchIcon, SlidersHorizontal } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Gallery } from "@/components/Gallery";
import { MediaViewer } from "@/components/MediaViewer";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useRequireAuth } from "@/lib/auth";
import { api, type CameraStat } from "@/lib/api";
import { useInfiniteMedia } from "@/hooks/useInfiniteMedia";

interface Filters {
  q: string;
  media_type: "" | "image" | "video";
  camera_model: string;
  favorite: boolean;
  date_from: string;
  date_to: string;
}

const EMPTY: Filters = {
  q: "",
  media_type: "",
  camera_model: "",
  favorite: false,
  date_from: "",
  date_to: "",
};

export default function SearchPage() {
  const { loading: authLoading } = useRequireAuth();

  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);
  const [showFilters, setShowFilters] = useState(false);
  const [cameras, setCameras] = useState<CameraStat[]>([]);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    api.cameras().then(setCameras).catch(() => setCameras([]));
  }, []);

  const fetcher = useCallback(
    (cursor: string | undefined) =>
      api.search({
        cursor,
        limit: 60,
        q: applied.q || undefined,
        media_type: applied.media_type || undefined,
        camera_model: applied.camera_model || undefined,
        favorite: applied.favorite || undefined,
        date_from: applied.date_from || undefined,
        date_to: applied.date_to || undefined,
      }),
    [applied]
  );

  const {
    items,
    loading,
    loadingMore,
    error,
    hasMore,
    sentinelRef,
    patchItem,
    removeItem,
  } = useInfiniteMedia(fetcher, [applied]);

  const apply = () => {
    setApplied(draft);
    setSearched(true);
  };

  const reset = () => {
    setDraft(EMPTY);
    setApplied(EMPTY);
    setSearched(false);
  };

  if (authLoading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-16 sm:pb-0">
      <Navbar />

      <main className="mx-auto max-w-6xl px-3 py-5 sm:px-4">
        {/* Search bar */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <SearchIcon
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <Input
              placeholder="Search by filename, path or description…"
              className="pl-9"
              value={draft.q}
              onChange={(e) => setDraft({ ...draft, q: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && apply()}
            />
          </div>
          <Button
            variant="secondary"
            size="icon"
            onClick={() => setShowFilters((s) => !s)}
            aria-label="Toggle filters"
          >
            <SlidersHorizontal size={16} />
          </Button>
          <Button onClick={apply}>Search</Button>
        </div>

        {/* Advanced filters */}
        {showFilters && (
          <div className="mt-3 grid gap-3 rounded-xl border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-sm">
              <span className="mb-1 block text-muted">Type</span>
              <select
                className="h-10 w-full rounded-lg border border-border bg-surface px-2 text-sm"
                value={draft.media_type}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    media_type: e.target.value as Filters["media_type"],
                  })
                }
              >
                <option value="">Any</option>
                <option value="image">Photos</option>
                <option value="video">Videos</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">Camera</span>
              <select
                className="h-10 w-full rounded-lg border border-border bg-surface px-2 text-sm"
                value={draft.camera_model}
                onChange={(e) =>
                  setDraft({ ...draft, camera_model: e.target.value })
                }
              >
                <option value="">Any</option>
                {cameras.map((c) => (
                  <option key={c.model} value={c.model}>
                    {c.model} ({c.count})
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">From</span>
              <Input
                type="date"
                value={draft.date_from}
                onChange={(e) =>
                  setDraft({ ...draft, date_from: e.target.value })
                }
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">To</span>
              <Input
                type="date"
                value={draft.date_to}
                onChange={(e) =>
                  setDraft({ ...draft, date_to: e.target.value })
                }
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.favorite}
                onChange={(e) =>
                  setDraft({ ...draft, favorite: e.target.checked })
                }
                className="h-4 w-4 accent-accent"
              />
              Favourites only
            </label>
            <div className="flex items-end">
              <Button variant="ghost" size="sm" onClick={reset}>
                Clear filters
              </Button>
            </div>
          </div>
        )}

        {/* Results */}
        <div className="mt-5">
          {!searched ? (
            <p className="py-24 text-center text-sm text-muted">
              Enter a query or open the filters to search your library.
            </p>
          ) : loading ? (
            <div className="grid place-items-center py-24">
              <Spinner className="h-8 w-8" />
            </div>
          ) : error ? (
            <p className="py-24 text-center text-sm text-muted">{error}</p>
          ) : items.length === 0 ? (
            <p className="py-24 text-center text-sm text-muted">
              No media matched your search.
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-muted">
                {items.length}
                {hasMore ? "+" : ""} result
                {items.length === 1 ? "" : "s"}
              </p>
              <Gallery
                items={items}
                grouped={false}
                onSelect={(i) => setViewerIndex(i)}
              />
              <div ref={sentinelRef} className="h-10" />
              {loadingMore && (
                <div className="grid place-items-center py-6">
                  <Spinner />
                </div>
              )}
            </>
          )}
        </div>
      </main>

      {viewerIndex !== null && (
        <MediaViewer
          items={items}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
          onPatch={patchItem}
          onDelete={removeItem}
        />
      )}
    </div>
  );
}
