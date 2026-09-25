#!/usr/bin/env python3
"""Accept one-off file uploads from the Windows PC over the LAN (HTTP PUT).

Usage: scripts/receive-file.py [--port 8001] [--dir incoming] [--allow 192.168.1.77]

Prints the PowerShell line to run on the PC. Files land in --dir; the URL path must carry
the random token printed at start so stray requests are rejected. Stop with Ctrl-C.
"""
import argparse
import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024 * 1024


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--dir", default="incoming")
    ap.add_argument("--allow", action="append", default=[])
    args = ap.parse_args()
    dest = Path(args.dir)
    dest.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(12)

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            if args.allow and self.client_address[0] not in args.allow:
                self.send_error(403, "client not allowed")
                return
            parts = self.path.strip("/").split("/")
            if len(parts) != 2 or parts[0] != token or "/" in parts[1] or ".." in parts[1]:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BYTES:
                self.send_error(413, "bad length")
                return
            target = dest / parts[1]
            with open(target, "wb") as f:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"stored\n")
            print(f"received {target} ({length} bytes)", flush=True)

        def log_message(self, fmt, *a):
            sys.stderr.write(f"{self.client_address[0]} {fmt % a}\n")

    print(f"upload URL: http://<this-host>:{args.port}/{token}/<filename>", flush=True)
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
