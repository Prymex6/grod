"""Project members, issues and the discussion under them."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    OWNER_LOGIN,
    SLUG,
    basic_header,
    create_project,
    make_token,
    register_other,
    seed_repository,
)

BASE = f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}"
ISSUES = f"{BASE}/issues"
MEMBERS = f"{BASE}/members"
OTHER_LOGIN = "piotr.m"
ACCOUNT_EMAIL = "anna.k@grod.dev"
ACCOUNT_PASSWORD = "correct-horse-battery"


async def sign_in(client: httpx.AsyncClient, *, email: str, password: str) -> None:
    """Swap the session of the client for another account."""
    client.cookies.clear()
    response = await client.post(
        f"{API_PREFIX}/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == httpx.codes.OK, response.text


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client)


async def test_a_member_may_read_a_private_project(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)

    added = await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})
    assert added.status_code == httpx.codes.CREATED, added.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    seen = await client.get(f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}")

    assert seen.status_code == httpx.codes.OK, "a guest sees a private project"


async def test_a_guest_may_not_push_but_a_developer_may(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    guest_token = await make_token(client, scopes=["repo:read", "repo:write"])
    address = f"/{OWNER_LOGIN}/{SLUG}.git/info/refs?service=git-receive-pack"
    client.cookies.clear()

    as_guest = await client.get(address, headers=basic_header(guest_token))
    assert as_guest.status_code == httpx.codes.FORBIDDEN, "a guest must not push"

    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "developer"})
    client.cookies.clear()

    as_developer = await client.get(address, headers=basic_header(guest_token))
    assert as_developer.status_code == httpx.codes.OK, "a developer may push"


async def test_only_a_maintainer_may_manage_members(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "developer"})

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "maintainer"})
    assert refused.status_code == httpx.codes.FORBIDDEN

    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "maintainer"})

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    allowed = await client.get(MEMBERS)
    assert [member["role"] for member in allowed.json()] == ["maintainer"]


async def test_the_owner_cannot_be_added_as_a_member(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    response = await client.post(MEMBERS, json={"login": OWNER_LOGIN, "role": "developer"})

    assert response.status_code == httpx.codes.CONFLICT


async def test_a_member_can_be_taken_off_the_project(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "developer"})

    removed = await client.delete(f"{MEMBERS}/{OTHER_LOGIN}")

    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(MEMBERS)).json() == []

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    assert (await client.get(f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}")).status_code == (
        httpx.codes.NOT_FOUND
    )


async def test_issues_are_numbered_from_one(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    first = await client.post(ISSUES, json={"title": "First job"})
    second = await client.post(ISSUES, json={"title": "Second job"})

    assert first.status_code == httpx.codes.CREATED, first.text
    assert first.json()["number"] == 1
    assert second.json()["number"] == 2
    assert first.json()["state"] == "open"
    assert first.json()["author"]["login"] == OWNER_LOGIN


async def test_issues_are_listed_newest_first_and_can_be_filtered(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.post(ISSUES, json={"title": "Old"})
    await client.post(ISSUES, json={"title": "New"})
    await client.patch(f"{ISSUES}/1", json={"state": "closed"})

    everything = await client.get(ISSUES)
    open_only = await client.get(ISSUES, params={"state": "open"})
    closed_only = await client.get(ISSUES, params={"state": "closed"})

    assert [issue["title"] for issue in everything.json()] == ["New", "Old"]
    assert [issue["number"] for issue in open_only.json()] == [2]
    assert [issue["number"] for issue in closed_only.json()] == [1]
    assert closed_only.json()[0]["closedAt"] is not None


async def test_an_issue_can_be_edited_and_closed_by_its_author(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.post(ISSUES, json={"title": "Needs fixing", "description": "A description"})

    changed = await client.patch(f"{ISSUES}/1", json={"title": "Fixed", "state": "closed"})

    assert changed.status_code == httpx.codes.OK
    assert changed.json()["title"] == "Fixed"
    assert changed.json()["state"] == "closed"
    assert changed.json()["updatedAt"] is not None


async def test_a_stranger_may_not_edit_someone_elses_issue(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.post(ISSUES, json={"title": "My job"})
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.patch(f"{ISSUES}/1", json={"title": "Replaced"})

    assert refused.status_code == httpx.codes.FORBIDDEN


async def test_a_guest_may_open_an_issue_and_answer_it(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    opened = await client.post(ISSUES, json={"title": "An issue from a guest"})
    assert opened.status_code == httpx.codes.CREATED
    assert opened.json()["author"]["login"] == OTHER_LOGIN

    commented = await client.post(f"{ISSUES}/1/comments", json={"body": "Confirmed, same here."})
    assert commented.status_code == httpx.codes.CREATED

    listed = await client.get(f"{ISSUES}/1/comments")
    assert [comment["body"] for comment in listed.json()] == ["Confirmed, same here."]
    assert listed.json()[0]["author"]["login"] == OTHER_LOGIN


async def test_a_comment_can_be_removed_by_its_author(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.post(ISSUES, json={"title": "A job"})
    comment = await client.post(f"{ISSUES}/1/comments", json={"body": "To be deleted"})

    removed = await client.delete(f"{ISSUES}/1/comments/{comment.json()['id']}")

    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(f"{ISSUES}/1/comments")).json() == []


async def test_issues_of_a_private_project_stay_hidden(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.post(ISSUES, json={"title": "Secret job"})
    client.cookies.clear()

    response = await client.get(ISSUES)

    assert response.status_code == httpx.codes.NOT_FOUND


async def test_a_missing_issue_is_reported(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    response = await client.get(f"{ISSUES}/404")

    assert response.status_code == httpx.codes.NOT_FOUND
