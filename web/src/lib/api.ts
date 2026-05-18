/**
 * Thin typed wrapper around the PhotoPi REST API.
 *
 * In the default Docker deployment nginx proxies `/api` to the backend, so
 * an empty base URL (relative requests) is correct. Override with
 * NEXT_PUBLIC_API_BASE only when frontend and backend live on different
 * origins.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const TOKEN_KEY = "photopi_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** When true, a 401 will not redirect to /login (used by the login call). */
  noAuthRedirect?: boolean;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the PhotoPi server.");
  }

  if (resp.status === 401 && !opts.noAuthRedirect) {
    clearToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login/";
    }
    throw new ApiError(401, "Session expired. Please sign in again.");
  }

  if (resp.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await resp.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!resp.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `Request failed (${resp.status})`;
    throw new ApiError(resp.status, detail);
  }

  return payload as T;
}

// --- Domain types ---------------------------------------------------------
export interface MediaItem {
  id: number;
  filename: string;
  media_type: "image" | "video";
  taken_at: string;
  width: number | null;
  height: number | null;
  duration: number | null;
  favorite: boolean;
  archived: boolean;
  thumb_status: string;
  is_duplicate: boolean;
  thumb_url: string;
  preview_url: string;
  file_url: string;
}

export interface MediaDetail extends MediaItem {
  rel_path: string;
  size_bytes: number;
  mime_type: string;
  taken_source: string;
  camera_make: string | null;
  camera_model: string | null;
  lat: number | null;
  lon: number | null;
  altitude: number | null;
  description: string | null;
  content_hash: string | null;
  phash: string | null;
  duplicate_of: number | null;
  indexed_at: string;
  maps_url: string | null;
}

export interface MediaPage {
  items: MediaItem[];
  next_cursor: string | null;
  count: number;
}

export interface TimelineBucket {
  year: string;
  month: string;
  count: number;
}

export interface Album {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  source: string;
  cover_media_id: number | null;
  is_shared: boolean;
  share_token: string | null;
  created_at: string;
  item_count: number;
  cover_url: string | null;
}

export interface AlbumDetail extends Album {
  items: MediaItem[];
  next_cursor: string | null;
}

export interface IndexJob {
  id: number;
  status: string;
  root_path: string;
  total_files: number;
  processed_files: number;
  indexed_files: number;
  updated_files: number;
  skipped_files: number;
  failed_files: number;
  current_path: string | null;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  progress: number;
}

export interface StorageStats {
  media_total: number;
  image_count: number;
  video_count: number;
  album_count: number;
  library_bytes: number;
  thumbnail_bytes: number;
  database_bytes: number;
  data_free_bytes: number;
  media_free_bytes: number;
  oldest: string | null;
  newest: string | null;
}

export interface CameraStat {
  model: string;
  count: number;
}

export interface Dashboard {
  stats: StorageStats;
  job: IndexJob | null;
  job_running: boolean;
  cameras: CameraStat[];
}

export interface CurrentUser {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

// --- Endpoint helpers -----------------------------------------------------
function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "" && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; expires_in: number }>(
      "/auth/login",
      { method: "POST", body: { username, password }, noAuthRedirect: true }
    ),
  me: () => request<CurrentUser>("/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/auth/change-password", {
      method: "POST",
      body: { current_password, new_password },
    }),

  // Media
  timeline: (params: { cursor?: string; limit?: number; media_type?: string }) =>
    request<MediaPage>(`/media${qs(params)}`),
  timelineBuckets: () => request<TimelineBucket[]>("/media/timeline/buckets"),
  media: (id: number) => request<MediaDetail>(`/media/${id}`),
  updateMedia: (
    id: number,
    patch: { favorite?: boolean; archived?: boolean; description?: string }
  ) => request<MediaDetail>(`/media/${id}`, { method: "PATCH", body: patch }),
  deleteMedia: (id: number) =>
    request<void>(`/media/${id}`, { method: "DELETE" }),

  // Search
  search: (params: {
    q?: string;
    media_type?: string;
    camera_model?: string;
    favorite?: boolean;
    date_from?: string;
    date_to?: string;
    cursor?: string;
    limit?: number;
  }) => request<MediaPage>(`/search${qs(params)}`),
  cameras: () => request<CameraStat[]>("/search/cameras"),

  // Albums
  albums: () => request<Album[]>("/albums"),
  createAlbum: (name: string, description?: string) =>
    request<Album>("/albums", { method: "POST", body: { name, description } }),
  album: (id: number, cursor?: string) =>
    request<AlbumDetail>(`/albums/${id}${qs({ cursor })}`),
  updateAlbum: (
    id: number,
    patch: {
      name?: string;
      description?: string;
      cover_media_id?: number;
      is_shared?: boolean;
    }
  ) => request<Album>(`/albums/${id}`, { method: "PATCH", body: patch }),
  deleteAlbum: (id: number) =>
    request<void>(`/albums/${id}`, { method: "DELETE" }),
  addToAlbum: (id: number, media_ids: number[]) =>
    request<Album>(`/albums/${id}/items`, {
      method: "POST",
      body: { media_ids },
    }),
  removeFromAlbum: (id: number, media_ids: number[]) =>
    request<Album>(`/albums/${id}/items`, {
      method: "DELETE",
      body: { media_ids },
    }),
  sharedAlbum: (token: string, cursor?: string) =>
    request<AlbumDetail>(`/albums/shared/${token}${qs({ cursor })}`),

  // Admin
  dashboard: () => request<Dashboard>("/admin/dashboard"),
  indexStatus: () => request<IndexJob | null>("/admin/index/status"),
  startIndex: (root_path?: string) =>
    request<IndexJob>("/admin/index/start", {
      method: "POST",
      body: { root_path },
    }),
  pauseIndex: () => request<{ status: string }>("/admin/index/pause", { method: "POST" }),
  resumeIndex: () =>
    request<{ status: string }>("/admin/index/resume", { method: "POST" }),
  cancelIndex: () =>
    request<{ status: string }>("/admin/index/cancel", { method: "POST" }),
};

/** Resolve a relative API media URL to an absolute one for <img> tags.
 *  Appends ?token=... so browser-native requests (img, video) can authenticate.
 */
export function mediaUrl(path: string): string {
  const token = getToken();
  const sep = path.includes("?") ? "&" : "?";
  return `${API_BASE}${path}${token ? `${sep}token=${token}` : ""}`;
}
