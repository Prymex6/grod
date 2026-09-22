"""Turning a session cookie or a service token into the actor of a call."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import get_optional_user
from grod.accounts.models import User
from grod.db import get_db_session
from grod.iam import service
from grod.iam.service import Actor

NOBODY_DETAIL = "Sign in, or send a service token"
BEARER = "Bearer "


async def get_actor(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User | None, Depends(get_optional_user)],
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    """Return who is making this call: a person or a machine.

    A service token wins over a session, because an application that sends one
    means to act as itself even when a browser cookie happens to travel along.
    """
    del request
    if authorization is not None and authorization.startswith(BEARER):
        account = await service.authenticate_service(db, authorization.removeprefix(BEARER).strip())
        if account is not None:
            return service.actor_of_service(account)

    if user is not None:
        return service.actor_of_user(user)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOBODY_DETAIL)


CurrentActor = Annotated[Actor, Depends(get_actor)]


async def get_optional_actor(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User | None, Depends(get_optional_user)],
    authorization: Annotated[str | None, Header()] = None,
) -> Actor | None:
    """Return the actor, or None for a visitor who showed nothing."""
    try:
        return await get_actor(request, db, user, authorization)
    except HTTPException:
        return None


OptionalActor = Annotated[Actor | None, Depends(get_optional_actor)]
