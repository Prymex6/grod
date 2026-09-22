"""Suggestions written in a review, and turning them into a commit."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from grod.collaboration import suggestions
from grod.main import API_PREFIX
from tests.test_merge_requests import open_request, push_branch
from tests.test_repositories import SLUG, create_project, seed_repository

PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
MERGE_REQUESTS = f"{PROJECT}/merge-requests"

FILE_PATH = "src/main.py"
BEFORE = "print('x')\n"
SUGGESTED = 'print("poprawione")'


def suggestion_comment(text: str) -> str:
    """A review comment the way somebody writes one with a suggestion in it."""
    return f"Lepiej tak:\n\n```suggestion\n{text}\n```\n"


def test_a_suggestion_is_read_out_of_a_comment() -> None:
    assert suggestions.read_suggestion(suggestion_comment(SUGGESTED)) == SUGGESTED
    assert suggestions.read_suggestion("an ordinary remark with nothing in it") is None


def test_a_suggestion_with_nothing_in_it_takes_the_line_out() -> None:
    assert suggestions.read_suggestion("```suggestion\n```") == ""


def test_a_suggestion_may_span_several_lines() -> None:
    body = suggestion_comment("first\nsecond")

    assert suggestions.read_suggestion(body) == "first\nsecond"


@pytest.fixture
async def reviewable(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A merge request with one file worth commenting on."""
    del account
    project = await create_project(client)
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_branch(
        work,
        project["id"],
        branch="fix",
        path=FILE_PATH,
        content=BEFORE,
        message="A fix",
    )
    return {"project": project, "request": await open_request(client, source="fix")}


async def comment_on(client: httpx.AsyncClient, number: int, *, body: str, line: int = 1) -> str:
    written = await client.post(
        f"{MERGE_REQUESTS}/{number}/comments",
        json={"body": body, "filePath": FILE_PATH, "lineNumber": line},
    )
    assert written.status_code == httpx.codes.CREATED, written.text
    comment_id: str = written.json()["id"]
    return comment_id


async def test_a_suggestion_becomes_a_commit_on_the_branch(
    client: httpx.AsyncClient, reviewable: dict[str, Any]
) -> None:
    """Nobody copies the text by hand; the platform writes the commit."""
    number = reviewable["request"]["number"]
    comment_id = await comment_on(client, number, body=suggestion_comment(SUGGESTED))

    applied = await client.post(f"{MERGE_REQUESTS}/{number}/comments/{comment_id}/apply")
    assert applied.status_code == httpx.codes.OK, applied.text
    assert applied.json()["subject"].startswith("Apply suggestion")

    file = await client.get(f"{PROJECT}/file", params={"path": FILE_PATH, "ref": "fix"})
    assert file.json()["text"] == f"{SUGGESTED}\n"


async def test_an_empty_suggestion_takes_the_line_out(
    client: httpx.AsyncClient, reviewable: dict[str, Any]
) -> None:
    number = reviewable["request"]["number"]
    comment_id = await comment_on(client, number, body="```suggestion\n```")

    applied = await client.post(f"{MERGE_REQUESTS}/{number}/comments/{comment_id}/apply")
    assert applied.status_code == httpx.codes.OK, applied.text

    # It was the only line, so what is left is an empty file.
    file = await client.get(f"{PROJECT}/file", params={"path": FILE_PATH, "ref": "fix"})
    assert file.json()["text"] == ""


async def test_a_comment_without_a_suggestion_changes_nothing(
    client: httpx.AsyncClient, reviewable: dict[str, Any]
) -> None:
    number = reviewable["request"]["number"]
    comment_id = await comment_on(client, number, body="Just a remark, with no suggestion")

    refused = await client.post(f"{MERGE_REQUESTS}/{number}/comments/{comment_id}/apply")
    assert refused.status_code == httpx.codes.BAD_REQUEST


async def test_a_suggestion_about_a_line_that_is_gone_is_refused(
    client: httpx.AsyncClient, reviewable: dict[str, Any]
) -> None:
    number = reviewable["request"]["number"]
    comment_id = await comment_on(client, number, body=suggestion_comment("anything"), line=99)

    refused = await client.post(f"{MERGE_REQUESTS}/{number}/comments/{comment_id}/apply")
    assert refused.status_code == httpx.codes.CONFLICT


async def test_applying_a_suggestion_sets_the_same_things_going(
    client: httpx.AsyncClient, reviewable: dict[str, Any]
) -> None:
    """The commit is a push like any other, so the scanner looks at it too."""
    number = reviewable["request"]["number"]
    comment_id = await comment_on(
        client, number, body=suggestion_comment("KEY = 'AKIAQJ7K2M9XPLRT4W6Z'")
    )
    await client.post(f"{MERGE_REQUESTS}/{number}/comments/{comment_id}/apply")

    # The source branch is not the default one, so nothing is scanned yet.
    assert (await client.get(f"{PROJECT}/findings")).json() == []
