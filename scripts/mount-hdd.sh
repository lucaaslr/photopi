#!/usr/bin/env bash
# Mount the external USB HDD and optionally persist it across reboots via fstab.
#
# Usage:
#   sudo ./scripts/mount-hdd.sh                 # interactive
#   sudo ./scripts/mount-hdd.sh /dev/sda2       # mount a known device
set -euo pipefail

MOUNT_POINT="/mnt/hdd"

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
  read -r -p "Enter the partition to mount (e.g. /dev/sda2): " DEVICE
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
  if [ "$FSTYPE" = "ntfs" ] || [ "$FSTYPE" = "ntfs-3g" ]; then
    # ntfs-3g handles permissions and avoids the "exclusively opened" error
    # that the plain kernel driver triggers on drives with a dirty bit set.
    ntfs-3g "$DEVICE" "$MOUNT_POINT" -o big_writes,noatime
  else
    mount "$DEVICE" "$MOUNT_POINT"
  fi
  echo "Mounted $DEVICE at $MOUNT_POINT"
fi

# --- 3. Offer to persist in /etc/fstab ------------------------------------
UUID="$(blkid -o value -s UUID "$DEVICE" || true)"
if [ -n "$UUID" ] && ! grep -q "$UUID" /etc/fstab; then
  echo
  read -r -p "Add to /etc/fstab so it mounts automatically at boot? [y/N] " ANS
  if [[ "$ANS" =~ ^[Yy]$ ]]; then
    if [ "$FSTYPE" = "ntfs" ] || [ "$FSTYPE" = "ntfs-3g" ]; then
      # 'nofail'  - Pi boots normally even if the drive is unplugged.
      # 'noatime' - fewer writes to the HDD, better for flash/external storage.
      # 'big_writes' - better throughput for ntfs-3g.
      # '0 0'    - skip dump and fsck (NTFS integrity is checked by Windows chkdsk).
      OPTS="big_writes,noatime,nofail"
      echo "UUID=$UUID  $MOUNT_POINT  ntfs-3g  $OPTS  0  0" >> /etc/fstab
    else
      echo "UUID=$UUID  $MOUNT_POINT  ${FSTYPE:-auto}  defaults,nofail  0  2" \
        >> /etc/fstab
    fi
    echo "Added to /etc/fstab. Verify with:  mount -a"
  fi
fi

echo
echo "Done. Contents of $MOUNT_POINT:"
ls -la "$MOUNT_POINT" | head -n 12
