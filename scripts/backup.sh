#!/usr/bin/env bash
# Back up PhotoPi application data (database + thumbnail cache).
#
# This backs up only PhotoPi's own data volume - your original photos on
# the HDD are never touched and should be backed up separately.
#
# Usage:
#   ./scripts/backup.sh [destination-dir]
set -euo pipefail

cd "$(dirname "$0")/.."

DEST="${1:-./backups}"
mkdir -p "$DEST"

STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$DEST/photopi-data-$STAMP.tar.gz"

# Resolve the Docker volume name (compose prefixes it with the project dir).
VOLUME="$(docker volume ls --format '{{.Name}}' | grep -E 'photopi-data$' | head -n1)"
if [ -z "$VOLUME" ]; then
  echo "ERROR: could not find the 'photopi-data' Docker volume."
  echo "Is PhotoPi installed and has it been started at least once?"
  exit 1
fi

echo "Backing up volume '$VOLUME' -> $ARCHIVE"

# Run a throwaway container that tars the volume's contents to stdout.
docker run --rm \
  -v "$VOLUME":/data:ro \
  -v "$(cd "$DEST" && pwd)":/backup \
  alpine:3.20 \
  tar czf "/backup/photopi-data-$STAMP.tar.gz" -C /data .

echo "Backup complete: $ARCHIVE"
echo "Size: $(du -h "$ARCHIVE" | cut -f1)"

# --- Restore instructions --------------------------------------------------
cat <<'NOTE'

To restore this backup later:
  docker compose down
  docker run --rm -v <project>_photopi-data:/data -v "$PWD/backups":/backup \
    alpine:3.20 sh -c "rm -rf /data/* && tar xzf /backup/<archive>.tar.gz -C /data"
  docker compose up -d
NOTE
