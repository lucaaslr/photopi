import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "PhotoPi",
  description:
    "A lightweight, self-hosted photo library for your Google Photos Takeout export.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0c0c0e",
};

/*
 * The inline script applies the saved theme before first paint so users
 * never see a flash of the wrong colour scheme.
 */
const themeScript = `
(function () {
  try {
    var t = localStorage.getItem('photopi_theme');
    if (!t) {
      t = window.matchMedia('(prefers-color-scheme: light)').matches
        ? 'light' : 'dark';
    }
    document.documentElement.classList.toggle('dark', t === 'dark');
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
