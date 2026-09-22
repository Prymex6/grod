"""The loop that looks at the watched addresses while the platform runs."""

import asyncio
import contextlib
import logging

from grod.db import get_session_factory
from grod.monitoring import service

logger = logging.getLogger(__name__)

# How often the loop wakes up to see whether anything is due.
TICK_SECONDS = 15.0


async def _tick() -> None:
    """Run every check whose time has come."""
    async with get_session_factory()() as session:
        for check in await service.due_checks(session):
            try:
                await service.run_check(session, check=check)
            except Exception:
                # One bad address must never stop the loop for the others.
                logger.exception("Check %s could not be run", check.id)


async def serve() -> None:
    """Keep looking until the task is cancelled."""
    while True:
        try:
            await _tick()
        except Exception:
            logger.exception("The watch loop stumbled")
        await asyncio.sleep(TICK_SECONDS)


def start() -> asyncio.Task[None]:
    """Start the loop in the background."""
    return asyncio.create_task(serve(), name="monitoring-watch")


async def stop(task: asyncio.Task[None]) -> None:
    """Stop the loop and wait for it to finish."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
