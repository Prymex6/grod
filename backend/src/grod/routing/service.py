"""Routes and handing a call over to what stands behind them."""

import re
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.apps import service as apps
from grod.apps.models import AppState
from grod.routing.models import NAME_PATTERN, Route, RouteTarget

NAME_RULE = re.compile(NAME_PATTERN)
FORWARD_TIMEOUT_SECONDS = 30.0
# Hop-by-hop headers belong to one connection and must not travel further.
SKIPPED_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


class InvalidNameError(Exception):
    """A route is named like a host name."""


class NameTakenError(Exception):
    """Another route already answers at that name."""


class NowhereToGoError(Exception):
    """The route points at something that is not running."""


@dataclass(frozen=True)
class Answer:
    """What came back from the other side."""

    status: int
    headers: dict[str, str]
    body: bytes


async def find(session: AsyncSession, name: str) -> Route | None:
    """Return the route with this name, if any."""
    result = await session.execute(select(Route).where(Route.name == name.lower()))
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    target_kind: RouteTarget,
    target: str,
    public: bool,
) -> Route:
    """Create a route. Names are unique across the whole instance."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    route = Route(
        owner_id=owner.id,
        name=address,
        target_kind=target_kind,
        target=target,
        public=public,
    )
    session.add(route)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return route


async def delete(session: AsyncSession, *, route: Route) -> None:
    """Take a route down."""
    await session.delete(route)
    await session.commit()


async def resolve(session: AsyncSession, *, route: Route) -> str:
    """Return the address the call is to be handed to."""
    if route.target_kind == RouteTarget.ADDRESS:
        return route.target.rstrip("/")

    owner = await session.get(User, route.owner_id)
    if owner is None:
        raise NowhereToGoError(route.target)

    application = await apps.find(session, owner=owner, name=route.target)
    if application is None or application.host_port is None:
        raise NowhereToGoError(route.target)
    if application.state != AppState.RUNNING:
        raise NowhereToGoError(route.target)
    return f"http://127.0.0.1:{application.host_port}"


async def forward(
    *,
    base_url: str,
    method: str,
    path: str,
    query: str,
    headers: dict[str, str],
    body: bytes,
) -> Answer:
    """Hand one call over and bring the answer back."""
    address = f"{base_url}/{path.lstrip('/')}" if path else base_url
    if query:
        address = f"{address}?{query}"

    passed = {name: value for name, value in headers.items() if name.lower() not in SKIPPED_HEADERS}

    async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT_SECONDS) as client:
        try:
            answer = await client.request(method, address, headers=passed, content=body or None)
        except httpx.HTTPError as error:
            raise NowhereToGoError(address) from error

    returned = {
        name: value for name, value in answer.headers.items() if name.lower() not in SKIPPED_HEADERS
    }
    return Answer(status=answer.status_code, headers=returned, body=answer.content)
