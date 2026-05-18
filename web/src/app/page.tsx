"use client";

/**
 * Home page - the reverse-chronological photo timeline.
 *
 * Media is loaded a page at a time via keyset pagination and grouped into
 * month sections. Selecting a thumbnail opens the full-screen viewer.
 */
import { useCallback, useState } from "react";
import { ImageOff, RefreshCw } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Gallery } from "@/components/Gallery";
import { MediaViewer } from "@/components/MediaViewer";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { useRequireAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { useInfiniteMedia } from "@/hooks/useInfiniteMedia";

export default function TimelinePage() {
  const { loading: authLoading } = useRequireAuth();
  const [filter, setFilter] = useState<"all" | "image" | "video">("all");
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  const fetcher = useCallback(
    (cursor: string | undefined) =>
      api.timeline({
        cursor,
        limit: 60,
        media_type: filter === "all" ? undefined : filter,
      }),
    [filter]
  );

  const {
    items,
    loading,
    loadingMore,
    error,
    hasMore,
    sentinelRef,
    reload,
    patchItem,
    removeItem,
  } = useInfiniteMedia(fetcher, [filter]);

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
        {/* Filter pills */}
        <div className="mb-5 flex items-center gap-2">
          {(["all", "image", "video"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={
                "rounded-full px-3 py-1 text-sm capitalize transition " +
                (filter === f
                  ? "bg-accent text-accent-fg"
                  : "bg-elevated text-muted hover:text-fg")
              }
            >
              {f === "image" ? "Photos" : f === "video" ? "Videos" : "All"}
            </button>
          ))}
          <button
            onClick={reload}
            aria-label="Refresh"
            className="ml-auto rounded-lg p-2 text-muted transition hover:bg-elevated hover:text-fg"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        {loading ? (
          <div className="grid place-items-center py-24">
            <Spinner className="h-8 w-8" />
          </div>
        ) : error ? (
          <div className="grid place-items-center gap-3 py-24 text-center">
            <p className="text-sm text-muted">{error}</p>
            <Button variant="secondary" size="sm" onClick={reload}>
              Try again
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="grid place-items-center gap-3 py-24 text-center">
            <ImageOff size={40} className="text-muted" />
            <div>
              <p className="font-medium">Your library is empty</p>
              <p className="text-sm text-muted">
                Run an index from the Admin page to scan your Takeout export.
              </p>
            </div>
          </div>
        ) : (
          <>
            <Gallery
              items={items}
              onSelect={(i) => setViewerIndex(i)}
            />
            <div ref={sentinelRef} className="h-10" />
            {loadingMore && (
              <div className="grid place-items-center py-6">
                <Spinner />
              </div>
            )}
            {!hasMore && (
              <p className="py-6 text-center text-xs text-muted">
                {items.length} item{items.length === 1 ? "" : "s"} · end of
                library
              </p>
            )}
          </>
        )}
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
