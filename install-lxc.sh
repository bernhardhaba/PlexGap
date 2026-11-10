#!/usr/bin/env bash
# PlexGap im LXC-Container (Debian/Ubuntu) als root installieren, im Ordner mit server.py + index.html:
#   bash install-lxc.sh
set -euo pipefail

APP=/opt/plexgap
apt-get update -y
apt-get install -y python3

mkdir -p "$APP"
cp server.py index.html "$APP/"

cat > /etc/systemd/system/plexgap.service <<'EOF'
[Unit]
Description=PlexGap (Plex fehlende Folgen)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/plexgap
Environment=HOST=0.0.0.0
Environment=HEADLESS=1
Environment=PLEXGAP_AUTOUPDATE=1
ExecStart=/usr/bin/python3 /opt/plexgap/server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable plexgap
systemctl restart plexgap
echo "Fertig: http://$(hostname -I | awk '{print $1}'):8765"
