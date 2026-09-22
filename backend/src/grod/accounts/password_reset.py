"""Resetting a forgotten password through a link sent by email."""

import secrets
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import passwords, service, sessions
from grod.config import get_settings
from grod.mail import send_email

RESET_KEY_PREFIX = "accounts:password-reset:"
TOKEN_BYTES = 32

SUBJECT = "Grod - set a new password"
BODY = """Hello,

somebody asked to set a new password for the account {email}.
If that was you, open this link:

{link}

The link works for {minutes} minutes and only once. If it was not you, ignore
this message - the password stays as it is.
"""


class InvalidResetTokenError(Exception):
    """The link is unknown, already used or expired."""


def _key(token: str) -> str:
    return f"{RESET_KEY_PREFIX}{token}"


async def request_reset(session: AsyncSession, *, email: str) -> None:
    """Send a reset link, and stay silent about whether the account exists."""
    user = await service.find_by_email(session, email)
    if user is None or not user.is_active:
        return

    settings = get_settings()
    token = secrets.token_urlsafe(TOKEN_BYTES)
    await sessions.get_client().set(
        _key(token), str(user.id), ex=settings.password_reset_ttl_seconds
    )

    link = f"{str(settings.public_url).rstrip('/')}/password/reset?token={token}"
    await send_email(
        to=user.email,
        subject=SUBJECT,
        body=BODY.format(
            email=user.email,
            link=link,
            minutes=settings.password_reset_ttl_seconds // 60,
        ),
    )


async def confirm_reset(session: AsyncSession, *, token: str, password: str) -> None:
    """Set a new password and sign every device of that account out."""
    stored = await sessions.get_client().getdel(_key(token))
    if stored is None:
        raise InvalidResetTokenError

    user_id = UUID(stored.decode() if isinstance(stored, bytes) else str(stored))
    user = await service.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise InvalidResetTokenError

    user.password_hash = passwords.hash_password(password)
    await session.commit()
    # A forgotten password may mean someone else had access.
    await sessions.delete_all_sessions(user.id)
