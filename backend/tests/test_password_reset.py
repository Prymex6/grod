"""Setting a new password from a link sent by email."""

import re
from typing import Any

import httpx

from grod.main import API_PREFIX
from tests.conftest import ACCOUNT_EMAIL, ACCOUNT_PASSWORD

AUTH = f"{API_PREFIX}/auth"
NEW_PASSWORD = "brand-new-password-2026"


def token_from(body: str) -> str:
    """Read the reset token out of the message."""
    found = re.search(r"token=([\w-]+)", body)
    assert found, body
    return found.group(1)


async def test_reset_link_is_sent_to_a_known_account(
    client: httpx.AsyncClient, account: dict[str, Any], captured_emails: list[dict[str, str]]
) -> None:
    del account
    response = await client.post(f"{AUTH}/password/reset-request", json={"email": ACCOUNT_EMAIL})

    assert response.status_code == httpx.codes.ACCEPTED
    assert len(captured_emails) == 1
    assert captured_emails[0]["to"] == ACCOUNT_EMAIL
    assert "/password/reset?token=" in captured_emails[0]["body"]


async def test_unknown_address_gets_the_same_answer(
    client: httpx.AsyncClient, captured_emails: list[dict[str, str]]
) -> None:
    response = await client.post(
        f"{AUTH}/password/reset-request", json={"email": "nobody@grod.dev"}
    )

    assert response.status_code == httpx.codes.ACCEPTED
    assert captured_emails == [], "an answer must not reveal that the account is missing"


async def test_reset_sets_the_new_password_and_signs_devices_out(
    client: httpx.AsyncClient, account: dict[str, Any], captured_emails: list[dict[str, str]]
) -> None:
    del account
    await client.post(f"{AUTH}/password/reset-request", json={"email": ACCOUNT_EMAIL})
    token = token_from(captured_emails[0]["body"])

    reset = await client.post(
        f"{AUTH}/password/reset", json={"token": token, "password": NEW_PASSWORD}
    )
    assert reset.status_code == httpx.codes.NO_CONTENT

    # The session from registration is gone.
    assert (await client.get(f"{AUTH}/me")).status_code == httpx.codes.UNAUTHORIZED

    old = await client.post(
        f"{AUTH}/login", json={"email": ACCOUNT_EMAIL, "password": ACCOUNT_PASSWORD}
    )
    assert old.status_code == httpx.codes.UNAUTHORIZED

    new = await client.post(
        f"{AUTH}/login", json={"email": ACCOUNT_EMAIL, "password": NEW_PASSWORD}
    )
    assert new.status_code == httpx.codes.OK


async def test_reset_link_works_only_once(
    client: httpx.AsyncClient, account: dict[str, Any], captured_emails: list[dict[str, str]]
) -> None:
    del account
    await client.post(f"{AUTH}/password/reset-request", json={"email": ACCOUNT_EMAIL})
    body = {"token": token_from(captured_emails[0]["body"]), "password": NEW_PASSWORD}

    assert (await client.post(f"{AUTH}/password/reset", json=body)).status_code == (
        httpx.codes.NO_CONTENT
    )
    assert (await client.post(f"{AUTH}/password/reset", json=body)).status_code == (
        httpx.codes.BAD_REQUEST
    )


async def test_unknown_reset_token_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{AUTH}/password/reset", json={"token": "made-up", "password": NEW_PASSWORD}
    )

    assert response.status_code == httpx.codes.BAD_REQUEST


async def test_reset_requires_a_long_enough_password(
    client: httpx.AsyncClient, account: dict[str, Any], captured_emails: list[dict[str, str]]
) -> None:
    del account
    await client.post(f"{AUTH}/password/reset-request", json={"email": ACCOUNT_EMAIL})

    response = await client.post(
        f"{AUTH}/password/reset",
        json={"token": token_from(captured_emails[0]["body"]), "password": "short"},
    )

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY
