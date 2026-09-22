"""Merge requests standing one on another, and what a merge does to them."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from grod.main import API_PREFIX
from grod.repositories import git
from tests.test_repositories import SLUG, create_project, run_git, seed_repository

PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
MERGE_REQUESTS = f"{PROJECT}/merge-requests"


async def branch_from(
    work_dir: Path, project_id: str, *, base: str, branch: str, path: str, content: str
) -> None:
    """Start a branch off another one, put one commit on it and push it."""
    bare = str(git.repository_path(UUID(project_id)))
    await run_git("checkout", base, cwd=work_dir)
    await run_git("checkout", "-b", branch, cwd=work_dir)
    target = work_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", f"Add {path}", cwd=work_dir)
    await run_git("push", bare, branch, cwd=work_dir)


async def open_request(client: httpx.AsyncClient, *, title: str, source: str, target: str) -> int:
    made = await client.post(
        MERGE_REQUESTS,
        json={"title": title, "description": "", "sourceBranch": source, "targetBranch": target},
    )
    assert made.status_code == httpx.codes.CREATED, made.text
    number: int = made.json()["number"]
    return number


@pytest.fixture
async def stacked(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """Three requests in a row: main <- first <- second <- third."""
    del account
    project = await create_project(client)
    work = tmp_path / "work"
    await seed_repository(project["id"], work)

    await branch_from(work, project["id"], base="main", branch="first", path="a.txt", content="a\n")
    await branch_from(
        work, project["id"], base="first", branch="second", path="b.txt", content="b\n"
    )
    await branch_from(
        work, project["id"], base="second", branch="third", path="c.txt", content="c\n"
    )

    first = await open_request(client, title="First", source="first", target="main")
    second = await open_request(client, title="Second", source="second", target="first")
    third = await open_request(client, title="Third", source="third", target="second")
    return {"project": project, "work": work, "numbers": (first, second, third)}


async def test_the_stack_is_read_off_the_branches(
    client: httpx.AsyncClient, stacked: dict[str, Any]
) -> None:
    """Nothing declares a stack; the targets say what stands on what."""
    first, second, third = stacked["numbers"]

    for number in (first, second, third):
        stack = await client.get(f"{MERGE_REQUESTS}/{number}/stack")
        assert stack.status_code == httpx.codes.OK, stack.text
        assert [item["number"] for item in stack.json()] == [first, second, third]
        assert [item["position"] for item in stack.json()] == [1, 2, 3]


async def test_a_request_standing_alone_is_not_a_stack(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> None:
    del account
    project = await create_project(client, slug="alone")
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await branch_from(work, project["id"], base="main", branch="alone", path="a.txt", content="a\n")

    requests = f"{API_PREFIX}/projects/anna.k/alone/merge-requests"
    made = await client.post(
        requests, json={"title": "Alone", "sourceBranch": "alone", "targetBranch": "main"}
    )

    stack = await client.get(f"{requests}/{made.json()['number']}/stack")
    assert stack.json() == []


async def test_merging_the_bottom_moves_the_one_above_onto_the_target(
    client: httpx.AsyncClient, stacked: dict[str, Any]
) -> None:
    """The whole point: nobody repoints branches by hand after a merge."""
    first, second, third = stacked["numbers"]

    merged = await client.post(f"{MERGE_REQUESTS}/{first}/merge")
    assert merged.status_code == httpx.codes.OK, merged.text

    above = await client.get(f"{MERGE_REQUESTS}/{second}")
    assert above.json()["targetBranch"] == "main"
    # The one above that is untouched: it still stands on the second.
    assert (await client.get(f"{MERGE_REQUESTS}/{third}")).json()["targetBranch"] == "second"


async def test_what_is_left_to_review_is_only_the_work_of_that_branch(
    client: httpx.AsyncClient, stacked: dict[str, Any]
) -> None:
    """After the bottom goes in, the one above must not show its files again."""
    first, second, _ = stacked["numbers"]
    await client.post(f"{MERGE_REQUESTS}/{first}/merge")

    changes = await client.get(f"{MERGE_REQUESTS}/{second}/changes")
    assert [item["path"] for item in changes.json()] == ["b.txt"]


async def test_the_stack_shortens_as_it_goes_in(
    client: httpx.AsyncClient, stacked: dict[str, Any]
) -> None:
    first, second, third = stacked["numbers"]
    await client.post(f"{MERGE_REQUESTS}/{first}/merge")

    stack = await client.get(f"{MERGE_REQUESTS}/{second}/stack")
    assert [item["number"] for item in stack.json()] == [second, third]

    await client.post(f"{MERGE_REQUESTS}/{second}/merge")
    assert (await client.get(f"{MERGE_REQUESTS}/{third}")).json()["targetBranch"] == "main"
    # One left alone is no longer a stack.
    assert (await client.get(f"{MERGE_REQUESTS}/{third}/stack")).json() == []
