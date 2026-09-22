"""Endpoints for the site of a project, and the server that shows it."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.schemas import ApiModel
from grod.collaboration.router import NOT_ALLOWED_DETAIL, readable
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.pages import service
from grod.pages.models import BRANCH_MAX_LENGTH, DEFAULT_DIRECTORY, DIRECTORY_MAX_LENGTH

router = APIRouter(prefix="/projects/{owner}/{slug}/site", tags=["pages"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

NOT_FOUND_DETAIL = "This project publishes no site"


class SiteConfigure(ApiModel):
    """Which branch and folder the site is built from."""

    branch: str = Field(min_length=1, max_length=BRANCH_MAX_LENGTH)
    directory: str = Field(default=DEFAULT_DIRECTORY, max_length=DIRECTORY_MAX_LENGTH)
    enabled: bool = True


class SiteView(ApiModel):
    """The site of a project as the console shows it."""

    branch: str
    directory: str
    enabled: bool
    published_commit: str | None
    published_at: datetime | None
    url: str


def _url(settings: Settings, owner: str, slug: str) -> str:
    """The address a visitor opens to see the site."""
    return f"{str(settings.public_url).rstrip('/')}/-/pages/{owner}/{slug}/"


def _view(site: service.Site, settings: Settings, owner: str, slug: str) -> SiteView:
    return SiteView(
        branch=site.branch,
        directory=site.directory,
        enabled=site.enabled,
        published_commit=site.published_commit,
        published_at=site.published_at,
        url=_url(settings, owner, slug),
    )


@router.get("")
async def read_site(
    owner: str, slug: str, db: DbSession, user: OptionalUser, settings: SettingsDependency
) -> SiteView:
    """Return what the project publishes."""
    project, _ = await readable(db, owner, slug, user)
    site = await service.find(db, project=project)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return _view(site, settings, owner, slug)


@router.put("")
async def configure_site(
    owner: str,
    slug: str,
    body: SiteConfigure,
    db: DbSession,
    user: CurrentUser,
    settings: SettingsDependency,
) -> SiteView:
    """Set up the site, or change it. It takes the right to change the project."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    site = await service.configure(
        db,
        project=project,
        branch=body.branch,
        directory=body.directory,
        enabled=body.enabled,
    )
    return _view(site, settings, owner, slug)


@router.post("/publish")
async def publish_site(
    owner: str, slug: str, db: DbSession, user: CurrentUser, settings: SettingsDependency
) -> SiteView:
    """Publish the site again from the tip of its branch."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    site = await service.find(db, project=project)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)

    try:
        published = await service.publish(db, project=project, site=site)
    except service.NothingToPublishError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Nothing to publish at: {error}"
        ) from None
    return _view(published, settings, owner, slug)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def remove_site(owner: str, slug: str, db: DbSession, user: CurrentUser) -> None:
    """Take the site down and remove the files it published."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    site = await service.find(db, project=project)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    await service.remove(db, site=site)


# The sites themselves are served outside the API, under their own prefix.
serving_router = APIRouter(prefix="/-/pages", tags=["pages"])


@serving_router.get("/{owner}/{slug}")
@serving_router.get("/{owner}/{slug}/{path:path}")
async def serve_site(
    owner: str, slug: str, db: DbSession, user: OptionalUser, path: str = ""
) -> FileResponse:
    """Serve one file of a published site.

    A site is exactly as visible as the project behind it: the site of a
    private project asks for an account that may read that project.
    """
    project, _ = await readable(db, owner, slug, user)
    site = await service.find(db, project=project)
    if site is None or not site.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)

    found = service.resolve_file(project.id, path)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such page")
    return FileResponse(found.path, media_type=found.media_type)
