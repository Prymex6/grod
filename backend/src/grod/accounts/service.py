"""Account operations behind the HTTP endpoints."""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import passwords, sessions, totp
from grod.accounts.models import User
from grod.community.models import Group


class EmailAlreadyUsedError(Exception):
    """Another account already uses this address."""


class InvalidCredentialsError(Exception):
    """Wrong address, wrong password, or a disabled account."""


class TooManyAttemptsError(Exception):
    """The address hit the failed sign-in limit."""


class InvalidTotpCodeError(Exception):
    """The one-time code does not match the secret."""


class TotpNotEnrolledError(Exception):
    """No authenticator secret is waiting to be confirmed."""


@dataclass(frozen=True)
class PasswordStepResult:
    """Outcome of the password step: either a session, or a code is required."""

    user: User
    pending_token: str | None


LOGIN_ALLOWED = re.compile(r"[^a-z0-9._-]+")
LOGIN_FALLBACK = "user"
LOGIN_MAX_ATTEMPTS = 100


async def _free_login(session: AsyncSession, email: str) -> str:
    """Turn an address into a handle nobody else uses yet.

    Handles and group addresses share one space, because both stand at the
    front of a project address, so a group slug blocks a handle as well.
    """
    base = LOGIN_ALLOWED.sub("-", email.split("@")[0].lower()).strip("-._") or LOGIN_FALLBACK
    for attempt in range(LOGIN_MAX_ATTEMPTS):
        candidate = base if attempt == 0 else f"{base}{attempt + 1}"
        taken = await session.execute(select(User).where(User.login == candidate))
        used_by_group = await session.execute(select(Group).where(Group.slug == candidate))
        if taken.scalar_one_or_none() is None and used_by_group.scalar_one_or_none() is None:
            return candidate
    raise EmailAlreadyUsedError


async def find_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """Return the account with this identifier, if any."""
    return await session.get(User, user_id)


async def find_by_login(session: AsyncSession, login: str) -> User | None:
    """Return the account with this handle, if any."""
    result = await session.execute(select(User).where(User.login == login.lower()))
    return result.scalar_one_or_none()


async def find_by_email(session: AsyncSession, email: str) -> User | None:
    """Return the account with this address, if any."""
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def register(session: AsyncSession, *, email: str, display_name: str, password: str) -> User:
    """Create an account. Registration is open to everyone on this platform."""
    user = User(
        email=email.lower(),
        login=await _free_login(session, email),
        display_name=display_name,
        password_hash=passwords.hash_password(password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise EmailAlreadyUsedError from error
    return user


async def sign_in_with_password(
    session: AsyncSession, *, email: str, password: str, attempt_limit: int
) -> PasswordStepResult:
    """Check the password and say whether a two-factor code is still needed."""
    if await sessions.failed_attempts(email) >= attempt_limit:
        raise TooManyAttemptsError

    user = await find_by_email(session, email)
    # Hash a throwaway password when the account is missing, so that answers
    # take a similar amount of time whether or not the address exists.
    password_hash = user.password_hash if user else passwords.hash_password(password)
    password_matches = passwords.verify_password(password, password_hash)

    if user is None or not password_matches or not user.is_active:
        await sessions.count_failed_attempt(email)
        raise InvalidCredentialsError

    await sessions.clear_failed_attempts(email)

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
        await session.commit()

    if user.totp_enabled:
        return PasswordStepResult(
            user=user, pending_token=await sessions.create_pending_login(user.id)
        )
    return PasswordStepResult(user=user, pending_token=None)


async def complete_totp_login(session: AsyncSession, *, pending_token: str, code: str) -> User:
    """Finish a sign-in that was waiting for a one-time code."""
    user_id = await sessions.take_pending_login(pending_token)
    if user_id is None:
        raise InvalidCredentialsError

    user = await get_by_id(session, user_id)
    if user is None or not user.is_active or user.totp_secret is None:
        raise InvalidCredentialsError
    if not totp.verify_code(user.totp_secret, code):
        raise InvalidTotpCodeError
    return user


async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """Return an account by identifier."""
    return await session.get(User, user_id)


async def start_totp_enrollment(
    session: AsyncSession, *, user: User, issuer: str
) -> tuple[str, str]:
    """Store a fresh secret and return it with its provisioning URI."""
    secret = totp.generate_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    await session.commit()
    return secret, totp.provisioning_uri(secret, user.email, issuer)


async def confirm_totp_enrollment(session: AsyncSession, *, user: User, code: str) -> None:
    """Turn two-factor on once the user proves the app is set up."""
    if user.totp_secret is None:
        raise TotpNotEnrolledError
    if not totp.verify_code(user.totp_secret, code):
        raise InvalidTotpCodeError
    user.totp_enabled = True
    await session.commit()


async def disable_totp(session: AsyncSession, *, user: User) -> None:
    """Turn two-factor off and forget the secret."""
    user.totp_secret = None
    user.totp_enabled = False
    await session.commit()
