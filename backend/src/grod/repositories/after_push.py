"""Everything the platform does once a push has been accepted."""

from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.ci import triggers as ci
from grod.pages import triggers as pages
from grod.repositories.models import Project
from grod.repositories.pushes import branch_tips
from grod.scanning import triggers as scanning


async def handle(
    session: AsyncSession, *, project: Project, before: dict[str, str], pusher: User | None
) -> None:
    """Tell the modules that care which branches the push moved.

    None of them may break a push, so each takes the snapshot of the tips
    and answers for itself what to do with it.
    """
    after = await branch_tips(project)
    await ci.after_push(session, project=project, before=before, after=after, pusher=pusher)
    await pages.after_push(session, project=project, before=before, after=after)
    await scanning.after_push(session, project=project, before=before, after=after)
