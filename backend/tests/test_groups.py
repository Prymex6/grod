"""Groups: the shared namespace, its members and what they may do."""

from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    create_project,
    register_other,
)

GROUPS = f"{API_PREFIX}/groups"
GROUP_SLUG = "kowalski"
GROUP = f"{GROUPS}/{GROUP_SLUG}"
PROJECT_SLUG = "tools"
OTHER_LOGIN = "piotr.m"
ACCOUNT_EMAIL = "anna.k@grod.dev"
ACCOUNT_PASSWORD = "correct-horse-battery"


async def make_group(client: httpx.AsyncClient, *, visibility: str = "private") -> dict[str, Any]:
    response = await client.post(
        GROUPS,
        json={
            "slug": GROUP_SLUG,
            "name": "Kowalski",
            "description": "Shared projects",
            "visibility": visibility,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


@pytest.fixture
async def group(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await make_group(client)


async def test_whoever_creates_a_group_owns_it(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    assert group["role"] == "owner"
    assert group["memberCount"] == 1

    listed = await client.get(GROUPS)
    assert [item["slug"] for item in listed.json()] == [GROUP_SLUG]


async def test_a_group_may_not_take_the_address_of_an_account(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    taken = await client.post(GROUPS, json={"slug": account["login"], "name": "Impersonator"})
    assert taken.status_code == httpx.codes.CONFLICT


async def test_a_project_of_a_group_answers_under_its_address(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    del group
    created = await client.post(
        f"{API_PREFIX}/projects",
        json={"slug": PROJECT_SLUG, "name": "Tools", "group": GROUP_SLUG},
    )
    assert created.status_code == httpx.codes.CREATED, created.text
    assert created.json()["ownerLogin"] == GROUP_SLUG
    assert created.json()["cloneUrl"].endswith(f"/{GROUP_SLUG}/{PROJECT_SLUG}.git")

    read = await client.get(f"{API_PREFIX}/projects/{GROUP_SLUG}/{PROJECT_SLUG}")
    assert read.status_code == httpx.codes.OK, read.text

    # A group project is not a personal one, so it stays out of that listing.
    personal = await client.get(f"{API_PREFIX}/projects")
    assert [item["slug"] for item in personal.json()] == []

    of_group = await client.get(f"{GROUP}/projects")
    assert [item["slug"] for item in of_group.json()] == [PROJECT_SLUG]


async def test_a_developer_of_a_group_may_push_to_its_projects(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    del group
    await client.post(
        f"{API_PREFIX}/projects",
        json={"slug": PROJECT_SLUG, "name": "Tools", "group": GROUP_SLUG},
    )
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    added = await client.post(f"{GROUP}/members", json={"login": OTHER_LOGIN, "role": "developer"})
    assert added.status_code == httpx.codes.CREATED, added.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    seen = await client.get(f"{API_PREFIX}/projects/{GROUP_SLUG}/{PROJECT_SLUG}")

    assert seen.status_code == httpx.codes.OK, "a member reads a private group project"
    access = seen.json()["access"]
    assert access["write"] is True
    assert access["manage"] is False


async def test_a_stranger_does_not_see_a_private_group(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    del group
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    seen = await client.get(GROUP)
    assert seen.status_code == httpx.codes.NOT_FOUND

    refused = await client.post(
        f"{API_PREFIX}/projects",
        json={"slug": PROJECT_SLUG, "name": "Tools", "group": GROUP_SLUG},
    )
    assert refused.status_code == httpx.codes.NOT_FOUND, "nor may they fill it"


async def test_a_guest_may_not_change_the_group(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    del group
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(f"{GROUP}/members", json={"login": OTHER_LOGIN, "role": "guest"})

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.patch(GROUP, json={"name": "Mine"})

    assert refused.status_code == httpx.codes.FORBIDDEN


async def test_the_last_owner_may_not_leave(
    client: httpx.AsyncClient, group: dict[str, Any], account: dict[str, Any]
) -> None:
    del group
    stuck = await client.delete(f"{GROUP}/members/{account['login']}")

    assert stuck.status_code == httpx.codes.CONFLICT


async def test_a_group_with_projects_is_not_deleted(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    del group
    await client.post(
        f"{API_PREFIX}/projects",
        json={"slug": PROJECT_SLUG, "name": "Tools", "group": GROUP_SLUG},
    )

    refused = await client.delete(GROUP)
    assert refused.status_code == httpx.codes.CONFLICT

    await client.delete(f"{API_PREFIX}/projects/{GROUP_SLUG}/{PROJECT_SLUG}")
    removed = await client.delete(GROUP)
    assert removed.status_code == httpx.codes.NO_CONTENT


async def test_two_groups_may_hold_projects_with_the_same_address(
    client: httpx.AsyncClient, group: dict[str, Any]
) -> None:
    del group
    await create_project(client, slug=PROJECT_SLUG)
    in_group = await client.post(
        f"{API_PREFIX}/projects",
        json={"slug": PROJECT_SLUG, "name": "Tools", "group": GROUP_SLUG},
    )

    assert in_group.status_code == httpx.codes.CREATED, in_group.text
