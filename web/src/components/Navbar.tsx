"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Images,
  Search,
  FolderOpen,
  Settings,
  Moon,
  Sun,
  LogOut,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "./ThemeProvider";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Photos", icon: Images },
  { href: "/search", label: "Search", icon: Search },
  { href: "/albums", label: "Albums", icon: FolderOpen },
];

/**
 * Top navigation bar. Doubles as a bottom tab bar on small screens so the
 * UI stays comfortable on a phone browsing the Pi over the LAN.
 */
export function Navbar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-3 sm:gap-2 sm:px-4">
        <Link href="/" className="mr-2 flex items-center gap-2 font-semibold">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-accent-fg">
            <Images size={16} />
          </span>
          <span className="hidden sm:inline">PhotoPi</span>
        </Link>

        {/* Desktop links */}
        <nav className="hidden items-center gap-1 sm:flex">
          {LINKS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition",
                isActive(href)
                  ? "bg-elevated text-fg"
                  : "text-muted hover:bg-elevated hover:text-fg"
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
          {user?.is_admin && (
            <Link
              href="/admin"
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition",
                isActive("/admin")
                  ? "bg-elevated text-fg"
                  : "text-muted hover:bg-elevated hover:text-fg"
              )}
            >
              <Settings size={16} />
              Admin
            </Link>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="rounded-lg p-2 text-muted transition hover:bg-elevated hover:text-fg"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {user && (
            <button
              onClick={logout}
              aria-label="Sign out"
              title={`Sign out (${user.username})`}
              className="rounded-lg p-2 text-muted transition hover:bg-elevated hover:text-fg"
            >
              <LogOut size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Mobile bottom tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-bg/95 backdrop-blur sm:hidden">
        {LINKS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] transition",
              isActive(href) ? "text-accent" : "text-muted"
            )}
          >
            <Icon size={20} />
            {label}
          </Link>
        ))}
        {user?.is_admin && (
          <Link
            href="/admin"
            className={cn(
              "flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] transition",
              isActive("/admin") ? "text-accent" : "text-muted"
            )}
          >
            <Settings size={20} />
            Admin
          </Link>
        )}
      </nav>
    </header>
  );
}
