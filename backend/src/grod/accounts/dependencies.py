"""FastAPI dependencies that turn a session cookie into an account."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service, sessions
from grod.accounts.models import User
from grod.config import Settings, get_settings
from grod.db import get_db_session

NOT_SIGNED_IN_DETAIL = "Not signed in"


def get_session_token(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> str:
    """Read the session token from the cookie, or refuse the request."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_SIGNED_IN_DETAIL)
    return token


SessionToken = Annotated[str, Depends(get_session_token)]


async def get_current_user(
    token: SessionToken,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Return the signed-in account behind the session cookie."""
    user_id = await sessions.read_session(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_SIGNED_IN_DETAIL)

    user = await service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        # The account is gone or disabled, so the session is worthless.
        await sessions.delete_session(token)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=NOT_SIGNED_IN_DETAIL)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User | None:
    """Return the signed-in account, or None for a visitor without a session."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    user_id = await sessions.read_session(token)
    if user_id is None:
        return None
    user = await service.get_by_id(db, user_id)
    return user if user is not None and user.is_active else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
