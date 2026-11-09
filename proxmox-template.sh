#!/usr/bin/env bash
# PlexGap: legt LXC 109 (192.168.2.209) an und installiert die App.
# Auf dem Proxmox-Host als root ausführen:  bash PlexGap-Proxmox-Setup.sh
# Optional anpassbar per Umgebungsvariable: GW, BRIDGE, STORAGE, TEMPLATE_STORAGE
set -euo pipefail

CTID=109
IP=192.168.2.209/24
GW=${GW:-192.168.2.1}
BRIDGE=${BRIDGE:-vmbr0}
STORAGE=${STORAGE:-local-lvm}
TEMPLATE_STORAGE=${TEMPLATE_STORAGE:-local}

if pct status "$CTID" >/dev/null 2>&1; then
  echo "Container $CTID existiert bereits - Abbruch." >&2
  exit 1
fi

read -r -s -p "Root-Passwort für den Container: " PW; echo

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
base64 -d > "$TMP/server.py" <<'EOF_SERVER'
@@SERVER_PY@@
EOF_SERVER
base64 -d > "$TMP/index.html" <<'EOF_INDEX'
@@INDEX_HTML@@
EOF_INDEX
base64 -d > "$TMP/install-lxc.sh" <<'EOF_INSTALL'
@@INSTALL_SH@@
EOF_INSTALL

pveam update
TPL=$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort -V | tail -1)
pveam list "$TEMPLATE_STORAGE" | grep -q "$TPL" || pveam download "$TEMPLATE_STORAGE" "$TPL"

pct create "$CTID" "$TEMPLATE_STORAGE:vztmpl/$TPL" \
  --hostname plexgap --cores 1 --memory 512 --swap 256 \
  --rootfs "$STORAGE:4" \
  --net0 "name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GW" \
  --nameserver 1.1.1.1 \
  --unprivileged 1 --onboot 1 \
  --password "$PW"
pct start "$CTID"

echo "Warte auf Netzwerk im Container ..."
for i in $(seq 1 30); do
  pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1 && break
  sleep 2
done

pct exec "$CTID" -- mkdir -p /root/plexgap
for f in server.py index.html install-lxc.sh; do
  pct push "$CTID" "$TMP/$f" "/root/plexgap/$f"
done
pct exec "$CTID" -- bash -c 'cd /root/plexgap && bash install-lxc.sh'

echo
echo "PlexGap läuft: http://192.168.2.209:8765"
