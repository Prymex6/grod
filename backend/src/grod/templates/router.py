"""Endpoints of Jarmark: the catalog, and taking something off it."""

import contextlib
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.schemas import ApiModel
from grod.apps import service as applications
from grod.apps.models import DEFAULT_CPUS, DEFAULT_MEMORY_MB
from grod.collaboration.router import readable
from grod.db import get_db_session
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.repositories import git
from grod.repositories import service as projects
from grod.repositories.models import Visibility
from grod.templates import service
from grod.templates.models import (
    DESCRIPTION_MAX_LENGTH,
    IMAGE_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    SLUG_PATTERN,
    TITLE_MAX_LENGTH,
    Offering,
    OfferingKind,
)

router = APIRouter(prefix="/market", tags=["templates"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such offering"
NOT_YOURS_DETAIL = "This offering is not yours"


class OfferingPublish(ApiModel):
    """Something to put out on the fair."""

    slug: str = Field(pattern=SLUG_PATTERN, min_length=2, max_length=SLUG_MAX_LENGTH)
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH)
    kind: OfferingKind = OfferingKind.TEMPLATE
    # A template says which project and branch it copies.
    owner: str = ""
    project: str = ""
    branch: str = ""
    # An application says which image it runs.
    image: str = Field(default="", max_length=IMAGE_MAX_LENGTH)


class OfferingView(ApiModel):
    """One offering as the catalog shows it."""

    slug: str
    title: str
    description: str
    kind: OfferingKind
    author: str
    branch: str
    image: str
    published: bool
    taken: int
    created_at: datetime


class TakeTemplate(ApiModel):
    """Where to put the project made from a template."""

    slug: str = Field(pattern=SLUG_PATTERN, min_length=1, max_length=SLUG_MAX_LENGTH)
    name: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    visibility: Visibility = Visibility.PRIVATE


class TakeApplication(ApiModel):
    """What to call the application made from an offering."""

    name: str = Field(min_length=3, max_length=SLUG_MAX_LENGTH)


class TakenView(ApiModel):
    """What the taker now has of their own."""

    kind: OfferingKind
    address: str


async def _view(db: AsyncSession, offering: Offering) -> OfferingView:
    author = await accounts.find_by_id(db, offering.owner_id)
    return OfferingView(
        slug=offering.slug,
        title=offering.title,
        description=offering.description,
        kind=offering.kind,
        author=author.login if author else "",
        branch=offering.branch,
        image=offering.image,
        published=offering.published,
        taken=offering.taken,
        created_at=offering.created_at,
    )


async def _found(db: AsyncSession, slug: str) -> Offering:
    offering = await service.find(db, slug)
    if offering is None or not offering.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return offering


@router.get("")
async def list_offerings(
    db: DbSession, user: OptionalUser, kind: OfferingKind | None = None
) -> list[OfferingView]:
    """Return what stands on the fair. Everybody may look, signed in or not."""
    del user
    found = await service.list_offerings(db, kind=kind)
    return [await _view(db, offering) for offering in found]


@router.get("/mine")
async def list_mine(db: DbSession, user: CurrentUser) -> list[OfferingView]:
    """Return what the signed-in account put out, taken down ones included."""
    found = await service.list_of_owner(db, owner_id=user.id)
    return [await _view(db, offering) for offering in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def publish_offering(body: OfferingPublish, db: DbSession, user: CurrentUser) -> OfferingView:
    """Put a template or an application out for everybody on this instance."""
    project = None
    if body.kind == OfferingKind.TEMPLATE:
        if not body.owner or not body.project:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="A template names the project it copies"
            )
        project, access = await readable(db, body.owner, body.project, user)
        # Publishing somebody else's project as your own template is not sharing.
        if not access.manage:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_YOURS_DETAIL)
    elif not body.image:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="An application names the image it runs"
        )

    try:
        offering = await service.publish(
            db,
            owner=user,
            slug=body.slug,
            title=body.title,
            description=body.description,
            kind=body.kind,
            project=project,
            branch=body.branch or (project.default_branch if project else ""),
            image=body.image,
        )
    except service.InvalidSlugError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid address") from None
    except service.SlugTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Something already stands under that address"
        ) from None
    return await _view(db, offering)


@router.get("/{slug}")
async def read_offering(slug: str, db: DbSession, user: OptionalUser) -> OfferingView:
    """Return one offering."""
    del user
    return await _view(db, await _found(db, slug))


@router.post("/{slug}/take-template")
async def take_template(
    slug: str, body: TakeTemplate, db: DbSession, user: CurrentUser
) -> TakenView:
    """Make a project of your own out of a template."""
    offering = await _found(db, slug)
    if offering.kind != OfferingKind.TEMPLATE or offering.project_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This offering is not a template")

    source = await projects.find_by_id(db, offering.project_id)
    if source is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The template is gone")

    try:
        made = await projects.create(
            db,
            owner=user,
            slug=body.slug,
            name=body.name,
            description=offering.description[:DESCRIPTION_MAX_LENGTH],
            visibility=body.visibility,
        )
    except projects.InvalidSlugError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid address") from None
    except projects.SlugAlreadyUsedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a project at that address"
        ) from None

    # A template with nothing in it leaves an empty project, not a broken one.
    with contextlib.suppress(git.GitError):
        await git.copy_from(made.id, source.id, branch=offering.branch)

    await service.count_taken(db, offering=offering)
    return TakenView(kind=offering.kind, address=f"{user.login}/{made.slug}")


@router.post("/{slug}/take-application")
async def take_application(
    slug: str, body: TakeApplication, db: DbSession, user: CurrentUser
) -> TakenView:
    """Make an application of your own out of an offering."""
    offering = await _found(db, slug)
    if offering.kind != OfferingKind.APPLICATION or not offering.image:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This offering is not an application")

    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=quotas.Thing.APPLICATION)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        made = await applications.create(
            db,
            owner=user,
            name=body.name,
            image=offering.image,
            memory_mb=DEFAULT_MEMORY_MB,
            cpus=float(DEFAULT_CPUS),
        )
    except applications.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except applications.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have an application with that name"
        ) from None

    await service.count_taken(db, offering=offering)
    return TakenView(kind=offering.kind, address=made.name)


@router.patch("/{slug}")
async def change_offering(
    slug: str, published: bool, db: DbSession, user: CurrentUser
) -> OfferingView:
    """Take an offering off the fair, or put it back."""
    offering = await service.find(db, slug)
    if offering is None or offering.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return await _view(db, await service.set_published(db, offering=offering, published=published))


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offering(slug: str, db: DbSession, user: CurrentUser) -> None:
    """Remove an offering. What people made from it stays theirs."""
    offering = await service.find(db, slug)
    if offering is None or offering.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    await service.delete(db, offering=offering)
