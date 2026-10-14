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

from . import __version__, changes, compare, config, repo, report, tns
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
        self.scan = None
        self.job = None

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
        self._stop_scan()
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

    def parent_base(self, body):
        workspace = str(body.get("ws", "")).strip()
        if not workspace:
            raise ApiError("Choose a workspace.")
        return self._repo(repo.parent_base, workspace)

    def _stop_scan(self):
        if self.scan is not None:
            self.scan.cancel()
            self.scan = None
        if self.job is not None:
            self.job.cancel()
            self.job = None

    def start_changes(self, body):
        """Start looking for the objects changed in a workspace (optionally between two versions)."""
        workspace = str(body.get("ws", "")).strip()
        items = {item["id"]: item for item in self._repo(repo.workspaces)}
        if workspace not in items:
            raise ApiError("Choose a workspace.")
        depth, seen, parent = 0, {workspace}, items[workspace]["parent_id"]
        while parent in items and parent not in seen:  # stop on any loop in the parent chain
            seen.add(parent)
            depth, parent = depth + 1, items[parent]["parent_id"]
        after = upto = None
        if body.get("mode") == "versions":
            try:
                after, upto = sorted((int(body["from"]), int(body["to"])))
            except (KeyError, TypeError, ValueError):
                raise ApiError("Choose two versions.")
            if after == upto:
                raise ApiError("Choose two different versions.")
        self._stop_scan()
        self.scan = changes.Scan(self.db, workspace, depth, after, upto)
        return self.scan.progress()

    def changes_progress(self, _body):
        if self.scan is None:
            raise ApiError("No search is running.", status=409)
        return self.scan.progress()

    def cancel_changes(self, _body):
        self._stop_scan()
        return {"status": "cancelled"}

    def start_compare(self, body):
        """Read the selected objects on both sides. Left: older version, or the parent's base version."""
        workspace = str(body.get("ws", "")).strip()
        keys = body.get("objects")
        if not workspace:
            raise ApiError("Choose a workspace.")
        if not isinstance(keys, list) or not keys:
            raise ApiError("Select at least one object to compare.")
        if body.get("mode") == "versions":
            try:
                older, newer = sorted((int(body["from"]), int(body["to"])))
            except (KeyError, TypeError, ValueError):
                raise ApiError("Choose two versions.")
            chain_a = self._repo(compare.side_chain, workspace, older)
            chain_b = self._repo(compare.side_chain, workspace, newer)
        else:
            found = self._repo(repo.parent_base, workspace)
            if not found["latest"] or not found["base"]:
                raise ApiError("The parent version this workspace is based on could not be determined.")
            chain_a = self._repo(compare.side_chain, found["base"]["workspace_id"], found["base"]["number"])
            chain_b = self._repo(compare.side_chain, workspace, found["latest"]["number"])
        if self.job is not None:
            self.job.cancel()
        self.job = compare.Compare(self.db, [str(k) for k in keys], chain_a, chain_b)
        return self.job.progress()

    def compare_progress(self, _body):
        if self.job is None:
            raise ApiError("No comparison is running.", status=409)
        return self.job.progress()

    def cancel_compare(self, _body):
        if self.job is not None:
            self.job.cancel()
            self.job = None
        return {"status": "cancelled"}

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
        self._stop_scan()
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
        ("GET", "/api/parent-base"): parent_base,
        ("POST", "/api/changes"): start_changes,
        ("GET", "/api/changes"): changes_progress,
        ("POST", "/api/changes/cancel"): cancel_changes,
        ("POST", "/api/compare"): start_compare,
        ("GET", "/api/compare"): compare_progress,
        ("POST", "/api/compare/cancel"): cancel_compare,
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
