"""Starting pipelines for the branches a push moved.

Grod runs `git receive-pack` itself, both over HTTP and over SSH, so it can
compare the branch tips before and after a push instead of installing a hook
that would have to call back into the platform.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.ci import config as pipeline_config
from grod.ci import service
from grod.repositories.models import Project
from grod.repositories.pushes import moved_branches

logger = logging.getLogger(__name__)


async def after_push(
    session: AsyncSession,
    *,
    project: Project,
    before: dict[str, str],
    after: dict[str, str],
    pusher: User | None,
) -> list[int]:
    """Start a pipeline for every branch the push moved.

    A branch without the pipeline file, or with one the platform cannot read,
    simply gets no pipeline: a push must never fail because of the build.
    """
    started: list[int] = []

    for branch, commit in moved_branches(before, after).items():
        try:
            run = await service.start(
                session, project=project, ref=branch, commit=commit, triggered_by=pusher
            )
        except service.NoConfigError:
            continue
        except pipeline_config.ConfigError:
            logger.warning(
                "Project %s has a pipeline file that cannot be read at %s", project.id, commit
            )
            continue
        started.append(run.pipeline.number)

    return started
