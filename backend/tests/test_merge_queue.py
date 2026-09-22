"""The line merge requests stand in, and what it protects against."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.ci.models import Pipeline, RunState
from grod.collaboration import merge_queue
from grod.main import API_PREFIX
from grod.repositories import git
from tests.test_merge_requests import open_request, push_branch
from tests.test_repositories import SLUG, create_project, run_git, seed_repository

PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
MERGE_REQUESTS = f"{PROJECT}/merge-requests"
QUEUE = f"{PROJECT}/merge-queue"
RULES = f"{PROJECT}/merge-rules"

CONFIG = """stages: [test]
jobs:
  test:
    stage: test
    script: echo "testing"
"""


async def push_config(work_dir: Path, project_id: str, text: str = CONFIG) -> None:
    """Put a pipeline file on the main branch."""
    config = work_dir / ".grod" / "ci.yml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", "Add the pipeline file", cwd=work_dir)
    await run_git("push", str(git.repository_path(UUID(project_id))), "main", cwd=work_dir)


@pytest.fixture
async def queued(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A project with a pipeline file and one merge request waiting in line."""
    del account
    project = await create_project(client)
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_config(work, project["id"])
    await push_branch(
        work,
        project["id"],
        branch="guide",
        path="docs/guide.md",
        content="# Guide\n",
        message="Add a guide",
    )
    request = await open_request(client, source="guide")

    entered = await client.post(f"{MERGE_REQUESTS}/{request['number']}/queue")
    assert entered.status_code == httpx.codes.CREATED, entered.text
    return {"project": project, "work": work, "request": request}


async def only_pipeline(db: AsyncSession, project_id: str) -> Pipeline:
    """The newest pipeline of a project, which is the one the queue started.

    Every caller is checking what the queue did, so a project without a
    pipeline means the test failed before it got to its point.
    """
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.project_id == UUID(project_id))
        .order_by(Pipeline.created_at.desc())
    )
    pipeline = result.scalars().first()
    assert pipeline is not None, "the queue started no pipeline"
    return pipeline


async def test_standing_in_line_is_shown_on_the_request(
    client: httpx.AsyncClient, queued: dict[str, Any]
) -> None:
    number = queued["request"]["number"]
    place = await client.get(f"{MERGE_REQUESTS}/{number}/queue")

    assert place.json()["state"] == "waiting"
    listed = await client.get(QUEUE)
    assert [item["number"] for item in listed.json()] == [number]
    assert listed.json()[0]["position"] == 1


async def test_the_same_request_cannot_stand_in_line_twice(
    client: httpx.AsyncClient, queued: dict[str, Any]
) -> None:
    again = await client.post(f"{MERGE_REQUESTS}/{queued['request']['number']}/queue")
    assert again.status_code == httpx.codes.CONFLICT


async def test_stepping_out_of_the_line_leaves_the_request_open(
    client: httpx.AsyncClient, queued: dict[str, Any]
) -> None:
    number = queued["request"]["number"]
    left = await client.delete(f"{MERGE_REQUESTS}/{number}/queue")

    assert left.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(QUEUE)).json() == []
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "open"


async def test_the_queue_tests_the_merge_result_not_the_branch(
    client: httpx.AsyncClient, queued: dict[str, Any], db_session: AsyncSession
) -> None:
    """This is the whole point: what runs is the commit that merging would make."""
    project_id = queued["project"]["id"]
    await merge_queue.advance(db_session)

    pipeline = await only_pipeline(db_session, project_id)
    assert pipeline.ref.startswith("grod-queue/")

    # The tested commit has both branches behind it, which the source alone has not.
    merged_in = await git.merge_base(
        UUID(project_id), pipeline.commit, queued["request"]["sourceBranch"]
    )
    assert merged_in == await git.resolve_ref(UUID(project_id), "guide")

    number = queued["request"]["number"]
    assert (await client.get(f"{MERGE_REQUESTS}/{number}/queue")).json()["state"] == "testing"
    # Nothing has moved yet: the target waits for the run.
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "open"


