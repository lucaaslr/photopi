"use client";

/**
 * useInfiniteMedia
 *
 * Keyset-paginated loader for media listings. Works for the timeline,
 * search results and album contents - the only thing that varies is the
 * fetch function passed in.
 *
 * Pages accumulate in memory; on a Pi-hosted library that can be large, so
 * callers should keep the page size moderate (the API default is 60).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { MediaItem, MediaPage } from "@/lib/api";

type Fetcher = (cursor: string | undefined) => Promise<MediaPage>;

interface InfiniteMediaState {
  items: MediaItem[];
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  hasMore: boolean;
  /** Attach to a sentinel element at the end of the list. */
  sentinelRef: (node: HTMLElement | null) => void;
  reload: () => void;
  /** Optimistically replace a single item (e.g. after a favourite toggle). */
  patchItem: (id: number, patch: Partial<MediaItem>) => void;
  /** Remove an item locally (e.g. after deletion). */
  removeItem: (id: number) => void;
}

export function useInfiniteMedia(
  fetcher: Fetcher,
  deps: unknown[] = []
): InfiniteMediaState {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against overlapping fetches and stale results after a reload.
  const fetchingRef = useRef(false);
  const generationRef = useRef(0);

  const load = useCallback(
    async (reset: boolean) => {
      if (fetchingRef.current) return;
      if (!reset && !hasMore) return;

      fetchingRef.current = true;
      const generation = generationRef.current;
      reset ? setLoading(true) : setLoadingMore(true);
      setError(null);

      try {
        const page = await fetcher(reset ? undefined : cursor);
        if (generation !== generationRef.current) return; // superseded
        setItems((prev) => (reset ? page.items : [...prev, ...page.items]));
        setCursor(page.next_cursor ?? undefined);
        setHasMore(page.next_cursor !== null);
      } catch (e) {
        if (generation !== generationRef.current) return;
        setError(e instanceof Error ? e.message : "Failed to load media.");
        setHasMore(false);
      } finally {
        if (generation === generationRef.current) {
          setLoading(false);
          setLoadingMore(false);
        }
        fetchingRef.current = false;
      }
    },
    // `cursor` and `hasMore` are intentionally read fresh on each call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fetcher, cursor, hasMore]
  );

  // Reset and reload whenever the dependency list changes.
  useEffect(() => {
    generationRef.current += 1;
    setItems([]);
    setCursor(undefined);
    setHasMore(true);
    void load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // IntersectionObserver-driven infinite scroll.
  const observerRef = useRef<IntersectionObserver | null>(null);
  const sentinelRef = useCallback(
    (node: HTMLElement | null) => {
      observerRef.current?.disconnect();
      if (!node) return;
      observerRef.current = new IntersectionObserver(
        (entries) => {
          if (entries[0]?.isIntersecting) void load(false);
        },
        { rootMargin: "600px" }
      );
      observerRef.current.observe(node);
    },
    [load]
  );

  useEffect(() => () => observerRef.current?.disconnect(), []);

  return {
    items,
    loading,
    loadingMore,
    error,
    hasMore,
    sentinelRef,
    reload: () => {
      generationRef.current += 1;
      setItems([]);
      setCursor(undefined);
      setHasMore(true);
      void load(true);
    },
    patchItem: (id, patch) =>
      setItems((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...patch } : m))
      ),
    removeItem: (id) => setItems((prev) => prev.filter((m) => m.id !== id)),
  };
}
