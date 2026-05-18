import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** A bordered surface used to group dashboard content. */
export function Card({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-surface p-5",
        className
      )}
      {...props}
    />
  );
}
