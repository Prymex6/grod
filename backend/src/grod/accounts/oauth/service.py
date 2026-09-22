"""The OpenID Connect flow: validate, consent, codes, tokens, claims."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import passwords
from grod.accounts.models import User
from grod.accounts.oauth import store, tokens
from grod.accounts.oauth.models import OAuthClient, OAuthGrant
from grod.accounts.oauth.store import AuthorizationCode, AuthorizationRequest, RefreshToken

OPENID_SCOPE = "openid"
SUPPORTED_SCOPES = (OPENID_SCOPE, "profile", "email", "offline_access")
OFFLINE_ACCESS_SCOPE = "offline_access"
SUPPORTED_CODE_CHALLENGE_METHOD = "S256"
CLIENT_ID_BYTES = 16
CLIENT_SECRET_BYTES = 32


class InvalidClientError(Exception):
    """Unknown client, disabled client, or wrong secret."""


class InvalidRedirectUriError(Exception):
    """The redirect address is not one the client registered."""


class InvalidRequestError(Exception):
    """The authorization request breaks the rules of the flow."""


class InvalidGrantError(Exception):
    """The code or refresh token cannot be exchanged."""


@dataclass(frozen=True)
class IssuedTokens:
    """What the token endpoint hands back."""

    access_token: str
    expires_in: int
    scopes: list[str]
    id_token: str | None
    refresh_token: str | None


@dataclass(frozen=True)
class ApprovedAuthorization:
    """Where to send the browser once the account holder said yes."""

    code: str
    redirect_uri: str
    state: str | None


@dataclass(frozen=True)
class NewClient:
    """A freshly registered application; the secret is shown only once."""

    client: OAuthClient
    client_secret: str | None


def _verify_challenge(verifier: str, challenge: str) -> bool:
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(expected, challenge)


async def find_client(session: AsyncSession, client_id: str) -> OAuthClient | None:
    """Return an active client by its identifier."""
    result = await session.execute(
        select(OAuthClient).where(OAuthClient.client_id == client_id, OAuthClient.is_active)
    )
    return result.scalar_one_or_none()


async def register_client(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    redirect_uris: list[str],
    scopes: list[str],
    confidential: bool,
) -> NewClient:
    """Register an application that may sign people in through this instance."""
    unsupported = set(scopes) - set(SUPPORTED_SCOPES)
    if unsupported or OPENID_SCOPE not in scopes:
        raise InvalidRequestError
    if not redirect_uris:
        raise InvalidRedirectUriError

    secret = secrets.token_urlsafe(CLIENT_SECRET_BYTES) if confidential else None
    client = OAuthClient(
        client_id=secrets.token_urlsafe(CLIENT_ID_BYTES),
        name=name,
        client_secret_hash=passwords.hash_password(secret) if secret else None,
        redirect_uris=redirect_uris,
        scopes=scopes,
        owner_id=owner.id,
    )
    session.add(client)
    await session.commit()
    return NewClient(client=client, client_secret=secret)


async def list_clients(session: AsyncSession, *, owner: User) -> list[OAuthClient]:
    """Return the applications registered by this account."""
    result = await session.execute(
        select(OAuthClient).where(OAuthClient.owner_id == owner.id).order_by(OAuthClient.created_at)
    )
    return list(result.scalars())


async def start_authorization(
    session: AsyncSession,
    *,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    scope: str,
    state: str | None,
    nonce: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> tuple[OAuthClient, str]:
    """Validate an /authorize call and park it until the account holder decides."""
    client = await find_client(session, client_id)
    if client is None:
        raise InvalidClientError
    if redirect_uri not in client.redirect_uris:
        raise InvalidRedirectUriError

    # Everything below is reported to the client through its redirect address.
    if response_type != "code":
        raise InvalidRequestError
    # PKCE is required of every client, which is what current guidance says.
    if not code_challenge or code_challenge_method != SUPPORTED_CODE_CHALLENGE_METHOD:
        raise InvalidRequestError

    requested = scope.split()
    if OPENID_SCOPE not in requested or set(requested) - set(client.scopes):
        raise InvalidRequestError

    handle = await store.save_request(
        AuthorizationRequest(
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            scopes=requested,
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
    )
    return client, handle


async def has_grant(
    session: AsyncSession, *, user: User, client: OAuthClient, scopes: list[str]
) -> bool:
    """True when this account already allowed the application these scopes."""
    grant = await _find_grant(session, user_id=user.id, client_id=client.id)
    return grant is not None and not set(scopes) - set(grant.scopes)


async def _find_grant(
    session: AsyncSession, *, user_id: UUID, client_id: UUID
) -> OAuthGrant | None:
    result = await session.execute(
        select(OAuthGrant).where(OAuthGrant.user_id == user_id, OAuthGrant.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def save_grant(
    session: AsyncSession, *, user: User, client: OAuthClient, scopes: list[str]
) -> None:
    """Remember the consent, adding to what was allowed before."""
    grant = await _find_grant(session, user_id=user.id, client_id=client.id)
    if grant is None:
        session.add(OAuthGrant(user_id=user.id, client_id=client.id, scopes=scopes))
    else:
        grant.scopes = sorted(set(grant.scopes) | set(scopes))
    await session.commit()


async def list_grants(session: AsyncSession, *, user: User) -> list[tuple[OAuthGrant, OAuthClient]]:
    """Return the applications this account has allowed."""
    result = await session.execute(
        select(OAuthGrant, OAuthClient)
        .join(OAuthClient, OAuthClient.id == OAuthGrant.client_id)
        .where(OAuthGrant.user_id == user.id)
        .order_by(OAuthGrant.created_at)
    )
    return [(grant, client) for grant, client in result.all()]


async def revoke_grant(session: AsyncSession, *, user: User, client_id: str) -> bool:
    """Take an application's access away and drop its refresh tokens."""
    client = await find_client(session, client_id)
    if client is None:
        return False
    grant = await _find_grant(session, user_id=user.id, client_id=client.id)
    if grant is None:
        return False
    await session.delete(grant)
    await session.commit()
    await store.revoke_refresh_tokens(user_id=str(user.id), client_id=client.client_id)
    return True


