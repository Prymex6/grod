"""Building the project view, shared by the project pages and the profiles."""

from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.config import Settings
from grod.repositories import git, service
from grod.repositories.models import Project
from grod.repositories.schemas import ProjectView


def _clone_url(settings: Settings, namespace: str, slug: str) -> str:
    return f"{str(settings.public_url).rstrip('/')}/{namespace}/{slug}.git"


async def project_view(
    project: Project,
    namespace: str,
    settings: Settings,
    access: service.Access,
    stars: int = 0,
    starred: bool = False,
) -> ProjectView:
    return ProjectView.model_validate(
        {
            "id": project.id,
            "owner_login": namespace,
            "slug": project.slug,
            "name": project.name,
            "description": project.description,
            "visibility": project.visibility,
            "default_branch": project.default_branch,
            "empty": await git.is_empty(project.id),
            "clone_url": _clone_url(settings, namespace, project.slug),
            "created_at": project.created_at,
            "stars": stars,
            "starred": starred,
            "access": {
                "read": access.read,
                "write": access.write,
                "manage": access.manage,
                "own": access.own,
            },
        }
    )


async def project_views(
    db: AsyncSession,
    found: list[service.ProjectWithOwner],
    user: User | None,
    settings: Settings,
    access: service.Access | None,
) -> list[ProjectView]:
    """Turn projects into views, counting their stars in one go.

    A listing where every project grants the same rights passes them in;
    a mixed one passes None and each project is asked about separately.
    """
    ids = [item.project.id for item in found]
    counts = await service.star_counts(db, project_ids=ids)
    mine = await service.starred_by(db, user=user, project_ids=ids)
    return [
        await project_view(
            item.project,
            item.namespace,
            settings,
            access
            if access is not None
            else await service.access_of(db, project=item.project, user=user),
            stars=counts.get(item.project.id, 0),
            starred=item.project.id in mine,
        )
        for item in found
    ]
