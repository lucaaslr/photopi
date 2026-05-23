#!/usr/bin/env bash
# PhotoPi first-time setup.
# Prepares the .env file, checks prerequisites and builds the containers.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== PhotoPi setup ==="

# --- 1. Check Docker -------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed."
  echo "On DietPi:  dietpi-software  ->  install 'Docker' and 'Docker Compose'"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' (v2) is not available."
  exit 1
fi

# --- 2. Create .env --------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from the template."

  # Generate a strong JWT secret automatically.
  if command -v openssl >/dev/null 2>&1; then
    SECRET="$(openssl rand -hex 32)"
    # Portable in-place sed (works on both GNU and BSD sed).
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=${SECRET}|" .env && rm -f .env.bak
    echo "Generated a random JWT_SECRET."
  fi

  echo
  echo ">>> IMPORTANT: edit .env now and set:"
  echo "      PHOTOS_DIR      - path to your Takeout export"
  echo "      ADMIN_PASSWORD  - your admin password"
  echo
  read -r -p "Press Enter once you have edited .env to continue..."
else
  echo ".env already exists - leaving it untouched."
fi

# --- 3. Validate the photos directory -------------------------------------
PHOTOS_DIR="$(grep -E '^PHOTOS_DIR=' .env | cut -d= -f2-)"
if [ ! -d "$PHOTOS_DIR" ]; then
  echo "WARNING: PHOTOS_DIR '$PHOTOS_DIR' does not exist yet."
  echo "         Mount your HDD there (see scripts/mount-hdd.sh) before indexing."
fi

# --- 4. Build & launch -----------------------------------------------------
echo
echo "Building containers (this takes a while on a Pi)..."
docker compose build

echo "Starting PhotoPi..."
docker compose up -d

WEB_PORT="$(grep -E '^WEB_PORT=' .env | cut -d= -f2-)"
WEB_PORT="${WEB_PORT:-8080}"

echo
echo "=== PhotoPi is starting ==="
echo "Open:  http://$(hostname -I | awk '{print $1}'):${WEB_PORT}"
echo "Sign in with the admin credentials from your .env file,"
echo "then go to Admin -> Start indexing to scan your library."