async def issue_code_for(*, request: AuthorizationRequest, user: User) -> ApprovedAuthorization:
    """Turn a validated request into a one-time code."""
    code = await store.save_code(
        AuthorizationCode(
            client_id=request.client_id,
            user_id=str(user.id),
            redirect_uri=request.redirect_uri,
            scopes=request.scopes,
            nonce=request.nonce,
            code_challenge=request.code_challenge,
            code_challenge_method=request.code_challenge_method,
        )
    )
    return ApprovedAuthorization(code=code, redirect_uri=request.redirect_uri, state=request.state)


async def approve_authorization(
    session: AsyncSession, *, handle: str, user: User
) -> ApprovedAuthorization | None:
    """Remember the consent, issue a code, or report the request expired."""
    request = await store.take_request(handle)
    if request is None:
        return None
    client = await find_client(session, request.client_id)
    if client is None:
        return None
    await save_grant(session, user=user, client=client, scopes=request.scopes)
    return await issue_code_for(request=request, user=user)


async def authenticate_client(
    session: AsyncSession, *, client_id: str, client_secret: str | None
) -> OAuthClient:
    """Check the credentials a client sent to the token endpoint."""
    client = await find_client(session, client_id)
    if client is None:
        raise InvalidClientError
    if client.is_confidential:
        if client_secret is None or client.client_secret_hash is None:
            raise InvalidClientError
        if not passwords.verify_password(client_secret, client.client_secret_hash):
            raise InvalidClientError
    elif client_secret is not None:
        raise InvalidClientError
    return client


def _claims_for(user: User, scopes: list[str]) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    if "profile" in scopes:
        claims["name"] = user.display_name
    if "email" in scopes:
        claims["email"] = user.email
        claims["email_verified"] = False
    return claims


async def _issue(
    session: AsyncSession,
    *,
    client: OAuthClient,
    user: User,
    scopes: list[str],
    nonce: str | None,
    issuer: str,
    access_token_ttl: int,
    id_token_ttl: int,
    with_id_token: bool,
) -> IssuedTokens:
    del session
    refresh_token: str | None = None
    if OFFLINE_ACCESS_SCOPE in scopes:
        refresh_token = tokens.create_refresh_token()
        await store.save_refresh_token(
            refresh_token,
            RefreshToken(client_id=client.client_id, user_id=str(user.id), scopes=scopes),
        )

    id_token = (
        tokens.create_id_token(
            subject=user.id,
            client_id=client.client_id,
            issuer=issuer,
            lifetime_seconds=id_token_ttl,
            nonce=nonce,
            claims=_claims_for(user, scopes),
        )
        if with_id_token
        else None
    )

    return IssuedTokens(
        access_token=tokens.create_access_token(
            subject=user.id,
            client_id=client.client_id,
            scopes=scopes,
            issuer=issuer,
            lifetime_seconds=access_token_ttl,
        ),
        expires_in=access_token_ttl,
        scopes=scopes,
        id_token=id_token,
        refresh_token=refresh_token,
    )


async def exchange_code(
    session: AsyncSession,
    *,
    client: OAuthClient,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    issuer: str,
    access_token_ttl: int,
    id_token_ttl: int,
) -> IssuedTokens:
    """Swap a one-time code for tokens."""
    stored = await store.take_code(code)
    if stored is None or stored.client_id != client.client_id:
        raise InvalidGrantError
    if stored.redirect_uri != redirect_uri:
        raise InvalidGrantError
    if not _verify_challenge(code_verifier, stored.code_challenge):
        raise InvalidGrantError

    user = await session.get(User, store.user_id_of(stored.user_id))
    if user is None or not user.is_active:
        raise InvalidGrantError

    return await _issue(
        session,
        client=client,
        user=user,
        scopes=stored.scopes,
        nonce=stored.nonce,
        issuer=issuer,
        access_token_ttl=access_token_ttl,
        id_token_ttl=id_token_ttl,
        with_id_token=True,
    )


async def refresh_tokens(
    session: AsyncSession,
    *,
    client: OAuthClient,
    refresh_token: str,
    issuer: str,
    access_token_ttl: int,
    id_token_ttl: int,
) -> IssuedTokens:
    """Hand out a new access token, and a new refresh token in its place."""
    stored = await store.take_refresh_token(refresh_token)
    if stored is None or stored.client_id != client.client_id:
        raise InvalidGrantError

    user = await session.get(User, store.user_id_of(stored.user_id))
    if user is None or not user.is_active:
        raise InvalidGrantError

    return await _issue(
        session,
        client=client,
        user=user,
        scopes=stored.scopes,
        nonce=None,
        issuer=issuer,
        access_token_ttl=access_token_ttl,
        id_token_ttl=id_token_ttl,
        with_id_token=False,
    )


async def user_claims(session: AsyncSession, *, access_token: str, issuer: str) -> dict[str, Any]:
    """Return the claims behind an access token, for the userinfo endpoint."""
    try:
        claims = tokens.decode_access_token(access_token, issuer=issuer)
    except tokens.InvalidTokenError as error:
        raise InvalidGrantError from error

    user = await session.get(User, store.user_id_of(str(claims["sub"])))
    if user is None or not user.is_active:
        raise InvalidGrantError

    scopes = str(claims.get("scope", "")).split()
    return {"sub": str(user.id), **_claims_for(user, scopes)}
