"""Publishing a site again when its branch moves."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from grod.pages import service
from grod.repositories.models import Project
from grod.repositories.pushes import moved_branches

logger = logging.getLogger(__name__)


async def after_push(
    session: AsyncSession, *, project: Project, before: dict[str, str], after: dict[str, str]
) -> bool:
    """Publish the site again when the push moved the branch it is built from.

    A site that cannot be published simply stays as it was: a push must never
    fail because of the site build.
    """
    site = await service.find(session, project=project)
    if site is None or not site.enabled:
        return False
    if site.branch not in moved_branches(before, after):
        return False

    try:
        await service.publish(session, project=project, site=site)
    except service.NothingToPublishError:
        logger.warning("Project %s has no %s folder on %s", project.id, site.directory, site.branch)
        return False
    return True
