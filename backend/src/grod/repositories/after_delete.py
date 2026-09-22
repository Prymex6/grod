"""What is left to clean up when a project goes away.

The rows go by themselves — every table points at the project with ON DELETE
CASCADE — but files do not. They are swept here, in one place, so a new module
that keeps files has one obvious spot to add itself to instead of leaving them
behind on every delete.
"""

import asyncio
import shutil
from pathlib import Path
from uuid import UUID

from grod.config import get_settings


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


async def handle(project_id: UUID) -> None:
    """Take the files of one project off the disk."""
    settings = get_settings()
    for folder in (
        settings.packages_path / str(project_id),
        settings.registry_path / str(project_id),
        settings.pages_path / str(project_id),
    ):
        await asyncio.to_thread(_remove_tree, folder)
