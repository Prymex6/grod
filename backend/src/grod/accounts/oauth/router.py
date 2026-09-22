"""OpenID Connect endpoints: authorize, consent, token, userinfo, discovery."""

from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.oauth import service, store
from grod.accounts.oauth.keys import SIGNING_ALGORITHM, get_public_jwks
from grod.accounts.oauth.models import OAuthClient
from grod.accounts.oauth.schemas import (
    AuthorizationView,
    ClientRegistration,
    ClientView,
    ConsentDecision,
    ConsentRequestView,
    NewClientView,
    TokenResponse,
)
from grod.config import Settings, get_settings
from grod.db import get_db_session

router = APIRouter(prefix="/oauth", tags=["accounts-oauth"])
discovery_router = APIRouter(tags=["accounts-oauth"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

GRANT_AUTHORIZATION_CODE = "authorization_code"
GRANT_REFRESH_TOKEN = "refresh_token"  # noqa: S105  (a grant name, not a secret)
BEARER_PREFIX = "Bearer "


def _redirect_with(target: str, params: dict[str, str]) -> RedirectResponse:
    separator = "&" if "?" in target else "?"
    return RedirectResponse(
        f"{target}{separator}{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )


def _client_fields(client: OAuthClient) -> dict[str, Any]:
    """Shape a client row the way both client views expect it."""
    return {
        "id": client.id,
        "client_id": client.client_id,
        "name": client.name,
        "redirect_uris": client.redirect_uris,
        "scopes": client.scopes,
        "confidential": client.is_confidential,
        "created_at": client.created_at,
    }


@router.get("/authorize")
async def authorize(
    request: Request,
    db: DbSession,
    settings: SettingsDependency,
    user: OptionalUser,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    scope: str,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    state: str | None = None,
    nonce: str | None = None,
) -> RedirectResponse:
    """Start a sign-in: park the request and send the browser to the console."""
    del request
    try:
        client, parked = await service.start_authorization(
            db,
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            scope=scope,
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
    except service.InvalidClientError, service.InvalidRedirectUriError:
        # With an untrusted client or address there is nowhere safe to redirect.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown client") from None
    except service.InvalidRequestError:
        params = {"error": "invalid_request"}
        if state is not None:
            params["state"] = state
        return _redirect_with(redirect_uri, params)

    requested = scope.split()
    if user is not None and await service.has_grant(db, user=user, client=client, scopes=requested):
        pending = await store.take_request(parked)
        if pending is not None:
            approved = await service.issue_code_for(request=pending, user=user)
            params = {"code": approved.code}
            if approved.state is not None:
                params["state"] = approved.state
            return _redirect_with(approved.redirect_uri, params)

    return _redirect_with(f"{settings.public_url}oauth/consent", {"request": parked})


@router.get("/requests/{handle}")
async def consent_request(handle: str, db: DbSession, user: CurrentUser) -> ConsentRequestView:
    """Describe a pending request so the console can ask for consent."""
    del user
    request = await store.read_request(handle)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request expired")
    client = await service.find_client(db, request.client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request expired")
    return ConsentRequestView(client_name=client.name, scopes=request.scopes)


@router.post("/requests/{handle}/approve")
async def approve(handle: str, db: DbSession, user: CurrentUser) -> ConsentDecision:
    """Consent: issue the one-time code and say where to send the browser."""
    approved = await service.approve_authorization(db, handle=handle, user=user)
    if approved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request expired")
    params = {"code": approved.code}
    if approved.state is not None:
        params["state"] = approved.state
    separator = "&" if "?" in approved.redirect_uri else "?"
    return ConsentDecision(redirect_to=f"{approved.redirect_uri}{separator}{urlencode(params)}")


@router.post("/requests/{handle}/deny")
async def deny(handle: str, user: CurrentUser) -> ConsentDecision:
    """Refusal: send the browser back with an error, as the standard says."""
    del user
    request = await store.take_request(handle)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request expired")
    params = {"error": "access_denied"}
    if request.state is not None:
        params["state"] = request.state
    separator = "&" if "?" in request.redirect_uri else "?"
    return ConsentDecision(redirect_to=f"{request.redirect_uri}{separator}{urlencode(params)}")


@router.post("/token")
async def token(
    db: DbSession,
    settings: SettingsDependency,
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
) -> TokenResponse:
    """Exchange a code or a refresh token for tokens."""
    try:
        client = await service.authenticate_client(
            db, client_id=client_id, client_secret=client_secret
        )
    except service.InvalidClientError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_client") from None

    issuer = str(settings.public_url).rstrip("/")
    try:
        if grant_type == GRANT_AUTHORIZATION_CODE:
            if not code or not redirect_uri or not code_verifier:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_request")
            issued = await service.exchange_code(
                db,
                client=client,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
                issuer=issuer,
                access_token_ttl=settings.oauth_access_token_ttl_seconds,
                id_token_ttl=settings.oauth_id_token_ttl_seconds,
            )
        elif grant_type == GRANT_REFRESH_TOKEN:
            if not refresh_token:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_request")
            issued = await service.refresh_tokens(
                db,
                client=client,
                refresh_token=refresh_token,
                issuer=issuer,
                access_token_ttl=settings.oauth_access_token_ttl_seconds,
                id_token_ttl=settings.oauth_id_token_ttl_seconds,
            )
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="unsupported_grant_type")
    except service.InvalidGrantError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_grant") from None

    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        scope=" ".join(issued.scopes),
        id_token=issued.id_token,
        refresh_token=issued.refresh_token,
    )


@router.get("/userinfo")
async def userinfo(
    db: DbSession,
    settings: SettingsDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return the claims behind a bearer access token."""
    if authorization is None or not authorization.startswith(BEARER_PREFIX):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    try:
        return await service.user_claims(
            db,
            access_token=authorization.removeprefix(BEARER_PREFIX),
            issuer=str(settings.public_url).rstrip("/"),
        )
    except service.InvalidGrantError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_token") from None


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def register_client(
    body: ClientRegistration, db: DbSession, user: CurrentUser
) -> NewClientView:
    """Register an application of the signed-in account."""
    try:
        created = await service.register_client(
            db,
            owner=user,
            name=body.name,
            redirect_uris=[str(uri) for uri in body.redirect_uris],
            scopes=body.scopes,
            confidential=body.confidential,
        )
    except service.InvalidRequestError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Unsupported scope; openid is required"
        ) from None
    return NewClientView.model_validate(
        {**_client_fields(created.client), "client_secret": created.client_secret}
    )


@router.get("/clients")
async def list_clients(db: DbSession, user: CurrentUser) -> list[ClientView]:
    """Return the applications registered by the signed-in account."""
    clients = await service.list_clients(db, owner=user)
    return [ClientView.model_validate(_client_fields(client)) for client in clients]


@router.get("/authorizations")
async def list_authorizations(db: DbSession, user: CurrentUser) -> list[AuthorizationView]:
    """Return the applications this account has allowed."""
    grants = await service.list_grants(db, user=user)
    return [
        AuthorizationView.model_validate(
            {
                "client_id": client.client_id,
                "name": client.name,
                "scopes": grant.scopes,
                "granted_at": grant.created_at,
            }
        )
        for grant, client in grants
    ]


@router.delete("/authorizations/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_authorization(client_id: str, db: DbSession, user: CurrentUser) -> None:
    """Take an application's access to this account away."""
    if not await service.revoke_grant(db, user=user, client_id=client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown application")


@discovery_router.get("/.well-known/openid-configuration")
async def discovery(settings: SettingsDependency) -> dict[str, Any]:
    """Tell clients where our endpoints are."""
    issuer = str(settings.public_url).rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/api/v1/oauth/authorize",
        "token_endpoint": f"{issuer}/api/v1/oauth/token",
        "userinfo_endpoint": f"{issuer}/api/v1/oauth/userinfo",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": [GRANT_AUTHORIZATION_CODE, GRANT_REFRESH_TOKEN],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [SIGNING_ALGORITHM],
        "scopes_supported": list(service.SUPPORTED_SCOPES),
        "code_challenge_methods_supported": [service.SUPPORTED_CODE_CHALLENGE_METHOD],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "claims_supported": ["sub", "name", "email", "email_verified"],
    }


@discovery_router.get("/.well-known/jwks.json")
async def jwks() -> dict[str, Any]:
    """Public keys clients use to verify our tokens."""
    return get_public_jwks()
