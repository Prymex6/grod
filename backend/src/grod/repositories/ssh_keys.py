"""SSH public keys of an account, used when Git talks over SSH."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import asyncssh
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.repositories.models import SSH_KEY_NAME_MAX_LENGTH, SshKey


class InvalidKeyError(Exception):
    """The text is not an OpenSSH public key."""


class KeyAlreadyAddedError(Exception):
    """Some account already registered this key."""


@dataclass(frozen=True)
class ParsedKey:
    """A public key in the normalised form Grod stores."""

    algorithm: str
    public_key: str
    fingerprint: str


def parse(text: str) -> ParsedKey:
    """Read a key in the `ssh-ed25519 AAAA... comment` form."""
    try:
        key = asyncssh.import_public_key(text.strip())
    except (asyncssh.KeyImportError, UnicodeDecodeError, ValueError) as error:
        raise InvalidKeyError from error
    return ParsedKey(
        algorithm=key.algorithm.decode(),
        public_key=key.export_public_key().decode().strip(),
        fingerprint=key.get_fingerprint(),
    )


async def add(session: AsyncSession, *, user: User, name: str, text: str) -> SshKey:
    """Register a public key for an account."""
    parsed = parse(text)
    existing = await session.execute(select(SshKey).where(SshKey.fingerprint == parsed.fingerprint))
    if existing.scalar_one_or_none() is not None:
        raise KeyAlreadyAddedError

    key = SshKey(
        user_id=user.id,
        name=name[:SSH_KEY_NAME_MAX_LENGTH],
        algorithm=parsed.algorithm,
        public_key=parsed.public_key,
        fingerprint=parsed.fingerprint,
    )
    session.add(key)
    await session.commit()
    return key


async def list_for(session: AsyncSession, *, user: User) -> list[SshKey]:
    """Return the keys of an account."""
    result = await session.execute(
        select(SshKey).where(SshKey.user_id == user.id).order_by(SshKey.created_at)
    )
    return list(result.scalars())


async def delete(session: AsyncSession, *, user: User, key_id: UUID) -> bool:
    """Remove one key of an account."""
    key = await session.get(SshKey, key_id)
    if key is None or key.user_id != user.id:
        return False
    await session.delete(key)
    await session.commit()
    return True


async def find_owner(session: AsyncSession, *, fingerprint: str) -> User | None:
    """Return the account a key belongs to and note that it was used."""
    result = await session.execute(select(SshKey).where(SshKey.fingerprint == fingerprint))
    key = result.scalar_one_or_none()
    if key is None:
        return None

    user = await session.get(User, key.user_id)
    if user is None or not user.is_active:
        return None

    key.last_used_at = datetime.now(UTC)
    await session.commit()
    return user
