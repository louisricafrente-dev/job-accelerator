"""Private queue callback for the API-directory deployment."""
import asyncio
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root not in sys.path:
    sys.path.insert(0, root)

from vercel.queue import accept_and_handle, subscribe, SanitizedName
from src.cloud_sync import TOPIC
from src.cloud_worker import sync_jobs

_groups = {"job-sync-worker"}
_group_lock = threading.Lock()


async def handle_delivery(body, headers):
    # API-directory triggers derive their own group, supplied by Vercel's private delivery.
    group = next((v for k, v in headers.items() if k.lower() == "ce-vqsconsumergroup"), "")
    if not group:
        raise ValueError("Missing queue consumer group")
    with _group_lock:
        if group not in _groups:
            subscribe(sync_jobs, topic=TOPIC, consumer_group=SanitizedName(group))
            _groups.add(group)
    await accept_and_handle(body, headers, lease_duration=240)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        asyncio.run(handle_delivery(body, dict(self.headers)))
        self.send_response(204)
        self.end_headers()
