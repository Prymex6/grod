"""Merge requests: the diff between two branches, the review and the merge."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from grod.main import API_PREFIX
from grod.repositories import git
from tests.test_collaboration import OTHER_LOGIN, sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    OWNER_LOGIN,
    SLUG,
    create_project,
    register_other,
    run_git,
    seed_repository,
)

BASE = f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}"
MERGE_REQUESTS = f"{BASE}/merge-requests"
MEMBERS = f"{BASE}/members"
ACCOUNT_EMAIL = "anna.k@grod.dev"
ACCOUNT_PASSWORD = "correct-horse-battery"
FEATURE_BRANCH = "feature"
NEW_FILE = "docs/guide.md"
NEW_CONTENT = "Guide\n"


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client)


async def push_branch(
    work_dir: Path,
    project_id: str,
    *,
    branch: str,
    path: str,
    content: str,
    message: str,
) -> None:
    """Add one commit on a new branch of the working copy and push it."""
    bare = git.repository_path(UUID(project_id))
    await run_git("checkout", "-b", branch, cwd=work_dir)
    target = work_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", message, cwd=work_dir)
    await run_git("push", str(bare), branch, cwd=work_dir)
    await run_git("checkout", "main", cwd=work_dir)


async def open_request(
    client: httpx.AsyncClient, *, source: str = FEATURE_BRANCH, target: str = "main"
) -> dict[str, Any]:
    response = await client.post(
        MERGE_REQUESTS,
        json={
            "title": "Add a guide",
            "description": "A new chapter of the documentation",
            "sourceBranch": source,
            "targetBranch": target,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


@pytest.fixture
async def ready(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A project with a main branch and a feature branch one commit ahead."""
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_branch(
        work,
        project["id"],
        branch=FEATURE_BRANCH,
        path=NEW_FILE,
        content=NEW_CONTENT,
        message="Add a guide",
    )
    return {"project": project, "work": work}


async def test_a_merge_request_shows_its_diff_and_its_commits(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    opened = await open_request(client)
    number = opened["number"]

    assert opened["state"] == "open"
    assert opened["author"]["login"] == OWNER_LOGIN

    changes = await client.get(f"{MERGE_REQUESTS}/{number}/changes")
    assert changes.status_code == httpx.codes.OK, changes.text
    files = changes.json()
    assert [item["path"] for item in files] == [NEW_FILE]
    assert files[0]["additions"] == 1
    assert "Guide" in files[0]["patch"]

    commits = await client.get(f"{MERGE_REQUESTS}/{number}/commits")
    assert [item["subject"] for item in commits.json()] == ["Add a guide"]


async def test_merging_moves_the_target_branch(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    project_id = ready["project"]["id"]
    before = await git.resolve_ref(UUID(project_id), "main")
    opened = await open_request(client)

    merged = await client.post(f"{MERGE_REQUESTS}/{opened['number']}/merge")
    assert merged.status_code == httpx.codes.OK, merged.text
    body = merged.json()

    assert body["state"] == "merged"
    assert body["mergedAt"] is not None

    after = await git.resolve_ref(UUID(project_id), "main")
    assert after != before, "the target branch keeps the merge commit"
    assert after == body["mergeCommit"]

    tree = await git.list_tree(UUID(project_id), ref="main", path="docs")
    assert [entry.name for entry in tree] == ["guide.md"], "the merged file is on main"

    again = await client.post(f"{MERGE_REQUESTS}/{opened['number']}/merge")
    assert again.status_code == httpx.codes.CONFLICT, "a merged request cannot be merged twice"


async def test_conflicting_branches_are_refused(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    work: Path = ready["work"]
    project_id = ready["project"]["id"]
    bare = git.repository_path(UUID(project_id))

    # Both branches change the same file in a different way.
    await run_git("checkout", FEATURE_BRANCH, cwd=work)
    (work / "README.md").write_text("The version from the branch\n", encoding="utf-8")
    await run_git("commit", "-am", "Change README", cwd=work)
    await run_git("push", str(bare), FEATURE_BRANCH, cwd=work)
    await run_git("checkout", "main", cwd=work)
    (work / "README.md").write_text("The version from main\n", encoding="utf-8")
    await run_git("commit", "-am", "Change README differently", cwd=work)
    await run_git("push", str(bare), "main", cwd=work)

    opened = await open_request(client)
    merged = await client.post(f"{MERGE_REQUESTS}/{opened['number']}/merge")

    assert merged.status_code == httpx.codes.CONFLICT, merged.text
    assert "README.md" in str(merged.json()["detail"]["conflicts"])

    read = await client.get(f"{MERGE_REQUESTS}/{opened['number']}")
    assert read.json()["state"] == "open", "a conflict leaves the request open"


async def test_a_request_needs_two_branches_that_exist(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    same = await client.post(
        MERGE_REQUESTS,
        json={"title": "Nothing", "sourceBranch": "main", "targetBranch": "main"},
    )
    assert same.status_code == httpx.codes.UNPROCESSABLE_ENTITY

    missing = await client.post(
        MERGE_REQUESTS,
        json={"title": "Nothing", "sourceBranch": "no-such-branch", "targetBranch": "main"},
    )
    assert missing.status_code == httpx.codes.NOT_FOUND


async def test_closing_and_reopening_a_request(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    opened = await open_request(client)
    number = opened["number"]

    closed = await client.post(f"{MERGE_REQUESTS}/{number}/close")
    assert closed.json()["state"] == "closed"

    reopened = await client.post(f"{MERGE_REQUESTS}/{number}/reopen")
    assert reopened.json()["state"] == "open"

    only_open = await client.get(MERGE_REQUESTS, params={"state": "open"})
    assert [item["number"] for item in only_open.json()] == [number]


async def test_a_review_comment_may_point_at_a_line(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    number = (await open_request(client))["number"]

    added = await client.post(
        f"{MERGE_REQUESTS}/{number}/comments",
        json={"body": "A typo in the title", "filePath": NEW_FILE, "lineNumber": 1},
    )
    assert added.status_code == httpx.codes.CREATED, added.text
    comment = added.json()
    assert comment["filePath"] == NEW_FILE
    assert comment["lineNumber"] == 1

    listed = await client.get(f"{MERGE_REQUESTS}/{number}/comments")
    assert [item["body"] for item in listed.json()] == ["A typo in the title"]

    removed = await client.delete(f"{MERGE_REQUESTS}/{number}/comments/{comment['id']}")
    assert removed.status_code == httpx.codes.NO_CONTENT

    empty = await client.get(f"{MERGE_REQUESTS}/{number}/comments")
    assert empty.json() == []


async def test_a_guest_may_review_but_not_merge(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    number = (await open_request(client))["number"]

    await register_other(client)
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    added = await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})
    assert added.status_code == httpx.codes.CREATED, added.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    review = await client.post(f"{MERGE_REQUESTS}/{number}/comments", json={"body": "Looks good"})
    assert review.status_code == httpx.codes.CREATED, "a guest takes part in the review"

    merged = await client.post(f"{MERGE_REQUESTS}/{number}/merge")
    assert merged.status_code == httpx.codes.FORBIDDEN, "merging takes the right to push"
