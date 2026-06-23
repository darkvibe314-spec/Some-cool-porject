#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/setup_vps.sh"
  exit 1
fi

REPO_DIR="/opt/yt-api"
SERVICE_FILE="${REPO_DIR}/deploy/yt-api.service"

apt update
apt install -y python3 python3-venv ffmpeg nginx

if [[ ! -d "${REPO_DIR}" ]]; then
  echo "Expected repository at ${REPO_DIR}. Copy project there first."
  exit 1
fi

python3 -m venv "${REPO_DIR}/.venv"
"${REPO_DIR}/.venv/bin/pip" install --upgrade pip yt-dlp

cp "${SERVICE_FILE}" /etc/systemd/system/yt-api.service
systemctl daemon-reload
systemctl enable --now yt-api.service

cat >/etc/nginx/sites-available/yt-api <<'EOF'
server {
  listen 80;
  server_name _;

  client_max_body_size 2k;

  location / {
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass http://127.0.0.1:4677;
  }
}
EOF

ln -sf /etc/nginx/sites-available/yt-api /etc/nginx/sites-enabled/yt-api
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "Setup complete. Check:"
echo "  systemctl status yt-api --no-pager"
echo "  curl http://127.0.0.1/health"
