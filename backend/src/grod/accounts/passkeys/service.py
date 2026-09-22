"""Registering and using passkeys, on top of the py_webauthn library."""

import json
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from grod.accounts.models import User
from grod.accounts.passkeys.models import LABEL_MAX_LENGTH, Passkey
from grod.accounts.sessions import get_client

CHALLENGE_KEY_PREFIX = "accounts:passkey-challenge:"
CHALLENGE_TTL_SECONDS = 5 * 60
HANDLE_BYTES = 32
DEFAULT_LABEL = "Passkey"


class PasskeyRejectedError(Exception):
    """The authenticator's answer did not check out."""


class ChallengeExpiredError(Exception):
    """The challenge is unknown, already used or too old."""


class UnknownPasskeyError(Exception):
    """No account has registered this authenticator."""


async def _save_challenge(challenge: bytes, *, user_id: UUID | None) -> str:
    handle = secrets.token_urlsafe(HANDLE_BYTES)
    payload = json.dumps(
        {
            "challenge": challenge.hex(),
            "userId": str(user_id) if user_id else None,
        }
    )
    await get_client().set(f"{CHALLENGE_KEY_PREFIX}{handle}", payload, ex=CHALLENGE_TTL_SECONDS)
    return handle


async def _take_challenge(handle: str) -> tuple[bytes, UUID | None]:
    raw = await get_client().getdel(f"{CHALLENGE_KEY_PREFIX}{handle}")
    if raw is None:
        raise ChallengeExpiredError
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    data = json.loads(text)
    stored_user = data["userId"]
    return bytes.fromhex(str(data["challenge"])), UUID(str(stored_user)) if stored_user else None


async def list_passkeys(session: AsyncSession, *, user: User) -> list[Passkey]:
    """Return the authenticators registered to an account."""
    result = await session.execute(
        select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at)
    )
    return list(result.scalars())


async def start_registration(
    session: AsyncSession, *, user: User, rp_id: str, rp_name: str
) -> tuple[str, dict[str, Any]]:
    """Return the options the browser needs to create a passkey."""
    existing = await list_passkeys(session, user=user)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=str(user.id).encode(),
        user_name=user.email,
        user_display_name=user.display_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=passkey.credential_id) for passkey in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    handle = await _save_challenge(options.challenge, user_id=user.id)
    parsed: dict[str, Any] = json.loads(options_to_json(options))
    return handle, parsed


async def finish_registration(
    session: AsyncSession,
    *,
    user: User,
    handle: str,
    credential: dict[str, Any],
    label: str | None,
    rp_id: str,
    origin: str,
) -> Passkey:
    """Store a passkey after checking the authenticator's answer."""
    challenge, challenge_user = await _take_challenge(handle)
    if challenge_user != user.id:
        raise ChallengeExpiredError

    try:
        verified = verify_registration_response(
            credential=json.dumps(credential),
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except InvalidRegistrationResponse as error:
        raise PasskeyRejectedError from error

    passkey = Passkey(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        label=(label or DEFAULT_LABEL)[:LABEL_MAX_LENGTH],
    )
    session.add(passkey)
    await session.commit()
    return passkey


async def delete_passkey(session: AsyncSession, *, user: User, passkey_id: UUID) -> bool:
    """Remove one authenticator of an account."""
    passkey = await session.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user.id:
        return False
    await session.delete(passkey)
    await session.commit()
    return True


async def start_authentication(*, rp_id: str) -> tuple[str, dict[str, Any]]:
    """Return sign-in options; the browser picks a passkey for this instance."""
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.PREFERRED
    )
    handle = await _save_challenge(options.challenge, user_id=None)
    parsed: dict[str, Any] = json.loads(options_to_json(options))
    return handle, parsed


async def finish_authentication(
    session: AsyncSession,
    *,
    handle: str,
    credential: dict[str, Any],
    rp_id: str,
    origin: str,
) -> User:
    """Check a passkey sign-in and return the account behind it."""
    challenge, _ = await _take_challenge(handle)

    raw_id = credential.get("rawId")
    if not isinstance(raw_id, str):
        raise PasskeyRejectedError
    credential_id = base64url_to_bytes(raw_id)

    result = await session.execute(select(Passkey).where(Passkey.credential_id == credential_id))
    passkey = result.scalar_one_or_none()
    if passkey is None:
        raise UnknownPasskeyError

    try:
        verified = verify_authentication_response(
            credential=json.dumps(credential),
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except InvalidAuthenticationResponse as error:
        raise PasskeyRejectedError from error

    user = await session.get(User, passkey.user_id)
    if user is None or not user.is_active:
        raise UnknownPasskeyError

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    await session.commit()
    return user
