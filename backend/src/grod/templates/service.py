"""Putting something out on the fair, and taking something off it.

Taking always makes something of the taker's own: a template becomes their
project, an application becomes their container. Nothing stays shared, so an
offering that is later taken down leaves what people made from it alone.
"""

import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.repositories.models import Project
from grod.templates.models import SLUG_PATTERN, Offering, OfferingKind

SLUG_RULE = re.compile(SLUG_PATTERN)
CATALOG_LIMIT = 100


class InvalidSlugError(Exception):
    """An offering is addressed like a project."""


class SlugTakenError(Exception):
    """Something already stands on the fair under that address."""


class NothingToCopyError(Exception):
    """A template was published from a project that has no code in it."""


async def list_offerings(
    session: AsyncSession, *, kind: OfferingKind | None = None, limit: int = CATALOG_LIMIT
) -> list[Offering]:
    """Return what is on the fair, the most taken first."""
    query = select(Offering).where(Offering.published.is_(True))
    if kind is not None:
        query = query.where(Offering.kind == kind)
    result = await session.execute(
        query.order_by(Offering.taken.desc(), Offering.created_at.desc()).limit(limit)
    )
    return list(result.scalars())


async def list_of_owner(session: AsyncSession, *, owner_id: UUID) -> list[Offering]:
    """Return what one account put out, published or not."""
    result = await session.execute(
        select(Offering).where(Offering.owner_id == owner_id).order_by(Offering.created_at.desc())
    )
    return list(result.scalars())


async def find(session: AsyncSession, slug: str) -> Offering | None:
    """Return one offering by its address."""
    result = await session.execute(select(Offering).where(Offering.slug == slug.lower()))
    return result.scalar_one_or_none()


async def publish(
    session: AsyncSession,
    *,
    owner: User,
    slug: str,
    title: str,
    description: str,
    kind: OfferingKind,
    project: Project | None = None,
    branch: str = "",
    image: str = "",
) -> Offering:
    """Put something out for everybody on this instance."""
    address = slug.lower()
    if SLUG_RULE.match(address) is None:
        raise InvalidSlugError(slug)

    offering = Offering(
        owner_id=owner.id,
        project_id=project.id if project else None,
        kind=kind,
        slug=address,
        title=title,
        description=description,
        branch=branch,
        image=image,
    )
    session.add(offering)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise SlugTakenError(slug) from error
    return offering


async def set_published(session: AsyncSession, *, offering: Offering, published: bool) -> Offering:
    """Take an offering off the fair, or put it back."""
    offering.published = published
    await session.commit()
    return offering


async def delete(session: AsyncSession, *, offering: Offering) -> None:
    """Remove an offering. What people made from it stays theirs."""
    await session.delete(offering)
    await session.commit()


async def count_taken(session: AsyncSession, *, offering: Offering) -> int:
    """Write down that somebody took it, and return the new count."""
    offering.taken += 1
    await session.commit()
    return offering.taken


async def popular(session: AsyncSession) -> int:
    """How many offerings stand on the fair right now."""
    result = await session.execute(
        select(func.count(Offering.id)).where(Offering.published.is_(True))
    )
    return int(result.scalar_one())
