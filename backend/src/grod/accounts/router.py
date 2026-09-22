"""HTTP endpoints for registration, sign-in, sessions and two-factor setup."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import password_reset, service, sessions
from grod.accounts.dependencies import CurrentUser, SessionToken
from grod.accounts.models import User
from grod.accounts.schemas import (
    AccountView,
    ClosedSessions,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SessionView,
    SignedIn,
    TotpCodeRequest,
    TotpEnrollment,
    TotpLoginRequest,
    TotpRequired,
)
from grod.config import Settings, get_settings
from grod.db import get_db_session

router = APIRouter(prefix="/auth", tags=["accounts"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
UserAgent = Annotated[str | None, Header(alias="User-Agent")]

INVALID_CREDENTIALS_DETAIL = "Invalid email or password"
INVALID_CODE_DETAIL = "Invalid verification code"


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


async def _sign_in(
    response: Response, user: User, settings: Settings, user_agent: str | None = None
) -> SignedIn:
    token = await sessions.create_session(user.id, user_agent=user_agent or "")
    _set_session_cookie(response, token, settings)
    return SignedIn(account=AccountView.model_validate(user))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    user_agent: UserAgent = None,
) -> SignedIn:
    """Create an account and sign it in."""
    try:
        user = await service.register(
            db, email=body.email, display_name=body.display_name, password=body.password
        )
    except service.EmailAlreadyUsedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This email is already registered"
        ) from None
    return await _sign_in(response, user, settings, user_agent)


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    user_agent: UserAgent = None,
) -> SignedIn | TotpRequired:
    """Check the password; ask for a one-time code when two-factor is on."""
    try:
        result = await service.sign_in_with_password(
            db,
            email=body.email,
            password=body.password,
            attempt_limit=settings.login_attempt_limit,
        )
    except service.TooManyAttemptsError:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many sign-in attempts"
        ) from None
    except service.InvalidCredentialsError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        ) from None

    if result.pending_token is not None:
        return TotpRequired(pending_token=result.pending_token)
    return await _sign_in(response, result.user, settings, user_agent)


@router.post("/login/totp")
async def login_with_totp(
    body: TotpLoginRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
    user_agent: UserAgent = None,
) -> SignedIn:
    """Finish a sign-in with the code from an authenticator app."""
    try:
        user = await service.complete_totp_login(
            db, pending_token=body.pending_token, code=body.code
        )
    except service.InvalidCredentialsError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        ) from None
    except service.InvalidTotpCodeError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CODE_DETAIL) from None
    return await _sign_in(response, user, settings, user_agent)


@router.get("/me")
async def current_account(user: CurrentUser) -> AccountView:
    """Return the signed-in account."""
    return AccountView.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    token: SessionToken,
    settings: SettingsDependency,
) -> None:
    """Sign the current session out, on the server and in the browser."""
    await sessions.delete_session(token)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.post("/password/reset-request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(body: PasswordResetRequest, db: DbSession) -> None:
    """Send a reset link. The answer never says whether the account exists."""
    await password_reset.request_reset(db, email=body.email)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: PasswordResetConfirm, db: DbSession) -> None:
    """Set a new password from a reset link and sign every device out."""
    try:
        await password_reset.confirm_reset(db, token=body.token, password=body.password)
    except password_reset.InvalidResetTokenError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="This reset link is no longer valid"
        ) from None


@router.get("/sessions")
async def list_sessions(user: CurrentUser, token: SessionToken) -> list[SessionView]:
    """Return the live sessions of the signed-in account."""
    sessions_of_user = await sessions.list_sessions(user.id)
    return [
        SessionView(
            created_at=datetime.fromtimestamp(session.created_at, tz=UTC),
            user_agent=session.user_agent,
            current=session.token == token,
        )
        for session in sessions_of_user
    ]


@router.post("/sessions/others/logout")
async def logout_other_sessions(user: CurrentUser, token: SessionToken) -> ClosedSessions:
    """Sign out every other device of the signed-in account."""
    return ClosedSessions(closed=await sessions.delete_other_sessions(user.id, keep_token=token))


@router.post("/totp/setup")
async def setup_totp(
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDependency,
) -> TotpEnrollment:
    """Create a secret for an authenticator app; confirm it to turn two-factor on."""
    secret, uri = await service.start_totp_enrollment(db, user=user, issuer=settings.instance_name)
    return TotpEnrollment(secret=secret, provisioning_uri=uri)


@router.post("/totp/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_totp(body: TotpCodeRequest, user: CurrentUser, db: DbSession) -> None:
    """Turn two-factor on after the first correct code."""
    try:
        await service.confirm_totp_enrollment(db, user=user, code=body.code)
    except service.TotpNotEnrolledError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="No authenticator secret to confirm"
        ) from None
    except service.InvalidTotpCodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_CODE_DETAIL) from None


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_totp(user: CurrentUser, db: DbSession) -> None:
    """Turn two-factor off for the current account."""
    await service.disable_totp(db, user=user)
