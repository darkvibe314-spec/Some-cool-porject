import json
import os
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse


ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
YOUTUBE_VIDEO_ID_LENGTH = 11
MAX_BODY_BYTES = 2048
DOWNLOAD_TIMEOUT_SECONDS = 300
STREAM_CHUNK_SIZE_BYTES = 64 * 1024
YT_DLP_PATH = shutil.which("yt-dlp")


def is_supported_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.netloc.lower() in ALLOWED_HOSTS


def normalize_youtube_url(raw_url: str) -> str | None:
    if not is_supported_url(raw_url):
        return None
    parsed = urlparse(raw_url.strip())
    host = parsed.netloc.lower()
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
    else:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    if not video_id or len(video_id) != YOUTUBE_VIDEO_ID_LENGTH:
        return None
    if not all(ch.isalnum() or ch in {"_", "-"} for ch in video_id):
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_input(handler: BaseHTTPRequestHandler) -> str | None:
    if handler.command == "GET":
        query = parse_qs(urlparse(handler.path).query)
        return (query.get("url") or [None])[0]
    if handler.command == "POST":
        try:
            content_length = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            return None
        raw = handler.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload.get("url")
    return None


def build_command(fmt: str, out_template: str) -> list[str]:
    if fmt == "mp3":
        return [
            YT_DLP_PATH or "yt-dlp",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "-o",
            out_template,
            "--batch-file",
            "-",
        ]
    return [
        YT_DLP_PATH or "yt-dlp",
        "--no-playlist",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_template,
        "--batch-file",
        "-",
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
        if YT_DLP_PATH is None:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "yt-dlp is not installed or not found in PATH. Please install yt-dlp."},
            )
            return
        url = parse_input(self)
        if not url:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Missing or invalid YouTube URL parameter/payload"},
            )
            return
        normalized_url = normalize_youtube_url(url)
        if not normalized_url:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid YouTube URL"})
            return
        with tempfile.TemporaryDirectory(prefix="yt-api-") as tmpdir:
            out_template = os.path.join(tmpdir, "%(id)s.%(ext)s")
            try:
                process = subprocess.run(
                    build_command(fmt, out_template),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                    input=f"{normalized_url}\n",
                )
            except subprocess.TimeoutExpired:
                self._send_json(HTTPStatus.GATEWAY_TIMEOUT, {"error": "Download timed out"})
                return
            if process.returncode != 0:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "Download failed. Check URL availability and access restrictions."},
                )
                return
            ext = ".mp3" if fmt == "mp3" else ".mp4"
            files = [f for f in os.listdir(tmpdir) if f.lower().endswith(ext)]
            if len(files) != 1:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "Expected exactly one output file"},
                )
                return
            file_path = os.path.join(tmpdir, files[0])
            file_size = os.path.getsize(file_path)
            safe_filename = files[0].replace("\r", "").replace("\n", "").replace('"', "")
            encoded_filename = quote(safe_filename)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/mpeg" if fmt == "mp3" else "video/mp4")
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{encoded_filename}",
            )
            self.send_header("Content-Length", str(file_size))
            self.end_headers()
            with open(file_path, "rb") as downloaded:
                while True:
                    chunk = downloaded.read(STREAM_CHUNK_SIZE_BYTES)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

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
    host = os.getenv("HOST", "127.0.0.1")
    try:
        port = int(os.getenv("PORT", "4677"))
    except ValueError:
        port = 4677
    server = ThreadingHTTPServer((host, port), YTDownloadHandler)
    print(f"Serving YT API on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
