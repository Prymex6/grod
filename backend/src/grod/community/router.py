"""Public profiles: what anybody may see about an account."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.dependencies import OptionalUser
from grod.accounts.schemas import ApiModel
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.repositories import service as projects
from grod.repositories import views
from grod.repositories.schemas import ProjectView

router = APIRouter(prefix="/users", tags=["community"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


class ProfileView(ApiModel):
    """An account as its public page shows it."""

    login: str
    display_name: str
    created_at: datetime
    projects: list[ProjectView]
    stars_given: int
    stars_received: int


@router.get("/{login}")
async def read_profile(
    login: str, db: DbSession, user: OptionalUser, settings: SettingsDependency
) -> ProfileView:
    """Return the profile of an account with the projects the caller may see."""
    account = await accounts.find_by_login(db, login)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such account")

    visible = await projects.list_visible_of(db, owner=account, viewer=user)
    found = [
        projects.ProjectWithOwner(project=project, owner=account, namespace=account.login)
        for project in visible
    ]
    # Rights differ from project to project here, so each one is asked about.
    shown = await views.project_views(db, found, user, settings, None)

    return ProfileView(
        login=account.login,
        display_name=account.display_name,
        created_at=account.created_at,
        projects=shown,
        stars_given=await projects.count_stars_given(db, user=account),
        stars_received=sum(project.stars for project in shown),
    )
