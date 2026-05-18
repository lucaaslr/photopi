"use client";

/**
 * Albums page.
 *
 * Shows the album grid; selecting one opens an inline detail view with the
 * album's media, a share toggle and (for admins) delete. Manual albums can
 * be created here; Takeout-reconstructed albums are read-mostly.
 */
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  FolderOpen,
  Plus,
  ArrowLeft,
  Share2,
  Trash2,
  Check,
  Copy,
  Loader2,
} from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Gallery } from "@/components/Gallery";
import { MediaViewer } from "@/components/MediaViewer";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Dialog } from "@/components/ui/Dialog";
import { useAuth, useRequireAuth } from "@/lib/auth";
import { api, type Album, type AlbumDetail } from "@/lib/api";
import { useInfiniteMedia } from "@/hooks/useInfiniteMedia";

// --- Album detail view ----------------------------------------------------
function AlbumView({
  albumId,
  onBack,
  onChanged,
}: {
  albumId: number;
  onBack: () => void;
  onChanged: () => void;
}) {
  const { user } = useAuth();
  const [album, setAlbum] = useState<AlbumDetail | null>(null);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetcher = useCallback(
    async (cursor: string | undefined) => {
      const detail = await api.album(albumId, cursor);
      // Capture metadata on the first page.
      if (!cursor) setAlbum(detail);
      return { items: detail.items, next_cursor: detail.next_cursor, count: detail.items.length };
    },
    [albumId]
  );

  const { items, loading, loadingMore, sentinelRef, patchItem, removeItem } =
    useInfiniteMedia(fetcher, [albumId]);

  const toggleShare = async () => {
    if (!album || busy) return;
    setBusy(true);
    try {
      const updated = await api.updateAlbum(album.id, {
        is_shared: !album.is_shared,
      });
      setAlbum({ ...album, ...updated });
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!album || busy) return;
    if (!window.confirm(`Delete the album "${album.name}"? The photos themselves are kept.`)) {
      return;
    }
    setBusy(true);
    try {
      await api.deleteAlbum(album.id);
      onChanged();
      onBack();
    } finally {
      setBusy(false);
    }
  };

  const shareLink =
    album?.share_token && typeof window !== "undefined"
      ? `${window.location.origin}/shared/?t=${album.share_token}`
      : "";

  const copyLink = async () => {
    if (!shareLink) return;
    await navigator.clipboard.writeText(shareLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={onBack} aria-label="Back">
          <ArrowLeft size={18} />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold">
            {album?.name ?? "Album"}
          </h1>
          {album && (
            <p className="text-sm text-muted">
              {album.item_count} item{album.item_count === 1 ? "" : "s"}
              {album.source === "takeout" && " · from Takeout"}
            </p>
          )}
        </div>
        {user?.is_admin && album && (
          <>
            <Button
              variant={album.is_shared ? "primary" : "secondary"}
              size="sm"
              onClick={toggleShare}
              disabled={busy}
            >
              <Share2 size={15} />
              {album.is_shared ? "Shared" : "Share"}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDelete}
              disabled={busy}
              aria-label="Delete album"
            >
              <Trash2 size={17} />
            </Button>
          </>
        )}
      </div>

      {album?.is_shared && shareLink && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-border bg-surface p-2.5 text-sm">
          <span className="truncate text-muted">{shareLink}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={copyLink}
            className="ml-auto shrink-0"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      )}

      {loading ? (
        <div className="grid place-items-center py-24">
          <Spinner className="h-8 w-8" />
        </div>
      ) : items.length === 0 ? (
        <p className="py-24 text-center text-sm text-muted">
          This album has no photos yet.
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

      {viewerIndex !== null && (
        <MediaViewer
          items={items}
          index={viewerIndex}
          onClose={() => setViewerIndex(null)}
          onIndexChange={setViewerIndex}
          onPatch={patchItem}
          onDelete={removeItem}
          readOnly={!user?.is_admin}
        />
      )}
    </div>
  );
}

// --- Album grid -----------------------------------------------------------
function AlbumCardGrid({
  albums,
  onOpen,
}: {
  albums: Album[];
  onOpen: (id: number) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {albums.map((album) => (
        <button
          key={album.id}
          onClick={() => onOpen(album.id)}
          className="group text-left"
        >
          <div className="aspect-square overflow-hidden rounded-xl bg-elevated">
            {album.cover_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={album.cover_url}
                alt={album.name}
                loading="lazy"
                className="h-full w-full object-cover transition group-hover:scale-[1.03]"
              />
            ) : (
              <div className="grid h-full w-full place-items-center text-muted">
                <FolderOpen size={32} />
              </div>
            )}
          </div>
          <p className="mt-2 truncate text-sm font-medium">{album.name}</p>
          <p className="text-xs text-muted">
            {album.item_count} item{album.item_count === 1 ? "" : "s"}
            {album.source === "takeout" && " · Takeout"}
          </p>
        </button>
      ))}
    </div>
  );
}

// --- Page -----------------------------------------------------------------
export default function AlbumsPage() {
  const { loading: authLoading } = useRequireAuth();
  const { user } = useAuth();

  const [albums, setAlbums] = useState<Album[] | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadAlbums = useCallback(() => {
    api
      .albums()
      .then(setAlbums)
      .catch(() => setAlbums([]));
  }, []);

  useEffect(() => {
    loadAlbums();
  }, [loadAlbums]);

  const createAlbum = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const album = await api.createAlbum(
        newName.trim(),
        newDesc.trim() || undefined
      );
      setCreateOpen(false);
      setNewName("");
      setNewDesc("");
      loadAlbums();
      setOpenId(album.id);
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Could not create the album."
      );
    } finally {
      setCreating(false);
    }
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
        {openId !== null ? (
          <AlbumView
            albumId={openId}
            onBack={() => setOpenId(null)}
            onChanged={loadAlbums}
          />
        ) : (
          <>
            <div className="mb-5 flex items-center justify-between">
              <h1 className="text-lg font-semibold">Albums</h1>
              {user?.is_admin && (
                <Button size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus size={16} />
                  New album
                </Button>
              )}
            </div>

            {albums === null ? (
              <div className="grid place-items-center py-24">
                <Spinner className="h-8 w-8" />
              </div>
            ) : albums.length === 0 ? (
              <div className="grid place-items-center gap-2 py-24 text-center">
                <FolderOpen size={40} className="text-muted" />
                <p className="font-medium">No albums yet</p>
                <p className="text-sm text-muted">
                  Create one, or index a Takeout export to reconstruct your
                  Google Photos albums automatically.
                </p>
              </div>
            ) : (
              <AlbumCardGrid albums={albums} onOpen={setOpenId} />
            )}
          </>
        )}
      </main>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New album"
        wide
      >
        <form onSubmit={createAlbum} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Name</label>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Holiday 2024"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Description{" "}
              <span className="font-normal text-muted">(optional)</span>
            </label>
            <Input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="A short note about this album"
            />
          </div>
          {createError && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {createError}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={creating || !newName.trim()}>
              {creating && <Loader2 size={15} className="animate-spin" />}
              Create
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
