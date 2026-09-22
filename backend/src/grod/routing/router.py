"""Endpoints for the routes, and the door they stand in front of."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.config import Settings, get_settings
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor, OptionalActor
from grod.iam.models import ResourceKind, Role
from grod.routing import service
from grod.routing.models import (
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    TARGET_MAX_LENGTH,
    Route,
    RouteTarget,
)

router = APIRouter(prefix="/routes", tags=["routing"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

NOT_FOUND_DETAIL = "No such route"
FORWARDED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class RouteCreate(ApiModel):
    """A new route."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)
    target_kind: RouteTarget = RouteTarget.APPLICATION
    target: str = Field(min_length=1, max_length=TARGET_MAX_LENGTH)
    public: bool = True


class RouteView(ApiModel):
    """A route as the console shows it."""

    id: str
    name: str
    target_kind: RouteTarget
    target: str
    public: bool
    url: str
    created_at: datetime


def _view(route: Route, settings: Settings) -> RouteView:
    return RouteView(
        id=str(route.id),
        name=route.name,
        target_kind=route.target_kind,
        target=route.target,
        public=route.public,
        url=f"{str(settings.public_url).rstrip('/')}/-/traffic/{route.name}/",
        created_at=route.created_at,
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> Route:
    """Find a route this actor may do that much with."""
    route = await scope.allowed(
        db, Route, actor=actor, kind=ResourceKind.ROUTE, name=name, needed=needed
    )
    if route is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return route


@router.get("")
async def list_routes(
    db: DbSession, actor: CurrentActor, settings: SettingsDependency
) -> list[RouteView]:
    """Return the routes the caller may see."""
    found = await scope.visible(db, Route, actor=actor, kind=ResourceKind.ROUTE)
    return [_view(route, settings) for route in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_route(
    body: RouteCreate, db: DbSession, user: CurrentUser, settings: SettingsDependency
) -> RouteView:
    """Create a route that points at an application or at an address."""
    try:
        route = await service.create(
            db,
            owner=user,
            name=body.name,
            target_kind=body.target_kind,
            target=body.target,
            public=body.public,
        )
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A route with that name already exists"
        ) from None
    return _view(route, settings)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Take a route down."""
    route = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, route=route)


# The routes themselves answer outside the API, under their own prefix.
traffic_router = APIRouter(prefix="/-/traffic", tags=["routing"])


@traffic_router.api_route("/{name}", methods=FORWARDED_METHODS)
@traffic_router.api_route("/{name}/{path:path}", methods=FORWARDED_METHODS)
async def forward_call(
    name: str, request: Request, db: DbSession, actor: OptionalActor, path: str = ""
) -> Response:
    """Hand the call over to whatever the route points at."""
    route = await service.find(db, name)
    if route is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    if not route.public:
        # A private route must look exactly like one that is not there, so the
        # check below answers with the same 404 when nobody may go through.
        if actor is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
        await _allowed(db, name, actor, Role.OPERATOR)

    try:
        base_url = await service.resolve(db, route=route)
        answer = await service.forward(
            base_url=base_url,
            method=request.method,
            path=path,
            query=request.url.query,
            headers=dict(request.headers),
            body=await request.body(),
        )
    except service.NowhereToGoError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Nothing answers behind this route"
        ) from None

    return Response(content=answer.body, status_code=answer.status, headers=answer.headers)
