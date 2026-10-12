"""Local HTTP server: serves the UI and a small JSON API. Listens on 127.0.0.1 only."""
import json
import re
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from . import __version__, config, repo, report, tns
from .db import Database, DbError

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}
_STATIC_NAME = re.compile(r"^[\w\-]+\.[a-z]+$")


def web_dir():
    # PyInstaller unpacks bundled data under sys._MEIPASS.
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) if base else Path(__file__).resolve().parent.parent) / "web"


class ApiError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


class App:
    def __init__(self):
        self.config = config.load()
        self.db = Database()
        self.token = secrets.token_urlsafe(24)
        self.httpd = None

    # --- API handlers -------------------------------------------------------

    def _tns_state(self):
        path = tns.resolve(self.config["tns_path"]) or tns.find()
        return {"path": path, "aliases": tns.read_aliases(path) if path else []}

    def state(self, _body):
        return {
            "version": __version__,
            "config": self.config,
            "tns": self._tns_state(),
            "connection": self.db.info,
        }

    def set_tns(self, body):
        path = tns.resolve(str(body.get("path", "")))
        if not path:
            raise ApiError("No tnsnames.ora was found at that location.")
        self.config["tns_path"] = path
        config.save(self.config)
        return self._tns_state()

    def connect(self, body):
        mode = "basic" if body.get("mode") == "basic" else "tns"
        user = str(body.get("user", "")).strip()
        password = str(body.get("password", ""))
        owner = str(body.get("owner", "")).strip() or "SIEBEL"
        if not user or not password:
            raise ApiError("Enter your database user ID and password.")
        params = {"mode": mode, "user": user, "password": password, "owner": owner}
        if mode == "tns":
            tns_path = self._tns_state()["path"]
            alias = str(body.get("alias", "")).strip()
            if not tns_path or not alias:
                raise ApiError("Choose a database from tnsnames.ora.")
            params.update(alias=alias, tns_path=tns_path)
        else:
            host = str(body.get("host", "")).strip()
            service = str(body.get("service", "")).strip()
            try:
                port = int(body.get("port") or 1521)
            except (TypeError, ValueError):
                raise ApiError("Port must be a number.")
            if not host or not service:
                raise ApiError("Enter the host and service name.")
            params.update(host=host, port=port, service=service)
        try:
            info = self.db.connect(**params)
        except DbError as exc:
            raise ApiError(str(exc), **exc.extra)
        self.config.update({k: v for k, v in params.items() if k in config.DEFAULTS and k != "tns_path"})
        self.config["owner"] = info["owner"]
        config.save(self.config)
        return {"connection": info}

    def disconnect(self, _body):
        self.db.disconnect()
        return {"connection": None}

    def _repo(self, call, *args):
        if not self.db.connected:
            raise ApiError("Connect to the database first.", status=409)
        try:
            return call(self.db, *args)
        except DbError as exc:
            raise ApiError(str(exc))

    def workspaces(self, _body):
        return {"workspaces": self._repo(repo.workspaces)}

    def versions(self, body):
        workspace = str(body.get("ws", "")).strip()
        if not workspace:
            raise ApiError("Choose a workspace.")
        return {"versions": self._repo(repo.versions, workspace)}

    def save_report(self, body):
        objects = body.get("objects")
        if not isinstance(objects, list) or not isinstance(body.get("counts"), dict):
            raise ApiError("There is no comparison result to save.")
        result = {
            "meta": body.get("meta") or [],
            "sides": body.get("sides") or ["Before", "After"],
            "counts": body["counts"],
            "objects": objects,
        }
        try:
            path = report.save(web_dir(), result, str(body.get("label", "")))
        except OSError as exc:
            raise ApiError(f"The report could not be written. ({exc})")
        if body.get("open", True):
            webbrowser.open(path.as_uri())
        return {"path": str(path)}

    def quit(self, _body):
        self.db.disconnect()
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()
        return {"stopped": True}

    ROUTES = {
        ("GET", "/api/state"): state,
        ("POST", "/api/tns"): set_tns,
        ("POST", "/api/connect"): connect,
        ("POST", "/api/disconnect"): disconnect,
        ("GET", "/api/workspaces"): workspaces,
        ("GET", "/api/versions"): versions,
        ("POST", "/api/report"): save_report,
        ("POST", "/api/quit"): quit,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "SiebDiff"
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

    def _handle(self, method):
        app = self.server.app
        # Rejecting unknown Host values stops other websites reaching this server through DNS tricks.
        if self.headers.get("Host") not in self.server.allowed_hosts:
            return self._json(403, {"error": "Forbidden"})
        url = urlsplit(self.path)
        path = url.path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not path.startswith("/api/"):
            return self._static(path) if method == "GET" else self._json(405, {"error": "Method not allowed"})
        if not secrets.compare_digest(self.headers.get("X-SiebDiff-Token", ""), app.token):
            return self._json(403, {"error": "Forbidden"})
        route = App.ROUTES.get((method, path))
        if route is None:
            return self._json(404, {"error": "Not found"})
        try:
            body = json.loads(raw) if raw else dict(parse_qsl(url.query))
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"error": "Invalid request"})
        try:
            self._json(200, route(app, body))
        except ApiError as exc:
            self._json(exc.status, {"error": str(exc), **exc.extra})

    def _static(self, path):
        name = "index.html" if path == "/" else path.lstrip("/")
        file = web_dir() / name
        if not _STATIC_NAME.match(name) or file.suffix not in _TYPES or not file.is_file():
            return self._json(404, {"error": "Not found"})
        data = file.read_bytes()
        if name == "index.html":
            data = data.replace(b"{{TOKEN}}", self.server.app.token.encode("ascii"))
        self._send(200, data, _TYPES[file.suffix])

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def create(app, port=0):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.app = app
    actual = httpd.server_address[1]
    httpd.allowed_hosts = {f"127.0.0.1:{actual}", f"localhost:{actual}"}
    app.httpd = httpd
    return httpd
