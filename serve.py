#!/usr/bin/env python3
"""Serve the CARTPAY DIGITAL HUB clone with local stand-ins for its backend.

The original page is a Next.js client component that reads its catalogue from
Supabase and posts enquiries to a serverless route. Both are replaced here:

    GET  /sb/rest/v1/products   -> products.json  (honours ?active=eq.true)
    GET  /api/orders            -> orders.json    (everything captured so far)
    POST /api/orders            -> appends to orders.json, returns
                                   {"success": true, "orderId": "NX-..."}

    python3 serve.py [port]     # default 8137
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRODUCTS = ROOT / "products.json"
ORDERS = ROOT / "orders.json"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):  # quieter than the default
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # preflight for the fetch() calls
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path.rstrip("/") == "/sb/rest/v1/products":
            rows = load_json(PRODUCTS, [])
            query = urllib.parse.parse_qs(parsed.query)
            if query.get("active") == ["eq.true"]:
                rows = [r for r in rows if r.get("active") is True]
            order = (query.get("order") or [""])[0]
            if order.startswith("name"):
                rows = sorted(rows, key=lambda r: r.get("name") or "", reverse=order.endswith(".desc"))
            self.send_json(rows)
            return
        if parsed.path == "/api/orders":
            self.send_json(load_json(ORDERS, []))
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/orders":
            self.send_json({"success": False, "error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.send_json({"success": False, "error": "invalid json"}, 400)
            return

        name = str(body.get("customerName") or "").strip()
        mobile = str(body.get("customerMobile") or "").strip()
        location = str(body.get("customerLocation") or "").strip()
        product_id = str(body.get("productId") or "").strip()
        if not name or not mobile or not product_id:
            self.send_json({"success": False, "error": "name, mobile and product are required"}, 400)
            return

        order_id = "CP-" + base64.b32encode(os.urandom(5)).decode().rstrip("=")
        orders = load_json(ORDERS, [])
        orders.append({
            "orderId": order_id,
            "customerName": name,
            "customerMobile": mobile,
            "customerLocation": location,
            "productId": product_id,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        ORDERS.write_text(json.dumps(orders, indent=2), encoding="utf-8")
        self.send_json({"success": True, "orderId": order_id})


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8137
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"CARTPAY clone on http://127.0.0.1:{port}/  (root: {ROOT})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
