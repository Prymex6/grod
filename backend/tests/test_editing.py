"""Editing files of a repository straight from the console."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.conftest import ACCOUNT_EMAIL, ACCOUNT_PASSWORD
from tests.test_collaboration import OTHER_LOGIN, sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    SLUG,
    create_project,
    register_other,
    seed_repository,
)

PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
FILES = f"{PROJECT}/files"
MEMBERS = f"{PROJECT}/members"

NOTE = "# A note\n\nThe first line.\n"


async def tip_of(client: httpx.AsyncClient, branch: str = "main") -> str:
    """Where a branch stands now, as the console sees it."""
    branches = await client.get(f"{PROJECT}/branches")
    found = [item for item in branches.json() if item["name"] == branch]
    assert found, branches.text
    commit: str = found[0]["commit"]
    return commit


async def read(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return await client.get(f"{PROJECT}/file", params={"path": path})


@pytest.fixture
async def started(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A project with one commit in it."""
    del account
    project = await create_project(client)
    await seed_repository(project["id"], tmp_path / "work")
    return project


async def test_a_new_file_arrives_with_its_own_commit(
    client: httpx.AsyncClient, started: dict[str, Any]
) -> None:
    del started
    parent = await tip_of(client)

    written = await client.put(
        f"{FILES}/docs/note.md",
        json={
            "content": NOTE,
            "message": "Add a note",
            "branch": "main",
            "parentCommit": parent,
        },
    )
    assert written.status_code == httpx.codes.OK, written.text
    assert written.json()["branch"] == "main"
    assert written.json()["commit"] != parent

    assert (await read(client, "docs/note.md")).json()["text"] == NOTE
    history = await client.get(f"{PROJECT}/commits")
    assert history.json()[0]["subject"] == "Add a note"
    assert history.json()[0]["authorEmail"] == ACCOUNT_EMAIL


async def test_the_file_that_was_there_is_replaced(
    client: httpx.AsyncClient, started: dict[str, Any]
) -> None:
    del started
    changed = await client.put(
        f"{FILES}/README.md",
        json={
            "content": "Something else entirely\n",
            "message": "Rewrite README",
            "branch": "main",
            "parentCommit": await tip_of(client),
        },
    )
    assert changed.status_code == httpx.codes.OK, changed.text
    assert (await read(client, "README.md")).json()["text"] == "Something else entirely\n"
    # Everything else the commit did not touch stays where it was.
    assert (await read(client, "src/main.py")).status_code == httpx.codes.OK


async def test_an_edit_of_a_branch_that_moved_is_refused(
    client: httpx.AsyncClient, started: dict[str, Any]
) -> None:
    """Two people editing the same file must not overwrite each other quietly."""
    del started
    stale = await tip_of(client)
    await client.put(
        f"{FILES}/a.txt",
        json={
            "content": "first\n",
            "message": "First",
            "branch": "main",
            "parentCommit": stale,
        },
    )

    refused = await client.put(
        f"{FILES}/a.txt",
        json={"content": "second\n", "message": "Second", "branch": "main", "parentCommit": stale},
    )
    assert refused.status_code == httpx.codes.CONFLICT
    assert (await read(client, "a.txt")).json()["text"] == "first\n"


async def test_a_file_can_be_taken_out(client: httpx.AsyncClient, started: dict[str, Any]) -> None:
    del started
    removed = await client.delete(
        f"{FILES}/src/main.py",
        params={
            "branch": "main",
            "message": "Remove main.py",
            "parentCommit": await tip_of(client),
        },
    )
    assert removed.status_code == httpx.codes.OK, removed.text
    assert (await read(client, "src/main.py")).status_code == httpx.codes.NOT_FOUND
    assert (await read(client, "README.md")).status_code == httpx.codes.OK


async def test_a_path_may_not_step_out_of_the_repository(
    client: httpx.AsyncClient, started: dict[str, Any]
) -> None:
    del started
    body = {
        "content": "not allowed\n",
        "message": "An attempt",
        "branch": "main",
        "parentCommit": await tip_of(client),
    }
    refused = await client.put(f"{FILES}/.git/config", json=body)
    assert refused.status_code == httpx.codes.BAD_REQUEST

    # A path with .. in it never even reaches the endpoint: the URL is
    # normalised first, so it lands nowhere. Either way nothing is written.
    for path in ("../poza.txt", "a/../../outside.txt"):
        answer = await client.put(f"{FILES}/{path}", json=body)
        assert answer.status_code >= httpx.codes.BAD_REQUEST, path


async def test_writing_into_an_empty_repository_makes_the_first_commit(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await create_project(client, slug="empty")
    written = await client.put(
        f"{API_PREFIX}/projects/anna.k/empty/files/README.md",
        json={"content": NOTE, "message": "First commit", "branch": "main"},
    )
    assert written.status_code == httpx.codes.OK, written.text

    read_back = await client.get(
        f"{API_PREFIX}/projects/anna.k/empty/file", params={"path": "README.md"}
    )
    assert read_back.json()["text"] == NOTE


async def test_somebody_who_may_only_read_cannot_write(
    client: httpx.AsyncClient, started: dict[str, Any]
) -> None:
    del started
    parent = await tip_of(client)
    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    added = await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})
    assert added.status_code == httpx.codes.CREATED, added.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.put(
        f"{FILES}/cudze.txt",
        json={
            "content": "not allowed\n",
            "message": "An attempt",
            "branch": "main",
            "parentCommit": parent,
        },
    )
    assert refused.status_code == httpx.codes.FORBIDDEN


async def test_a_commit_from_the_console_sets_the_same_things_going(
    client: httpx.AsyncClient, started: dict[str, Any]
) -> None:
    """A change made here must not be a quieter push than one from a terminal."""
    del started
    await client.put(
        f"{FILES}/deploy.py",
        json={
            "content": "KEY = 'AKIAQJ7K2M9XPLRT4W6Z'\n",
            "message": "Add a deployment",
            "branch": "main",
            "parentCommit": await tip_of(client),
        },
    )

    findings = await client.get(f"{PROJECT}/findings")
    assert [item["rule"] for item in findings.json()] == ["aws-access-key"]
