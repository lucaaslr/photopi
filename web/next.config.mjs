/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static HTML export: the whole app ships as plain files served by nginx.
  // This is the lightest possible deployment - no Node.js process on the Pi.
  output: 'export',
  // next/image optimisation needs a server; disable it for the static export.
  images: { unoptimized: true },
  // Cleaner URLs when served as static files (/login/ -> /login/index.html).
  trailingSlash: true,
  reactStrictMode: true,
};

export default nextConfig;
