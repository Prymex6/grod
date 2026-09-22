"""Looking through a repository again once somebody has pushed to it."""

from sqlalchemy.ext.asyncio import AsyncSession

from grod.repositories import git
from grod.repositories.models import Project
from grod.scanning import service


async def after_push(
    session: AsyncSession, *, project: Project, before: dict[str, str], after: dict[str, str]
) -> None:
    """Scan the default branch when the push moved it, and not otherwise.

    A scan may never break a push: whatever goes wrong while reading the
    repository is left here, because the code is already in.
    """
    branch = project.default_branch
    tip = after.get(branch)
    if tip is None or tip == before.get(branch):
        return

    try:
        await service.scan(session, project=project, ref=branch)
    except git.GitError:
        return
