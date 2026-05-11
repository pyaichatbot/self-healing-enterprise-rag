from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http method signature
        if self.path.startswith("/repos"):
            payload = {
                "items": [
                    {"repo": "mock-org/mock-rag", "path": "docs/architecture.md", "default_branch": "main"},
                ],
                "next_cursor": None,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args):  # noqa: A003
        _ = format, args
        return


class _ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run mock connector provider HTTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18999)
    args = parser.parse_args()
    server = _ThreadingServer((args.host, args.port), _Handler)
    print(f"http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
