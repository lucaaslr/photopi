# PhotoPi frontend image - multi-stage build.
#
# Stage 1 compiles the Next.js static export. Stage 2 is a tiny nginx image
# that just serves the resulting files, so nothing Node-related ships to
# the Raspberry Pi.

# --- Stage 1: build ---------------------------------------------------------
FROM node:20-slim AS builder

WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# Build the static export (next.config.mjs sets output: 'export').
COPY . .
RUN npm run build

# --- Stage 2: serve ---------------------------------------------------------
FROM nginx:1.27-alpine

# `next build` with output:'export' writes the site to /app/out.
COPY --from=builder /app/out /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1
