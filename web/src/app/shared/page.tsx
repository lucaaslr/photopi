"use client";

/**
 * Public shared-album view.
 *
 * Reachable without signing in via /shared/?t=<token>. The page is part of
 * a static export, so the token is read from the query string on the
 * client and the album is fetched through the unauthenticated
 * /albums/shared endpoint.
 */
import { useCallback, useEffect, useState } from "react";
import { Images } from "lucide-react";
import { Gallery } from "@/components/Gallery";
import { MediaViewer } from "@/components/MediaViewer";
import { Spinner } from "@/components/ui/Spinner";
import { api, type AlbumDetail } from "@/lib/api";
import { useInfiniteMedia } from "@/hooks/useInfiniteMedia";

export default function SharedAlbumPage() {
  const [token, setToken] = useState<string | null>(null);
  const [album, setAlbum] = useState<AlbumDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  // Read the share token from the query string (?t=...).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("t") ?? "");
  }, []);

  const fetcher = useCallback(
    async (cursor: string | undefined) => {
      if (!token) throw new Error("Missing share token");
      const detail = await api.sharedAlbum(token, cursor);
      if (!cursor) setAlbum(detail);
      return {
        items: detail.items,
        next_cursor: detail.next_cursor,
        count: detail.items.length,
      };
    },
    [token]
  );

  const { items, loading, loadingMore, error, sentinelRef } = useInfiniteMedia(
    fetcher,
    [token]
  );

  useEffect(() => {
    if (error) setNotFound(true);
  }, [error]);

  if (token === null) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  if (notFound || token === "") {
    return (
      <div className="grid min-h-screen place-items-center px-4 text-center">
        <div>
          <Images size={40} className="mx-auto mb-3 text-muted" />
          <p className="font-medium">Shared album not found</p>
          <p className="text-sm text-muted">
            The link may have expired or sharing was turned off.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-accent-fg">
            <Images size={16} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {album?.name ?? "Shared album"}
            </p>
            {album && (
              <p className="text-xs text-muted">
                {album.item_count} item{album.item_count === 1 ? "" : "s"} ·
                shared via PhotoPi
              </p>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-3 py-5 sm:px-4">
        {loading ? (
          <div className="grid place-items-center py-24">
            <Spinner className="h-8 w-8" />
          </div>
        ) : items.length === 0 ? (
          <p className="py-24 text-center text-sm text-muted">
            This album has no photos.
          </p>
        ) : (
          <>
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
      </main>

      {viewerIndex !== null && (
        <MediaViewer
          items={items}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
          readOnly
        />
      )}
    </div>
  );
}
