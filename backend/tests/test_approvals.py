"""Who has to say yes before a change goes in."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grod.collaboration import approvals, merge_queue
from grod.main import API_PREFIX
from grod.repositories import git
from tests.conftest import ACCOUNT_EMAIL, ACCOUNT_PASSWORD
from tests.test_collaboration import OTHER_LOGIN, sign_in
from tests.test_merge_requests import open_request, push_branch
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    SLUG,
    create_project,
    register_other,
    run_git,
    seed_repository,
)

PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
MERGE_REQUESTS = f"{PROJECT}/merge-requests"
MEMBERS = f"{PROJECT}/members"
RULES = f"{PROJECT}/merge-rules"

OWNERS_FILE = ".grod/owners"


def test_the_owners_file_is_read_the_way_such_files_are() -> None:
    rules = approvals.parse_owners(
        """
        # who answers for what
        *            @anna.k
        src/         @piotr.m @anna.k
        docs/*.md    @piotr.m
        """
    )

    assert [rule.pattern for rule in rules] == ["*", "src/", "docs/*.md"]
    # The last matching line wins, so the general rule does not swallow the rest.
    assert approvals.owners_of("README.md", rules) == ("anna.k",)
    assert approvals.owners_of("src/main.py", rules) == ("piotr.m", "anna.k")
    assert approvals.owners_of("docs/guide.md", rules) == ("piotr.m",)


def test_lines_that_say_nothing_are_skipped() -> None:
    rules = approvals.parse_owners("# only a comment\n\n   \nwithout-owners\n")

    assert rules == []


@pytest.fixture
async def request_of_anna(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A merge request opened by Anna, with Piotr able to review it."""
    del account
    project = await create_project(client)
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_branch(
        work,
        project["id"],
        branch="guide",
        path="docs/guide.md",
        content="# Guide\n",
        message="Add a guide",
    )
    made = await open_request(client, source="guide")

    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    added = await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "developer"})
    assert added.status_code == httpx.codes.CREATED, added.text
    return {"project": project, "work": work, "request": made}


async def test_nobody_has_to_say_yes_by_default(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    number = request_of_anna["request"]["number"]
    state = await client.get(f"{MERGE_REQUESTS}/{number}/approvals")

    assert state.json()["required"] == 0
    assert state.json()["satisfied"] is True


async def test_a_project_may_ask_for_one_yes(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    await client.put(RULES, json={"requiredApprovals": 1, "requiredChecks": []})
    number = request_of_anna["request"]["number"]

    assert (await client.get(f"{MERGE_REQUESTS}/{number}/approvals")).json()["satisfied"] is False
    refused = await client.post(f"{MERGE_REQUESTS}/{number}/merge")
    assert refused.status_code == httpx.codes.CONFLICT

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    said = await client.post(f"{MERGE_REQUESTS}/{number}/approve")
    assert said.status_code == httpx.codes.CREATED, said.text
    assert said.json()["satisfied"] is True
    assert [item["login"] for item in said.json()["given"]] == [OTHER_LOGIN]

    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    merged = await client.post(f"{MERGE_REQUESTS}/{number}/merge")
    assert merged.status_code == httpx.codes.OK, merged.text


async def test_the_author_cannot_say_yes_to_their_own_change(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    number = request_of_anna["request"]["number"]
    refused = await client.post(f"{MERGE_REQUESTS}/{number}/approve")

    assert refused.status_code == httpx.codes.FORBIDDEN


async def test_saying_yes_twice_changes_nothing(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    number = request_of_anna["request"]["number"]
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    await client.post(f"{MERGE_REQUESTS}/{number}/approve")

    again = await client.post(f"{MERGE_REQUESTS}/{number}/approve")
    assert again.status_code == httpx.codes.CONFLICT


async def test_a_yes_can_be_taken_back(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    await client.put(RULES, json={"requiredApprovals": 1, "requiredChecks": []})
    number = request_of_anna["request"]["number"]

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    await client.post(f"{MERGE_REQUESTS}/{number}/approve")
    taken = await client.delete(f"{MERGE_REQUESTS}/{number}/approve")

    assert taken.json()["satisfied"] is False
    assert taken.json()["given"] == []


async def test_new_work_makes_an_older_yes_stop_counting(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    """What was read is no longer what would be merged."""
    await client.put(RULES, json={"requiredApprovals": 1, "requiredChecks": []})
    number = request_of_anna["request"]["number"]

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    await client.post(f"{MERGE_REQUESTS}/{number}/approve")
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)

    work = request_of_anna["work"]
    bare = str(git.repository_path(UUID(request_of_anna["project"]["id"])))
    await run_git("checkout", "guide", cwd=work)
    (work / "docs" / "guide.md").write_text("# Guide\n\nWiecej\n", encoding="utf-8")
    await run_git("add", ".", cwd=work)
    await run_git("commit", "-m", "Append", cwd=work)
    await run_git("push", bare, "guide", cwd=work)

    state = await client.get(f"{MERGE_REQUESTS}/{number}/approvals")
    assert state.json()["given"][0]["stale"] is True
    assert state.json()["counted"] == 0
    assert state.json()["satisfied"] is False


async def test_an_owner_of_the_touched_path_has_to_say_yes(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any]
) -> None:
    project_id = request_of_anna["project"]["id"]
    written = await client.put(
        f"{PROJECT}/files/{OWNERS_FILE}",
        json={
            "content": f"docs/*.md @{OTHER_LOGIN}\n",
            "message": "Add the owners file",
            "branch": "main",
            "parentCommit": await git.resolve_ref(UUID(project_id), "main"),
        },
    )
    assert written.status_code == httpx.codes.OK, written.text

    number = request_of_anna["request"]["number"]
    state = await client.get(f"{MERGE_REQUESTS}/{number}/approvals")
    assert state.json()["missingOwners"] == [OTHER_LOGIN]
    assert state.json()["satisfied"] is False

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    said = await client.post(f"{MERGE_REQUESTS}/{number}/approve")
    assert said.json()["missingOwners"] == []
    assert said.json()["satisfied"] is True


async def test_the_queue_will_not_take_what_nobody_approved(
    client: httpx.AsyncClient, request_of_anna: dict[str, Any], db_session: AsyncSession
) -> None:
    await client.put(RULES, json={"requiredApprovals": 1, "requiredChecks": []})
    number = request_of_anna["request"]["number"]
    entered = await client.post(f"{MERGE_REQUESTS}/{number}/queue")
    assert entered.status_code == httpx.codes.CREATED, entered.text

    await merge_queue.advance(db_session)

    # It was not tested and not merged; the queue said why.
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "open"
    assert (await client.get(f"{PROJECT}/merge-queue")).json() == []
