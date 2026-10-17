import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import SessionFactory
from app.worker import claim_next_job, notify_assignee, process_job


async def run() -> None:
    handlers = {"notify_assignee": notify_assignee}
    while True:
        async with SessionFactory() as session:
            job = await claim_next_job(session)
            if job is not None:
                await process_job(session, job, handlers)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