async def test_a_green_run_lets_the_branch_move(
    client: httpx.AsyncClient, queued: dict[str, Any], db_session: AsyncSession
) -> None:
    project_id = queued["project"]["id"]
    before = await git.resolve_ref(UUID(project_id), "main")
    await merge_queue.advance(db_session)

    pipeline = await only_pipeline(db_session, project_id)
    pipeline.state = RunState.SUCCESS
    await db_session.commit()
    await merge_queue.advance(db_session)

    number = queued["request"]["number"]
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "merged"
    assert await git.resolve_ref(UUID(project_id), "main") == pipeline.commit
    assert await git.resolve_ref(UUID(project_id), "main") != before
    assert (await client.get(QUEUE)).json() == []

    # The throwaway branch is gone.
    branches = [ref.name for ref in await git.list_refs(UUID(project_id), kind="heads")]
    assert not [name for name in branches if name.startswith("grod-queue/")]


async def test_a_red_run_keeps_the_branch_where_it_was(
    client: httpx.AsyncClient, queued: dict[str, Any], db_session: AsyncSession
) -> None:
    project_id = queued["project"]["id"]
    before = await git.resolve_ref(UUID(project_id), "main")
    await merge_queue.advance(db_session)

    pipeline = await only_pipeline(db_session, project_id)
    pipeline.state = RunState.FAILED
    await db_session.commit()
    await merge_queue.advance(db_session)

    number = queued["request"]["number"]
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "open"
    assert await git.resolve_ref(UUID(project_id), "main") == before
    assert (await client.get(QUEUE)).json() == []


async def test_a_target_that_moved_sends_the_entry_back_in_line(
    client: httpx.AsyncClient, queued: dict[str, Any], db_session: AsyncSession
) -> None:
    """What was tested is no longer what would be merged, so it is built again."""
    project_id = queued["project"]["id"]
    await merge_queue.advance(db_session)
    pipeline = await only_pipeline(db_session, project_id)

    # Somebody pushes to main while the run is going.
    written = await client.put(
        f"{PROJECT}/files/other.txt",
        json={
            "content": "cos innego\n",
            "message": "A change next to it",
            "branch": "main",
            "parentCommit": await git.resolve_ref(UUID(project_id), "main"),
        },
    )
    assert written.status_code == httpx.codes.OK, written.text

    pipeline.state = RunState.SUCCESS
    await db_session.commit()
    await merge_queue.advance(db_session)

    number = queued["request"]["number"]
    place = await client.get(f"{MERGE_REQUESTS}/{number}/queue")
    assert place.json()["state"] == "waiting"
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "open"


async def test_a_required_check_that_did_not_run_stops_the_merge(
    client: httpx.AsyncClient, queued: dict[str, Any], db_session: AsyncSession
) -> None:
    written = await client.put(RULES, json={"requiredApprovals": 0, "requiredChecks": ["security"]})
    assert written.json()["requiredChecks"] == ["security"]

    project_id = queued["project"]["id"]
    before = await git.resolve_ref(UUID(project_id), "main")
    await merge_queue.advance(db_session)

    pipeline = await only_pipeline(db_session, project_id)
    pipeline.state = RunState.SUCCESS
    await db_session.commit()
    await merge_queue.advance(db_session)

    # The run was green, but the job nobody wrote is still missing.
    assert await git.resolve_ref(UUID(project_id), "main") == before
    number = queued["request"]["number"]
    assert (await client.get(f"{MERGE_REQUESTS}/{number}")).json()["state"] == "open"


async def test_a_project_without_a_pipeline_file_merges_straight_away(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path, db_session: AsyncSession
) -> None:
    """There is nothing to wait for, so the queue does not pretend there is."""
    del account
    project = await create_project(client, slug="no-pipeline")
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_branch(
        work,
        project["id"],
        branch="fix",
        path="a.txt",
        content="a\n",
        message="A fix",
    )
    requests = f"{API_PREFIX}/projects/anna.k/no-pipeline/merge-requests"
    made = await client.post(
        requests,
        json={"title": "A fix", "sourceBranch": "fix", "targetBranch": "main"},
    )
    await client.post(f"{requests}/{made.json()['number']}/queue")

    await merge_queue.advance(db_session)

    assert (await client.get(f"{requests}/{made.json()['number']}")).json()["state"] == "merged"
