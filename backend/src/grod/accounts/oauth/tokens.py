"""Signed tokens handed to OpenID Connect clients."""

import secrets
import time
from typing import Any
from uuid import UUID

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwt import JWTClaimsRegistry

from grod.accounts.oauth.keys import SIGNING_ALGORITHM, get_key_id, get_signing_key

ACCESS_TOKEN_TYPE = "at+jwt"  # noqa: S105  (a media type, not a secret)
ID_TOKEN_TYPE = "JWT"  # noqa: S105  (a media type, not a secret)
REFRESH_TOKEN_BYTES = 48


class InvalidTokenError(Exception):
    """The token is malformed, expired or signed by someone else."""


def _sign(payload: dict[str, Any], token_type: str) -> str:
    header = {"alg": SIGNING_ALGORITHM, "kid": get_key_id(), "typ": token_type}
    return jwt.encode(header, payload, get_signing_key())


def create_access_token(
    *, subject: UUID, client_id: str, scopes: list[str], issuer: str, lifetime_seconds: int
) -> str:
    """Return a signed access token for the API."""
    issued_at = int(time.time())
    return _sign(
        {
            "iss": issuer,
            "sub": str(subject),
            "aud": client_id,
            "client_id": client_id,
            "scope": " ".join(scopes),
            "iat": issued_at,
            "exp": issued_at + lifetime_seconds,
            "jti": secrets.token_urlsafe(16),
        },
        ACCESS_TOKEN_TYPE,
    )


def create_id_token(
    *,
    subject: UUID,
    client_id: str,
    issuer: str,
    lifetime_seconds: int,
    nonce: str | None,
    claims: dict[str, Any],
) -> str:
    """Return the identity token that tells the client who signed in."""
    issued_at = int(time.time())
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": str(subject),
        "aud": client_id,
        "iat": issued_at,
        "exp": issued_at + lifetime_seconds,
        **claims,
    }
    if nonce is not None:
        payload["nonce"] = nonce
    return _sign(payload, ID_TOKEN_TYPE)


def decode_access_token(token: str, *, issuer: str) -> dict[str, Any]:
    """Check the signature, the issuer and the lifetime of an access token."""
    requested = JWTClaimsRegistry(
        iss={"essential": True, "value": issuer},
        sub={"essential": True},
        exp={"essential": True},
    )
    try:
        decoded = jwt.decode(token, get_signing_key(), algorithms=[SIGNING_ALGORITHM])
        requested.validate(decoded.claims)
    except (JoseError, ValueError) as error:
        raise InvalidTokenError from error
    return dict(decoded.claims)


def create_refresh_token() -> str:
    """Return an opaque refresh token; its state lives in Valkey."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
