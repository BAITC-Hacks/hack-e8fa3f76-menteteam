"""Loopback-only, token-authenticated browser audio ingestion."""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

MAX_AUDIO_BYTES = 200 * 1024 * 1024


def meeting_platform(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
            or any(ord(char) < 32 for char in url) or "\\" in url):
        raise ValueError("Нужна HTTPS-ссылка на Teams, Zoom или Google Meet.")
    host = parsed.hostname or ""
    if host == "meet.google.com":
        return "Google Meet"
    if host == "zoom.us" or host.endswith(".zoom.us"):
        return "Zoom"
    if host in {"teams.microsoft.com", "teams.live.com", "teams.cloud.microsoft"}:
        return "Teams"
    raise ValueError("Поддерживаются ссылки Teams, Zoom и Google Meet.")


def create_server(upload_dir: Path, port: int = 8765):
    directory = Path(upload_dir)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *_):
            pass  # Do not log session tokens or meeting URLs.

        def respond(self, status, body, content_type="application/json"):
            payload = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self, query=False):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            supplied = parse_qs(urlsplit(self.path).query).get("token", [""])[0] if query else self.headers.get("X-Alem-Token", "")
            return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                    and secrets.compare_digest(supplied, token)
                    and (query or self.headers.get("Origin") == origin))

        def do_GET(self):
            if urlsplit(self.path).path != "/" or not self.authorized(query=True):
                return self.respond(403, '{"error":"Access denied"}')
            html = (Path(__file__).resolve().parents[1] / "assets" / "capture.html").read_text(encoding="utf-8")
            self.respond(200, html.replace("__TOKEN__", token), "text/html; charset=utf-8")

        def do_POST(self):
            if not self.authorized() or self.headers.get("X-Recording-Consent") != "yes":
                return self.respond(403, '{"error":"Consent and local session required"}')
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.respond(400, '{"error":"Invalid length"}')
            if self.path == "/join":
                if not 0 < length <= 4096:
                    return self.respond(413, '{"error":"Invalid link size"}')
                try:
                    url = json.loads(self.rfile.read(length))["url"]
                    platform = meeting_platform(url)
                except (ValueError, KeyError, TypeError):
                    return self.respond(400, '{"error":"Invalid meeting URL"}')
                return self.respond(200, json.dumps({"url": url, "platform": platform}))
            if self.path != "/upload":
                return self.respond(404, '{"error":"Not found"}')
            if not 0 < length <= MAX_AUDIO_BYTES:
                return self.respond(413, '{"error":"Audio limit is 200 MB"}')
            if self.headers.get("Content-Type", "").split(";")[0] not in {"audio/webm", "audio/ogg", "audio/mp4"}:
                return self.respond(415, '{"error":"Unsupported audio format"}')
            suffix = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a"}[self.headers["Content-Type"].split(";")[0]]
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"live-{uuid4().hex}{suffix}"
            temporary = target.with_suffix(".part")
            try:
                with temporary.open("xb") as output:
                    temporary.chmod(0o600)
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            raise OSError("Incomplete upload")
                        output.write(chunk)
                        remaining -= len(chunk)
                temporary.replace(target)
            except OSError:
                temporary.unlink(missing_ok=True)
                return self.respond(400, '{"error":"Incomplete upload"}')
            self.respond(201, json.dumps({"file": target.name}))

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.token = token
    return server


def start_capture(upload_dir: Path, port: int = 8765):
    server = create_server(upload_dir, port)
    Thread(target=server.serve_forever, daemon=True).start()
    return server
