"""Server-side sessions and short-lived login state, kept in Valkey."""

import json
import secrets
import time
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

from grod.config import get_settings

SESSION_KEY_PREFIX = "accounts:session:"
USER_SESSIONS_KEY_PREFIX = "accounts:user-sessions:"
PENDING_KEY_PREFIX = "accounts:pending-login:"
ATTEMPTS_KEY_PREFIX = "accounts:login-attempts:"
TOKEN_BYTES = 32

_client: Redis | None = None


@dataclass(frozen=True)
class SessionDetails:
    """A signed-in session as the account owner sees it."""

    token: str
    user_id: UUID
    created_at: int
    user_agent: str


def get_client() -> Redis:
    """Return the process-wide Valkey client."""
    global _client
    if _client is None:
        _client = Redis.from_url(str(get_settings().valkey_url), decode_responses=True)
    return _client


async def close_client() -> None:
    """Close the Valkey connections when the application shuts down."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _decode(value: object) -> str | None:
    """Normalise a Valkey answer to text; the client may hand back bytes."""
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _session_key(token: str) -> str:
    return f"{SESSION_KEY_PREFIX}{token}"


def _index_key(user_id: UUID) -> str:
    return f"{USER_SESSIONS_KEY_PREFIX}{user_id}"


async def create_session(user_id: UUID, *, user_agent: str = "") -> str:
    """Store a signed-in session and return its token."""
    token = _new_token()
    settings = get_settings()
    payload = json.dumps(
        {"userId": str(user_id), "createdAt": int(time.time()), "userAgent": user_agent[:200]}
    )
    client = get_client()
    async with client.pipeline() as pipeline:
        pipeline.set(_session_key(token), payload, ex=settings.session_ttl_seconds)
        pipeline.sadd(_index_key(user_id), token)
        pipeline.expire(_index_key(user_id), settings.session_ttl_seconds)
        await pipeline.execute()
    return token


async def _read(token: str) -> SessionDetails | None:
    raw = _decode(await get_client().get(_session_key(token)))
    if raw is None:
        return None
    data = json.loads(raw)
    return SessionDetails(
        token=token,
        user_id=UUID(str(data["userId"])),
        created_at=int(data["createdAt"]),
        user_agent=str(data["userAgent"]),
    )


async def read_session(token: str) -> UUID | None:
    """Return the account behind a session token, or None when it is unknown."""
    details = await _read(token)
    return details.user_id if details else None


async def list_sessions(user_id: UUID) -> list[SessionDetails]:
    """Return the live sessions of an account, newest first."""
    client = get_client()
    tokens = [_decode(token) for token in await client.smembers(_index_key(user_id))]
    sessions: list[SessionDetails] = []
    stale: list[str] = []
    for token in tokens:
        if token is None:
            continue
        details = await _read(token)
        if details is None:
            stale.append(token)
        else:
            sessions.append(details)
    if stale:
        # Expired sessions leave their token behind in the index.
        await client.srem(_index_key(user_id), *stale)
    return sorted(sessions, key=lambda session: session.created_at, reverse=True)


async def delete_session(token: str) -> None:
    """Sign a session out."""
    details = await _read(token)
    client = get_client()
    await client.delete(_session_key(token))
    if details is not None:
        await client.srem(_index_key(details.user_id), token)


async def delete_other_sessions(user_id: UUID, *, keep_token: str) -> int:
    """Sign out every session of an account except the one in use."""
    sessions = await list_sessions(user_id)
    removed = 0
    for session in sessions:
        if session.token == keep_token:
            continue
        await delete_session(session.token)
        removed += 1
    return removed


async def delete_all_sessions(user_id: UUID) -> int:
    """Sign out every session of an account."""
    sessions_of_user = await list_sessions(user_id)
    for session in sessions_of_user:
        await delete_session(session.token)
    return len(sessions_of_user)


async def create_pending_login(user_id: UUID) -> str:
    """Remember an account that passed the password step and still owes a code."""
    token = _new_token()
    settings = get_settings()
    await get_client().set(
        f"{PENDING_KEY_PREFIX}{token}", str(user_id), ex=settings.pending_login_ttl_seconds
    )
    return token


async def take_pending_login(token: str) -> UUID | None:
    """Consume a pending login so a token cannot be replayed."""
    stored = _decode(await get_client().getdel(f"{PENDING_KEY_PREFIX}{token}"))
    return UUID(stored) if stored else None


async def count_failed_attempt(email: str) -> int:
    """Count a failed sign-in and return how many happened inside the window."""
    settings = get_settings()
    key = f"{ATTEMPTS_KEY_PREFIX}{email.lower()}"
    client = get_client()
    attempts = await client.incr(key)
    if attempts == 1:
        await client.expire(key, settings.login_attempt_window_seconds)
    return int(attempts)


async def clear_failed_attempts(email: str) -> None:
    """Forget failed attempts after a successful sign-in."""
    await get_client().delete(f"{ATTEMPTS_KEY_PREFIX}{email.lower()}")


async def failed_attempts(email: str) -> int:
    """Return how many failed sign-ins are recorded for an address."""
    stored = _decode(await get_client().get(f"{ATTEMPTS_KEY_PREFIX}{email.lower()}"))
    return int(stored) if stored else 0
