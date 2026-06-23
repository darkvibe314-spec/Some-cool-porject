# YouTube MP3/MP4 API

Simple Python API for:
- `GET/POST /api/ytmp3`
- `GET/POST /api/ytmp4`
- `GET /health`

Default runtime port is `4677`.

## Local run

```bash
cd /home/runner/work/Some-cool-porject/Some-cool-porject
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip yt-dlp
python3 yt_api.py
```

Test:

```bash
curl "http://127.0.0.1:4677/health"
curl -L "http://127.0.0.1:4677/api/ytmp3?url=https://youtu.be/dQw4w9WgXcQ" -o out.mp3
curl -L "http://127.0.0.1:4677/api/ytmp4?url=https://youtu.be/dQw4w9WgXcQ" -o out.mp4
```

## Permanent VPS hosting (systemd + nginx)

1) Copy repository to `/opt/yt-api` on your VPS.

2) Run one command (Ubuntu/Debian):

```bash
cd /opt/yt-api && sudo bash /opt/yt-api/scripts/setup_vps.sh
```

This command:
- installs Python, ffmpeg, nginx
- creates `.venv`
- installs `yt-dlp`
- installs and enables systemd service (`yt-api.service`)
- configures nginx reverse proxy to `127.0.0.1:4677`

## Service operations

```bash
sudo systemctl status yt-api --no-pager
sudo systemctl restart yt-api
sudo journalctl -u yt-api -f
```

## Domain (later)

After DNS points to your VPS IP:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Then update `server_name` in `/etc/nginx/sites-available/yt-api` and reload nginx:

```bash
sudo systemctl reload nginx
```

## Tests

From repo root:

```bash
python3 -m unittest -v
```
