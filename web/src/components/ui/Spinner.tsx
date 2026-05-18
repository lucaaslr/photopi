import { cn } from "@/lib/utils";

/** Indeterminate loading indicator. */
export function Spinner({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn(
        "h-6 w-6 animate-spin rounded-full border-2 border-border",
        "border-t-accent",
        className
      )}
    />
  );
}
