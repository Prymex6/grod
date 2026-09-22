"""The loop that moves the merge queues while the platform runs."""

import asyncio
import contextlib
import logging

from grod.collaboration import merge_queue
from grod.db import get_session_factory

logger = logging.getLogger(__name__)

# How often the queues are looked at. A pipeline takes longer than this, so
# waking up often costs nothing and makes the queue feel immediate.
TICK_SECONDS = 5.0


async def _tick() -> None:
    """Move every queue one step."""
    async with get_session_factory()() as session:
        await merge_queue.advance(session)


async def serve() -> None:
    """Keep moving the queues until the task is cancelled."""
    while True:
        try:
            await _tick()
        except Exception:
            logger.exception("The merge queue loop stumbled")
        await asyncio.sleep(TICK_SECONDS)


def start() -> asyncio.Task[None]:
    """Start the loop in the background."""
    return asyncio.create_task(serve(), name="merge-queue")


async def stop(task: asyncio.Task[None]) -> None:
    """Stop the loop and wait for it to finish."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
