"""Stars given to projects and the public profile of an account."""

from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    OWNER_LOGIN,
    SLUG,
    create_project,
    register_other,
)

ACCOUNT_EMAIL = "anna.k@grod.dev"
ACCOUNT_PASSWORD = "correct-horse-battery"
PROFILE = f"{API_PREFIX}/users/{OWNER_LOGIN}"
STAR = f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}/star"


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client, visibility="public")


async def test_a_star_is_counted_once(client: httpx.AsyncClient, project: dict[str, Any]) -> None:
    del project
    first = await client.put(STAR)
    assert first.status_code == httpx.codes.NO_CONTENT, first.text

    # Starring again must not raise the count.
    await client.put(STAR)

    read = await client.get(f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}")
    assert read.json()["stars"] == 1
    assert read.json()["starred"] is True

    starred = await client.get(f"{API_PREFIX}/starred")
    assert [item["slug"] for item in starred.json()] == [SLUG]

    removed = await client.delete(STAR)
    assert removed.status_code == httpx.codes.NO_CONTENT

    after = await client.get(f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}")
    assert after.json()["stars"] == 0
    assert after.json()["starred"] is False


async def test_taking_back_a_star_nobody_gave(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    missing = await client.delete(STAR)
    assert missing.status_code == httpx.codes.NOT_FOUND


async def test_a_profile_shows_public_projects_and_stars(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await create_project(client, slug="vault", visibility="private")
    await client.put(STAR)

    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    seen = await client.get(PROFILE)

    assert seen.status_code == httpx.codes.OK, seen.text
    profile = seen.json()
    assert profile["login"] == OWNER_LOGIN
    assert [item["slug"] for item in profile["projects"]] == [SLUG], "the private one stays hidden"
    assert profile["starsReceived"] == 1
    assert profile["projects"][0]["starred"] is False, "somebody else's star is not mine"


async def test_the_owner_sees_every_project_on_their_profile(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await create_project(client, slug="vault", visibility="private")

    seen = await client.get(PROFILE)

    slugs = {item["slug"] for item in seen.json()["projects"]}
    assert slugs == {SLUG, "vault"}


async def test_a_profile_that_does_not_exist(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    missing = await client.get(f"{API_PREFIX}/users/nikt")
    assert missing.status_code == httpx.codes.NOT_FOUND


async def test_a_visitor_without_an_account_reads_a_profile(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    client.cookies.clear()

    seen = await client.get(PROFILE)

    assert seen.status_code == httpx.codes.OK, seen.text
    assert [item["slug"] for item in seen.json()["projects"]] == [SLUG]
