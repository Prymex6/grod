"""The OpenID Connect flow: consent, codes, tokens, claims and refreshes."""

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from grod.main import API_PREFIX

OAUTH = f"{API_PREFIX}/oauth"
REDIRECT_URI = "https://app.example.com/callback"
SCOPE = "openid profile email offline_access"


def pkce_pair() -> tuple[str, str]:
    """Return a PKCE verifier with its S256 challenge."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def create_client(client: httpx.AsyncClient, *, confidential: bool = True) -> dict[str, Any]:
    response = await client.post(
        f"{OAUTH}/clients",
        json={
            "name": "My application",
            "redirectUris": [REDIRECT_URI],
            "scopes": ["openid", "profile", "email", "offline_access"],
            "confidential": confidential,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def start_authorization(
    client: httpx.AsyncClient, *, client_id: str, challenge: str, state: str = "xyz"
) -> httpx.Response:
    return await client.get(
        f"{OAUTH}/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "nonce": "n-0S6_WzA2Mj",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )


def handle_from(response: httpx.Response) -> str:
    """Read the pending-request handle out of the redirect to the console."""
    assert response.status_code == httpx.codes.FOUND, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["request"][0]


async def sign_in_and_get_code(client: httpx.AsyncClient, *, client_id: str, challenge: str) -> str:
    started = await start_authorization(client, client_id=client_id, challenge=challenge)
    handle = handle_from(started)
    approved = await client.post(f"{OAUTH}/requests/{handle}/approve")
    assert approved.status_code == httpx.codes.OK, approved.text
    query = parse_qs(urlparse(approved.json()["redirectTo"]).query)
    assert query["state"] == ["xyz"]
    return str(query["code"][0])


async def test_discovery_and_jwks(client: httpx.AsyncClient) -> None:
    discovery = await client.get("/.well-known/openid-configuration")
    assert discovery.status_code == httpx.codes.OK
    document = discovery.json()
    assert document["issuer"] == "http://localhost:5173"
    assert document["code_challenge_methods_supported"] == ["S256"]

    jwks = await client.get("/.well-known/jwks.json")
    assert jwks.status_code == httpx.codes.OK
    keys = jwks.json()["keys"]
    assert keys[0]["kty"] == "RSA"
    assert "d" not in keys[0], "the private exponent must never be published"


async def test_consent_screen_describes_the_request(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    _, challenge = pkce_pair()

    started = await start_authorization(
        client, client_id=app_client["clientId"], challenge=challenge
    )
    described = await client.get(f"{OAUTH}/requests/{handle_from(started)}")

    assert described.status_code == httpx.codes.OK
    assert described.json()["clientName"] == "My application"
    assert described.json()["scopes"] == SCOPE.split()


async def test_full_authorization_code_flow(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    app_client = await create_client(client)
    verifier, challenge = pkce_pair()

    code = await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)

    exchanged = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_client["clientId"],
            "client_secret": app_client["clientSecret"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )
    assert exchanged.status_code == httpx.codes.OK, exchanged.text
    tokens = exchanged.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["id_token"]
    assert tokens["refresh_token"]

    claims = await client.get(
        f"{OAUTH}/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert claims.status_code == httpx.codes.OK
    assert claims.json() == {
        "sub": account["id"],
        "name": account["displayName"],
        "email": account["email"],
        "email_verified": False,
    }

    refreshed = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "refresh_token",
            "client_id": app_client["clientId"],
            "client_secret": app_client["clientSecret"],
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert refreshed.status_code == httpx.codes.OK
    assert refreshed.json()["access_token"] != tokens["access_token"]

    reused = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "refresh_token",
            "client_id": app_client["clientId"],
            "client_secret": app_client["clientSecret"],
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert reused.status_code == httpx.codes.BAD_REQUEST, "a refresh token works only once"


async def test_public_client_needs_no_secret(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client, confidential=False)
    assert app_client["clientSecret"] is None
    verifier, challenge = pkce_pair()

    code = await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)
    exchanged = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_client["clientId"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )

    assert exchanged.status_code == httpx.codes.OK, exchanged.text


async def test_code_cannot_be_reused(client: httpx.AsyncClient, account: dict[str, Any]) -> None:
    del account
    app_client = await create_client(client)
    verifier, challenge = pkce_pair()
    code = await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)
    body = {
        "grant_type": "authorization_code",
        "client_id": app_client["clientId"],
        "client_secret": app_client["clientSecret"],
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }

    assert (await client.post(f"{OAUTH}/token", data=body)).status_code == httpx.codes.OK
    assert (await client.post(f"{OAUTH}/token", data=body)).status_code == httpx.codes.BAD_REQUEST


async def test_wrong_code_verifier_is_rejected(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    _, challenge = pkce_pair()
    code = await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)

    exchanged = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_client["clientId"],
            "client_secret": app_client["clientSecret"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": "a-different-verifier-entirely",
        },
    )

    assert exchanged.status_code == httpx.codes.BAD_REQUEST


async def test_wrong_client_secret_is_rejected(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    verifier, challenge = pkce_pair()
    code = await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)

    exchanged = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "authorization_code",
            "client_id": app_client["clientId"],
            "client_secret": "not-the-secret",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )

    assert exchanged.status_code == httpx.codes.UNAUTHORIZED


async def test_unregistered_redirect_uri_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    _, challenge = pkce_pair()

    response = await client.get(
        f"{OAUTH}/authorize",
        params={
            "client_id": app_client["clientId"],
            "redirect_uri": "https://evil.example.com/callback",
            "response_type": "code",
            "scope": "openid",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )

    assert response.status_code == httpx.codes.BAD_REQUEST


async def test_authorization_without_pkce_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)

    response = await client.get(
        f"{OAUTH}/authorize",
        params={
            "client_id": app_client["clientId"],
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid",
            "state": "xyz",
        },
    )

    assert response.status_code == httpx.codes.FOUND
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["error"] == ["invalid_request"]
    assert query["state"] == ["xyz"]


async def test_denied_consent_reports_access_denied(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    _, challenge = pkce_pair()
    started = await start_authorization(
        client, client_id=app_client["clientId"], challenge=challenge
    )

    denied = await client.post(f"{OAUTH}/requests/{handle_from(started)}/deny")

    assert denied.status_code == httpx.codes.OK
    query = parse_qs(urlparse(denied.json()["redirectTo"]).query)
    assert query["error"] == ["access_denied"]


async def test_userinfo_rejects_a_bogus_token(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"{OAUTH}/userinfo", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED


async def test_registering_a_client_requires_a_session(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{OAUTH}/clients",
        json={"name": "App", "redirectUris": [REDIRECT_URI], "scopes": ["openid"]},
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED


async def test_allowed_application_skips_the_consent_screen(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    _, challenge = pkce_pair()
    await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)

    # The account already allowed this application, so Brama returns a code at once.
    again = await start_authorization(client, client_id=app_client["clientId"], challenge=challenge)

    assert again.status_code == httpx.codes.FOUND
    location = urlparse(again.headers["location"])
    assert location.netloc == "app.example.com"
    assert "code" in parse_qs(location.query)


async def test_granted_applications_are_listed(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    _, challenge = pkce_pair()
    await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)

    listed = await client.get(f"{OAUTH}/authorizations")

    assert listed.status_code == httpx.codes.OK
    granted = listed.json()
    assert len(granted) == 1
    assert granted[0]["name"] == "My application"
    assert granted[0]["scopes"] == SCOPE.split()


async def test_revoking_access_kills_refresh_tokens_and_asks_again(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    app_client = await create_client(client)
    verifier, challenge = pkce_pair()
    code = await sign_in_and_get_code(client, client_id=app_client["clientId"], challenge=challenge)
    tokens = (
        await client.post(
            f"{OAUTH}/token",
            data={
                "grant_type": "authorization_code",
                "client_id": app_client["clientId"],
                "client_secret": app_client["clientSecret"],
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
    ).json()

    revoked = await client.delete(f"{OAUTH}/authorizations/{app_client['clientId']}")
    assert revoked.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(f"{OAUTH}/authorizations")).json() == []

    refreshed = await client.post(
        f"{OAUTH}/token",
        data={
            "grant_type": "refresh_token",
            "client_id": app_client["clientId"],
            "client_secret": app_client["clientSecret"],
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert refreshed.status_code == httpx.codes.BAD_REQUEST, "revoking must kill refresh tokens"

    # Without a grant the consent screen comes back.
    again = await start_authorization(client, client_id=app_client["clientId"], challenge=challenge)
    assert "/oauth/consent" in again.headers["location"]


async def test_revoking_an_unknown_application_is_a_not_found(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    response = await client.delete(f"{OAUTH}/authorizations/made-up-client")

    assert response.status_code == httpx.codes.NOT_FOUND
