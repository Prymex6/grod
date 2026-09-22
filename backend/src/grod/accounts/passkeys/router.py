"""Endpoints for registering passkeys and signing in with them."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import sessions
from grod.accounts.dependencies import CurrentUser
from grod.accounts.passkeys import service
from grod.accounts.passkeys.schemas import (
    PasskeyAuthentication,
    PasskeyOptions,
    PasskeyRegistration,
    PasskeyView,
)
from grod.accounts.schemas import AccountView, SignedIn
from grod.config import Settings, get_settings
from grod.db import get_db_session

router = APIRouter(prefix="/auth/passkeys", tags=["accounts"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
UserAgent = Annotated[str | None, Header(alias="User-Agent")]

REJECTED_DETAIL = "The authenticator's answer was rejected"
EXPIRED_DETAIL = "The challenge expired; start again"


@router.get("")
async def list_passkeys(db: DbSession, user: CurrentUser) -> list[PasskeyView]:
    """Return the authenticators of the signed-in account."""
    passkeys = await service.list_passkeys(db, user=user)
    return [PasskeyView.model_validate(passkey) for passkey in passkeys]


@router.post("/register/options")
async def registration_options(
    db: DbSession, user: CurrentUser, settings: SettingsDependency
) -> PasskeyOptions:
    """Start registering a passkey for the signed-in account."""
    handle, options = await service.start_registration(
        db, user=user, rp_id=settings.webauthn_rp_id, rp_name=settings.instance_name
    )
    return PasskeyOptions(handle=handle, options=options)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_passkey(
    body: PasskeyRegistration,
    db: DbSession,
    user: CurrentUser,
    settings: SettingsDependency,
) -> PasskeyView:
    """Finish registering a passkey."""
    try:
        passkey = await service.finish_registration(
            db,
            user=user,
            handle=body.handle,
            credential=body.credential,
            label=body.label,
            rp_id=settings.webauthn_rp_id,
            origin=str(settings.public_url).rstrip("/"),
        )
    except service.ChallengeExpiredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=EXPIRED_DETAIL) from None
    except service.PasskeyRejectedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=REJECTED_DETAIL) from None
    return PasskeyView.model_validate(passkey)


@router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(passkey_id: UUID, db: DbSession, user: CurrentUser) -> None:
    """Remove one authenticator."""
    if not await service.delete_passkey(db, user=user, passkey_id=passkey_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown passkey")


@router.post("/login/options")
async def authentication_options(settings: SettingsDependency) -> PasskeyOptions:
    """Start a passkey sign-in; the browser offers the matching passkeys."""
    handle, options = await service.start_authentication(rp_id=settings.webauthn_rp_id)
    return PasskeyOptions(handle=handle, options=options)


@router.post("/login")
async def sign_in_with_passkey(
    body: PasskeyAuthentication,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    user_agent: UserAgent = None,
) -> SignedIn:
    """Finish a passkey sign-in and open a session."""
    try:
        user = await service.finish_authentication(
            db,
            handle=body.handle,
            credential=body.credential,
            rp_id=settings.webauthn_rp_id,
            origin=str(settings.public_url).rstrip("/"),
        )
    except service.ChallengeExpiredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=EXPIRED_DETAIL) from None
    except service.PasskeyRejectedError, service.UnknownPasskeyError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=REJECTED_DETAIL) from None

    token = await sessions.create_session(user.id, user_agent=user_agent or "")
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return SignedIn(account=AccountView.model_validate(user))
