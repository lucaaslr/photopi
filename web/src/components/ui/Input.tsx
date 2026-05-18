import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** Single-line text input with the shared field styling. */
export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm",
      "text-fg placeholder:text-muted transition",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
      "disabled:opacity-50",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";
