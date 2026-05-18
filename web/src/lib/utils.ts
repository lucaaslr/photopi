/** Small presentation helpers shared across components. */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind-aware className combiner. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Human-readable byte size, e.g. 1536 -> "1.5 KB". */
export function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(
    units.length - 1,
    Math.floor(Math.log(bytes) / Math.log(1024))
  );
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Seconds -> "m:ss" or "h:mm:ss" for video durations. */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "";
  const s = Math.floor(seconds % 60);
  const m = Math.floor((seconds / 60) % 60);
  const h = Math.floor(seconds / 3600);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** Full readable date, e.g. "14 March 2024". */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Unknown date";
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** Date + time, e.g. "14 March 2024, 09:42". */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Unknown";
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${formatDate(iso)}, ${time}`;
}

/** Heading for a timeline section, e.g. "March 2024". */
export function monthLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Unknown";
  return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** Group media-like items into contiguous month buckets (input is newest-first). */
export function groupByMonth<T extends { taken_at: string }>(
  items: T[]
): { key: string; label: string; items: T[] }[] {
  const groups: { key: string; label: string; items: T[] }[] = [];
  for (const item of items) {
    const d = new Date(item.taken_at);
    const key = Number.isNaN(d.getTime())
      ? "unknown"
      : `${d.getFullYear()}-${d.getMonth()}`;
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.items.push(item);
    } else {
      groups.push({ key, label: monthLabel(item.taken_at), items: [item] });
    }
  }
  return groups;
}
