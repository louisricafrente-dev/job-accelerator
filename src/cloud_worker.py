"""Private Vercel Queues subscriber, independent of browser requests."""
import asyncio
import os
from vercel.queue import Message, subscribe
from src.cloud_sync import TOPIC, process_message


@subscribe(topic=TOPIC, consumer_group="job-sync-worker", max_concurrency=1, retry_after=60)
async def sync_jobs(message: Message[dict[str, object]]) -> None:
    from src.aggregator import Aggregator
    from src.database import init_db
    db_path = "/tmp/data/jobs.db"
    os.makedirs("/tmp/data", exist_ok=True)
    await asyncio.to_thread(init_db, db_path)
    if message.payload.get("kind") == "upwork_monitor":
        from src.upwork_monitor import process
        await process(db_path, message.payload)
        return
    await process_message(db_path, message.payload, Aggregator(db_path))
