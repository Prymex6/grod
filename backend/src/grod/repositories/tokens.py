"""Personal access tokens: the password Git asks for when cloning or pushing."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import passwords
from grod.accounts.models import User
from grod.repositories.models import AccessToken

PREFIX = "grod"
SECRET_BYTES = 32
SCOPE_READ = "repo:read"
SCOPE_WRITE = "repo:write"
SUPPORTED_SCOPES = (SCOPE_READ, SCOPE_WRITE)
TOKEN_PARTS = 3


class UnsupportedScopeError(Exception):
    """The token was asked for a permission Grod does not know."""


@dataclass(frozen=True)
class NewToken:
    """A freshly created token; the secret is shown only once."""

    token: AccessToken
    value: str


@dataclass(frozen=True)
class TokenHolder:
    """Who a token belongs to and what it may do."""

    user: User
    scopes: list[str]


def _format(token_id: UUID, secret: str) -> str:
    return f"{PREFIX}_{token_id.hex}_{secret}"


def _parse(value: str) -> tuple[UUID, str] | None:
    # The secret is url-safe base64, so it may contain underscores itself.
    parts = value.split("_", TOKEN_PARTS - 1)
    if len(parts) != TOKEN_PARTS or parts[0] != PREFIX:
        return None
    try:
        return UUID(hex=parts[1]), parts[2]
    except ValueError:
        return None


async def create(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> NewToken:
    """Create a token for an account and return its only readable copy."""
    if set(scopes) - set(SUPPORTED_SCOPES) or not scopes:
        raise UnsupportedScopeError

    secret = secrets.token_urlsafe(SECRET_BYTES)
    token = AccessToken(
        user_id=user.id,
        name=name,
        secret_hash=passwords.hash_password(secret),
        scopes=scopes,
        expires_at=expires_at,
    )
    session.add(token)
    await session.commit()
    return NewToken(token=token, value=_format(token.id, secret))


async def list_for(session: AsyncSession, *, user: User) -> list[AccessToken]:
    """Return the tokens of an account."""
    result = await session.execute(
        select(AccessToken).where(AccessToken.user_id == user.id).order_by(AccessToken.created_at)
    )
    return list(result.scalars())


async def delete(session: AsyncSession, *, user: User, token_id: UUID) -> bool:
    """Remove one token of an account."""
    token = await session.get(AccessToken, token_id)
    if token is None or token.user_id != user.id:
        return False
    await session.delete(token)
    await session.commit()
    return True


async def authenticate(session: AsyncSession, value: str) -> TokenHolder | None:
    """Return the holder of a token, or None when it does not check out."""
    parsed = _parse(value)
    if parsed is None:
        return None
    token_id, secret = parsed

    token = await session.get(AccessToken, token_id)
    if token is None:
        return None
    if token.expires_at is not None and token.expires_at <= datetime.now(UTC):
        return None
    if not passwords.verify_password(secret, token.secret_hash):
        return None

    user = await session.get(User, token.user_id)
    if user is None or not user.is_active:
        return None

    token.last_used_at = datetime.now(UTC)
    await session.commit()
    return TokenHolder(user=user, scopes=list(token.scopes))
