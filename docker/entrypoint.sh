#!/bin/sh
# Prepares the data volume as root, then runs zendiloHUB as PUID:PGID.
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = 0 ]; then
  # Volumes created by Docker belong to root; bind mounts keep the owner they have on the host.
  mkdir -p "$ZENDILOHUB_DATA_DIR"
  [ "$(stat -c %u:%g "$ZENDILOHUB_DATA_DIR")" = "$PUID:$PGID" ] || chown -R "$PUID:$PGID" "$ZENDILOHUB_DATA_DIR"
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups -- "$@"
fi
exec "$@"
