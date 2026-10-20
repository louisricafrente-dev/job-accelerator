"""Private queue callback for the existing API-directory deployment."""
import asyncio
import os
import sys
from http.server import BaseHTTPRequestHandler

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)

from vercel.queue import accept_and_handle
from src.cloud_worker import sync_jobs


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        asyncio.run(accept_and_handle(body, dict(self.headers), lease_duration=240))
        self.send_response(204)
        self.end_headers()
