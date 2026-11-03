"""Local HTTP adapter (standard library). Loopback only; no outbound requests.

`App.handle()` is a pure request -> response function so tests can exercise every route
without sockets. `serve()` wraps it in a ThreadingHTTPServer bound to a loopback address.
"""
import argparse
import ipaddress
import json
import mimetypes
import socket
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .service import ReviewService, ServiceError, pdf_parser
from .store import Store

STATIC = Path(__file__).resolve().parent / "static"
MAX_JSON = 512 * 1024
MAX_UPLOAD = 5 * 1024 * 1024
CSRF_HEADER = "X-TDS-Review"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                    "Cross-Origin-Opener-Policy": "same-origin",
                    "Cross-Origin-Resource-Policy": "same-origin"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}


class Response:
    def __init__(self, status, body=b"", content_type="application/json", headers=None):
        self.status = status
        self.body = body
        self.headers = {"Content-Type": content_type, **SECURITY_HEADERS, **(headers or {})}


def json_response(status, value, headers=None):
    body = json.dumps(value, ensure_ascii=True).encode("utf-8")
    return Response(status, body, "application/json", {"Cache-Control": "no-store", **(headers or {})})


def error(status, message):
    return json_response(status, {"error": message})


class App:
    def __init__(self, data_dir, port=8765):
        self.store = Store(data_dir)
        self.service = ReviewService(self.store)
        self.port = port

    def allowed_host(self, host):
        if not host:
            return False
        names = {"127.0.0.1", "localhost", "[::1]"}
        return host in names or host in {"{}:{}".format(n, self.port) for n in names}

    def handle(self, method, raw_path, headers, body=b""):
        headers = {k.lower(): v for k, v in headers.items()}
        if not self.allowed_host(headers.get("host")):
            # DNS-rebinding defence: only loopback host names are served.
            return error(421, "Unrecognized host")
        parsed = urllib.parse.urlsplit(raw_path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if method == "POST" and headers.get(CSRF_HEADER.lower()) != "1":
            return error(403, "Missing request header")
        try:
            if path.startswith("/api/"):
                return self.api(method, path[5:].strip("/").split("/"), query, headers, body)
            if method != "GET":
                return error(405, "Method not allowed")
            return self.static(path)
        except ServiceError as exc:
            return error(exc.status, exc.message)

    def api(self, method, parts, query, headers, body):
        service = self.service
        if parts == ["health"] and method == "GET":
            return json_response(200, dict(status="ok", pdf_parser=pdf_parser(), model_calls="DISABLED",
                                           bound_to="loopback", data_store="local SQLite (append-only)"))
        if parts == ["samples"] and method == "GET":
            return json_response(200, service.public_samples())
        if len(parts) == 3 and parts[0] == "samples" and parts[2] == "cases" and method == "POST":
            return json_response(201, service.create_sample_case(parts[1]))
        if parts == ["documents"] and method == "POST":
            if headers.get("content-type", "").split(";")[0] not in ("application/pdf", "application/octet-stream"):
                return error(415, "Only PDF files can be reviewed")
            name = urllib.parse.unquote(headers.get("x-filename", ""))
            return json_response(201, service.upload(name, body))
        if len(parts) == 3 and parts[0] == "documents" and parts[2] == "file" and method == "GET":
            return self.document_file(parts[1])
        if parts == ["cases"]:
            if method == "GET":
                return json_response(200, service.list_cases())
            if method == "POST":
                return json_response(201, service.create_case(self.json_body(body)))
        if len(parts) >= 2 and parts[0] == "cases":
            case_id = parts[1]
            if len(parts) == 2 and method == "GET":
                run = query.get("run", [None])[0]
                return json_response(200, service.case_view(case_id, run))
            if parts[2:] == ["events"] and method == "POST":
                return json_response(201, service.record_event(case_id, self.json_body(body)))
            if parts[2:] == ["runs"] and method == "POST":
                return json_response(201, service.rerun(case_id, self.json_body(body)))
            if parts[2:] == ["export"] and method == "GET":
                export = service.export(case_id)
                name = "tds-review-{}.json".format(export["case"]["reference"])
                safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
                return json_response(200, export, {"Content-Disposition": 'attachment; filename="{}"'.format(safe)})
        return error(404, "Not found")

    @staticmethod
    def json_body(body):
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise ServiceError(400, "Request body must be JSON") from None

    def document_file(self, digest):
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return error(404, "Not found")
        state, path = self.store.verify_document(digest)
        if state != "VERIFIED":
            # Never display a file whose bytes differ from the analysed hash.
            return error(409, "Stored file failed its integrity check ({})".format(state))
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            return error(415, "Not a PDF")
        record = self.store.document(digest)
        safe = "".join(c if c.isalnum() or c in "-_. ()" else "_" for c in record["name"])
        return Response(200, data, "application/pdf", {
            "Content-Disposition": 'inline; filename="{}"'.format(safe), "Cache-Control": "no-store",
            "Content-Security-Policy": "frame-ancestors 'self'", "X-Frame-Options": "SAMEORIGIN"})

    def static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        if STATIC not in target.parents or not target.is_file():
            return error(404, "Not found")
        content_type = TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        headers = {"Cache-Control": "no-cache"}
        if target.suffix == ".html":
            headers["Content-Security-Policy"] = CSP
            headers["X-Frame-Options"] = "DENY"
        return Response(200, target.read_bytes(), content_type, headers)


def make_handler(app, request_timeout=20):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TDSReview/1"
        sys_version = ""
        timeout = request_timeout  # A client that stalls mid-request cannot hold a thread forever.

        def _dispatch(self, method):
            length = self.headers.get("Content-Length")
            body = b""
            if method == "POST":
                try:
                    size = int(length)
                except (TypeError, ValueError):
                    return self._send(error(411, "Content-Length required"))
                limit = MAX_UPLOAD + 1 if self.path.startswith("/api/documents") else MAX_JSON
                if size < 0 or size > limit:
                    return self._send(error(413, "Request is too large (PDF limit 5 MiB)"))
                body = self.rfile.read(size)
            try:
                response = app.handle(method, self.path, dict(self.headers.items()), body)
            except Exception:  # Never leak tracebacks or document strings to the client.
                response = error(500, "Unexpected server error; the review store was not changed by this request")
            self._send(response)

        def _send(self, response):
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._send(error(405, "Method not allowed"))

        do_DELETE = do_PATCH = do_PUT

        def log_message(self, fmt, *args):
            sys.stderr.write("  {} {}\n".format(self.command, self.path.split("?")[0]))

    return Handler


def loopback(host):
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
        return all(ipaddress.ip_address(info[4][0]).is_loopback for info in infos)
    except (socket.gaierror, ValueError):
        return False


def serve(host="127.0.0.1", port=8765, data_dir="local_data", open_browser=False):
    if not loopback(host):
        raise SystemExit("Refusing to bind to a non-loopback address. This prototype serves this computer only.")
    app = App(data_dir, port)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    url = "http://127.0.0.1:{}/".format(server.server_address[1])
    print("TDS Evidence Review is running at " + url)
    print("Data folder: " + str(app.store.data_dir) + "  (kept out of Git)")
    print("Offline: no model or network calls. Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local TDS evidence review workspace (offline).")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback address only (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default="local_data", help="Local folder for uploads and the review database")
    parser.add_argument("--open", action="store_true", help="Open the app in the default browser")
    args = parser.parse_args(argv)
    serve(args.host, args.port, args.data_dir, args.open)


if __name__ == "__main__":
    main()
