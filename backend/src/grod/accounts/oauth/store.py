"""Short-lived state of the sign-in flow, kept in Valkey.

Authorization requests, one-time codes and refresh tokens all live here so
that nothing about a half-finished sign-in is written to the database.
"""

import json
import secrets
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from grod.accounts.sessions import get_client
from grod.config import get_settings

REQUEST_KEY_PREFIX = "accounts:oauth-request:"
CODE_KEY_PREFIX = "accounts:oauth-code:"
REFRESH_KEY_PREFIX = "accounts:oauth-refresh:"
REFRESH_INDEX_KEY_PREFIX = "accounts:oauth-refresh-index:"
HANDLE_BYTES = 32


@dataclass(frozen=True)
class AuthorizationRequest:
    """A validated /authorize call waiting for the account holder to decide."""

    client_id: str
    redirect_uri: str
    scopes: list[str]
    state: str | None
    nonce: str | None
    code_challenge: str
    code_challenge_method: str


@dataclass(frozen=True)
class AuthorizationCode:
    """The one-time code a client exchanges for tokens."""

    client_id: str
    user_id: str
    redirect_uri: str
    scopes: list[str]
    nonce: str | None
    code_challenge: str
    code_challenge_method: str


@dataclass(frozen=True)
class RefreshToken:
    """State behind an opaque refresh token."""

    client_id: str
    user_id: str
    scopes: list[str]


def _new_handle() -> str:
    return secrets.token_urlsafe(HANDLE_BYTES)


def _decode(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    parsed: dict[str, Any] = json.loads(text)
    return parsed


async def save_request(request: AuthorizationRequest) -> str:
    """Store a pending authorization request and return its handle."""
    handle = _new_handle()
    await get_client().set(
        f"{REQUEST_KEY_PREFIX}{handle}",
        json.dumps(asdict(request)),
        ex=get_settings().oauth_request_ttl_seconds,
    )
    return handle


async def read_request(handle: str) -> AuthorizationRequest | None:
    """Return a pending authorization request without consuming it."""
    data = _decode(await get_client().get(f"{REQUEST_KEY_PREFIX}{handle}"))
    return AuthorizationRequest(**data) if data else None


async def take_request(handle: str) -> AuthorizationRequest | None:
    """Consume a pending authorization request."""
    data = _decode(await get_client().getdel(f"{REQUEST_KEY_PREFIX}{handle}"))
    return AuthorizationRequest(**data) if data else None


async def save_code(code_data: AuthorizationCode) -> str:
    """Store a one-time authorization code and return it."""
    code = _new_handle()
    await get_client().set(
        f"{CODE_KEY_PREFIX}{code}",
        json.dumps(asdict(code_data)),
        ex=get_settings().oauth_code_ttl_seconds,
    )
    return code


async def take_code(code: str) -> AuthorizationCode | None:
    """Consume an authorization code so it cannot be replayed."""
    data = _decode(await get_client().getdel(f"{CODE_KEY_PREFIX}{code}"))
    return AuthorizationCode(**data) if data else None


def _refresh_index_key(user_id: str, client_id: str) -> str:
    return f"{REFRESH_INDEX_KEY_PREFIX}{user_id}:{client_id}"


async def save_refresh_token(token: str, state: RefreshToken) -> None:
    """Remember what an opaque refresh token stands for."""
    ttl = get_settings().oauth_refresh_token_ttl_seconds
    index_key = _refresh_index_key(state.user_id, state.client_id)
    client = get_client()
    async with client.pipeline() as pipeline:
        pipeline.set(f"{REFRESH_KEY_PREFIX}{token}", json.dumps(asdict(state)), ex=ttl)
        pipeline.sadd(index_key, token)
        pipeline.expire(index_key, ttl)
        await pipeline.execute()


async def take_refresh_token(token: str) -> RefreshToken | None:
    """Consume a refresh token; every use hands out a new one."""
    data = _decode(await get_client().getdel(f"{REFRESH_KEY_PREFIX}{token}"))
    if data is None:
        return None
    state = RefreshToken(**data)
    await get_client().srem(_refresh_index_key(state.user_id, state.client_id), token)
    return state


async def revoke_refresh_tokens(*, user_id: str, client_id: str) -> int:
    """Drop every refresh token an application holds for an account."""
    client = get_client()
    index_key = _refresh_index_key(user_id, client_id)
    tokens = [
        token.decode() if isinstance(token, bytes) else str(token)
        for token in await client.smembers(index_key)
    ]
    if tokens:
        await client.delete(*[f"{REFRESH_KEY_PREFIX}{token}" for token in tokens])
    await client.delete(index_key)
    return len(tokens)


def user_id_of(value: str) -> UUID:
    """Parse the account identifier stored with a code or refresh token."""
    return UUID(value)
