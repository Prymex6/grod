"""Registration, sign-in, two-factor and session handling."""

import httpx
import pyotp

from grod.config import get_settings
from grod.main import API_PREFIX

AUTH = f"{API_PREFIX}/auth"
EMAIL = "anna.k@grod.dev"
PASSWORD = "correct-horse-battery"
DISPLAY_NAME = "Anna Kowalska"


async def register(client: httpx.AsyncClient, **overrides: str) -> httpx.Response:
    body = {"email": EMAIL, "displayName": DISPLAY_NAME, "password": PASSWORD} | overrides
    return await client.post(f"{AUTH}/register", json=body)


async def enable_totp(client: httpx.AsyncClient) -> str:
    """Enrol an authenticator app and return its secret."""
    setup = await client.post(f"{AUTH}/totp/setup")
    secret = setup.json()["secret"]
    confirmed = await client.post(f"{AUTH}/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    assert confirmed.status_code == httpx.codes.NO_CONTENT
    return str(secret)


async def test_registration_signs_the_account_in(client: httpx.AsyncClient) -> None:
    response = await register(client)

    assert response.status_code == httpx.codes.CREATED
    body = response.json()
    assert body["status"] == "signed_in"
    assert body["account"]["email"] == EMAIL
    assert body["account"]["totpEnabled"] is False
    assert get_settings().session_cookie_name in response.cookies

    me = await client.get(f"{AUTH}/me")
    assert me.status_code == httpx.codes.OK
    assert me.json()["displayName"] == DISPLAY_NAME


async def test_registration_rejects_a_duplicate_email(client: httpx.AsyncClient) -> None:
    await register(client)

    duplicate = await register(client, displayName="Someone Else")

    assert duplicate.status_code == httpx.codes.CONFLICT


async def test_registration_rejects_a_short_password(client: httpx.AsyncClient) -> None:
    response = await register(client, password="short")

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_password_hash_is_never_returned(client: httpx.AsyncClient) -> None:
    response = await register(client)

    assert "password" not in response.text.lower()


async def test_sign_in_and_out(client: httpx.AsyncClient) -> None:
    await register(client)
    client.cookies.clear()

    signed_in = await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
    assert signed_in.status_code == httpx.codes.OK
    assert signed_in.json()["status"] == "signed_in"

    logged_out = await client.post(f"{AUTH}/logout")
    assert logged_out.status_code == httpx.codes.NO_CONTENT

    after = await client.get(f"{AUTH}/me")
    assert after.status_code == httpx.codes.UNAUTHORIZED


async def test_sign_in_rejects_a_wrong_password(client: httpx.AsyncClient) -> None:
    await register(client)
    client.cookies.clear()

    response = await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": "wrong-one"})

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert get_settings().session_cookie_name not in response.cookies


async def test_sign_in_rejects_an_unknown_email(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{AUTH}/login", json={"email": "nobody@grod.dev", "password": PASSWORD}
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED


async def test_sign_in_blocks_after_too_many_failures(client: httpx.AsyncClient) -> None:
    await register(client)
    client.cookies.clear()
    limit = get_settings().login_attempt_limit

    for _ in range(limit):
        await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": "wrong-one"})

    blocked = await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})

    assert blocked.status_code == httpx.codes.TOO_MANY_REQUESTS


async def test_sign_in_with_two_factor(client: httpx.AsyncClient) -> None:
    await register(client)
    secret = await enable_totp(client)
    client.cookies.clear()

    first_step = await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
    assert first_step.status_code == httpx.codes.OK
    assert first_step.json()["status"] == "totp_required"
    assert get_settings().session_cookie_name not in first_step.cookies

    pending_token = first_step.json()["pendingToken"]
    second_step = await client.post(
        f"{AUTH}/login/totp",
        json={"pendingToken": pending_token, "code": pyotp.TOTP(secret).now()},
    )

    assert second_step.status_code == httpx.codes.OK
    assert second_step.json()["status"] == "signed_in"
    assert (await client.get(f"{AUTH}/me")).json()["totpEnabled"] is True


async def test_two_factor_rejects_a_wrong_code(client: httpx.AsyncClient) -> None:
    await register(client)
    await enable_totp(client)
    client.cookies.clear()

    first_step = await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
    response = await client.post(
        f"{AUTH}/login/totp",
        json={"pendingToken": first_step.json()["pendingToken"], "code": "000000"},
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED


async def test_pending_token_cannot_be_reused(client: httpx.AsyncClient) -> None:
    await register(client)
    secret = await enable_totp(client)
    client.cookies.clear()

    first_step = await client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
    pending_token = first_step.json()["pendingToken"]
    body = {"pendingToken": pending_token, "code": pyotp.TOTP(secret).now()}

    assert (await client.post(f"{AUTH}/login/totp", json=body)).status_code == httpx.codes.OK
    replayed = await client.post(f"{AUTH}/login/totp", json=body)

    assert replayed.status_code == httpx.codes.UNAUTHORIZED


async def test_endpoints_require_a_session(client: httpx.AsyncClient) -> None:
    for path in (f"{AUTH}/me", f"{AUTH}/totp/setup", f"{AUTH}/logout"):
        method = client.get if path.endswith("/me") else client.post
        response = await method(path)
        assert response.status_code == httpx.codes.UNAUTHORIZED, path
