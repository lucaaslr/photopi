#!/usr/bin/env bash
# Helper to mount the external USB HDD holding the Google Photos Takeout
# export, and optionally make the mount persistent across reboots.
#
# Usage:
#   sudo ./scripts/mount-hdd.sh                 # interactive
#   sudo ./scripts/mount-hdd.sh /dev/sda1       # mount a known device
set -euo pipefail

MOUNT_POINT="/mnt/google-photos"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root:  sudo $0"
  exit 1
fi

# --- 1. Identify the device ------------------------------------------------
DEVICE="${1:-}"
if [ -z "$DEVICE" ]; then
  echo "Available block devices:"
  lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT
  echo
  read -r -p "Enter the partition to mount (e.g. /dev/sda1): " DEVICE
fi

if [ ! -b "$DEVICE" ]; then
  echo "ERROR: '$DEVICE' is not a block device."
  exit 1
fi

# --- 2. Mount --------------------------------------------------------------
mkdir -p "$MOUNT_POINT"

FSTYPE="$(blkid -o value -s TYPE "$DEVICE" || true)"
echo "Detected filesystem: ${FSTYPE:-unknown}"

if mountpoint -q "$MOUNT_POINT"; then
  echo "$MOUNT_POINT is already mounted."
else
  mount "$DEVICE" "$MOUNT_POINT"
  echo "Mounted $DEVICE at $MOUNT_POINT"
fi

# --- 3. Offer to persist in /etc/fstab ------------------------------------
UUID="$(blkid -o value -s UUID "$DEVICE" || true)"
if [ -n "$UUID" ] && ! grep -q "$UUID" /etc/fstab; then
  echo
  read -r -p "Add this drive to /etc/fstab so it mounts at every boot? [y/N] " ANS
  if [[ "$ANS" =~ ^[Yy]$ ]]; then
    # 'nofail' keeps the Pi booting even if the drive is unplugged.
    echo "UUID=$UUID  $MOUNT_POINT  ${FSTYPE:-auto}  defaults,nofail,ro  0  2" \
      >> /etc/fstab
    echo "Added to /etc/fstab (read-only, nofail)."
  fi
fi

echo
echo "Done. Contents of $MOUNT_POINT:"
ls -la "$MOUNT_POINT" | head -n 12
