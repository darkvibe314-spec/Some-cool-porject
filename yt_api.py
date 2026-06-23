import json
import os
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def is_supported_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.netloc.lower() in ALLOWED_HOSTS


def parse_input(handler: BaseHTTPRequestHandler) -> str | None:
    if handler.command == "GET":
        query = parse_qs(urlparse(handler.path).query)
        return (query.get("url") or [None])[0]
    if handler.command == "POST":
        content_length = int(handler.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return None
        raw = handler.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None
        return payload.get("url")
    return None


def build_command(fmt: str, url: str, out_template: str) -> list[str]:
    if fmt == "mp3":
        return [
            "yt-dlp",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "-o",
            out_template,
            url,
        ]
    return [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_template,
        url,
    ]


class YTDownloadHandler(BaseHTTPRequestHandler):
    server_version = "YTDownloadAPI/1.0"

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_download(self, fmt: str) -> None:
        if shutil.which("yt-dlp") is None:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "yt-dlp is required in PATH"},
            )
            return
        url = parse_input(self)
        if not url or not is_supported_url(url):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid YouTube URL"})
            return
        with tempfile.TemporaryDirectory(prefix="yt-api-") as tmpdir:
            out_template = os.path.join(tmpdir, "%(id)s.%(ext)s")
            process = subprocess.run(
                build_command(fmt, url, out_template),
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "Download failed", "details": process.stderr.strip()},
                )
                return
            ext = ".mp3" if fmt == "mp3" else ".mp4"
            files = [f for f in os.listdir(tmpdir) if f.lower().endswith(ext)]
            if not files:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "Output file missing"})
                return
            file_path = os.path.join(tmpdir, files[0])
            with open(file_path, "rb") as downloaded:
                content = downloaded.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/mpeg" if fmt == "mp3" else "video/mp4")
            self.send_header("Content-Disposition", f'attachment; filename="{files[0]}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/api/ytmp3":
            self._handle_download("mp3")
            return
        if parsed.path == "/api/ytmp4":
            self._handle_download("mp4")
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ytmp3":
            self._handle_download("mp3")
            return
        if parsed.path == "/api/ytmp4":
            self._handle_download("mp4")
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})


def run() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), YTDownloadHandler)
    print(f"Serving YT API on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
