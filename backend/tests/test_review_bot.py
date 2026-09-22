"""What the tools said about single lines, read out of the job logs."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.ci import findings
from grod.ci import service as pipelines
from grod.ci.models import Job, RunState
from grod.main import API_PREFIX
from grod.repositories import git
from grod.repositories.models import Project
from tests.test_merge_requests import open_request, push_branch
from tests.test_repositories import SLUG, create_project, run_git, seed_repository

PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
MERGE_REQUESTS = f"{PROJECT}/merge-requests"

RUFF_LOG = """$ ruff check .
src/main.py:12:5: E501 Line too long (120 > 100)
src/main.py:40:1: F401 `os` imported but unused
docs/README.md:3:1: MD013 Line length
Found 3 errors.
"""

CONFIG = """stages: [lintery]
jobs:
  lintery:
    stage: lintery
    script: echo "checking"
"""


def test_the_usual_shape_of_a_complaint_is_understood() -> None:
    found = findings.read_log(RUFF_LOG)

    assert [(item.path, item.line, item.column) for item in found] == [
        ("src/main.py", 12, 5),
        ("src/main.py", 40, 1),
        ("docs/README.md", 3, 1),
    ]
    assert found[0].message.startswith("E501")


def test_a_complaint_without_a_column_still_counts() -> None:
    found = findings.read_log("file.py:7: a warning about something\n")

    assert len(found) == 1
    assert found[0].line == 7
    assert found[0].column is None


def test_what_is_not_about_a_line_is_left_alone() -> None:
    noise = """$ echo start
Found 3 errors.
https://example.com/guide:12: an address, not a file
/usr/lib/python3/os.py:4:1: not our file
ordinary text with no colon
"""

    assert findings.read_log(noise) == []


def test_a_line_in_quotes_is_something_a_script_echoed() -> None:
    quoted = '"src/main.py:1:1: E501 the line is too long"\n'

    assert findings.read_log(quoted) == []


def test_the_same_complaint_twice_is_kept_once() -> None:
    twice = "a.py:1:1: cos\na.py:1:1: cos\n"

    assert len(findings.read_log(twice)) == 1


@pytest.fixture
async def reviewed(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A merge request whose source branch has a finished pipeline."""
    del account
    project = await create_project(client)
    work = tmp_path / "work"
    await seed_repository(project["id"], work)

    config = work / ".grod" / "ci.yml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(CONFIG, encoding="utf-8")
    await run_git("add", ".", cwd=work)
    await run_git("commit", "-m", "Add a pipeline", cwd=work)
    await run_git("push", str(git.repository_path(UUID(project["id"]))), "main", cwd=work)

    await push_branch(
        work,
        project["id"],
        branch="fix",
        path="src/main.py",
        content="print('x')\n",
        message="A fix",
    )
    request = await open_request(client, source="fix")
    started = await client.post(f"{PROJECT}/pipelines", json={"ref": "fix"})
    assert started.status_code == httpx.codes.CREATED, started.text
    return {"project": project, "request": request, "pipeline": started.json()}


async def test_a_finished_job_leaves_its_remarks_on_the_request(
    client: httpx.AsyncClient, reviewed: dict[str, Any], db_session: AsyncSession
) -> None:
    """Nobody has to teach the tool anything: its own output is enough."""
    project = await db_session.get(Project, UUID(reviewed["project"]["id"]))
    assert project is not None
    pipeline = await pipelines.newest_for_ref(db_session, project=project, ref="fix")
    assert pipeline is not None

    result = await db_session.execute(select(Job).where(Job.pipeline_id == pipeline.id))
    job = result.scalars().first()
    assert job is not None
    job.log = RUFF_LOG
    await db_session.commit()
    await pipelines.finish_job(db_session, job=job, state=RunState.FAILED)

    number = reviewed["request"]["number"]
    listed = await client.get(f"{MERGE_REQUESTS}/{number}/findings")
    assert listed.status_code == httpx.codes.OK, listed.text
    assert [(item["path"], item["line"]) for item in listed.json()] == [
        ("docs/README.md", 3),
        ("src/main.py", 12),
        ("src/main.py", 40),
    ]
    assert listed.json()[0]["tool"] == "lintery"


async def test_running_the_job_again_replaces_what_it_said(
    client: httpx.AsyncClient, reviewed: dict[str, Any], db_session: AsyncSession
) -> None:
    project = await db_session.get(Project, UUID(reviewed["project"]["id"]))
    assert project is not None
    pipeline = await pipelines.newest_for_ref(db_session, project=project, ref="fix")
    assert pipeline is not None
    result = await db_session.execute(select(Job).where(Job.pipeline_id == pipeline.id))
    job = result.scalars().first()
    assert job is not None

    job.log = RUFF_LOG
    await db_session.commit()
    await pipelines.finish_job(db_session, job=job, state=RunState.FAILED)

    # The next run says only one thing, so only that one is left.
    job.log = "src/main.py:12:5: E501 Line too long (120 > 100)\n"
    await db_session.commit()
    await pipelines.finish_job(db_session, job=job, state=RunState.SUCCESS)

    number = reviewed["request"]["number"]
    listed = await client.get(f"{MERGE_REQUESTS}/{number}/findings")
    assert len(listed.json()) == 1


async def test_a_request_without_a_run_says_nothing(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> None:
    del account
    project = await create_project(client, slug="no-run")
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_branch(
        work, project["id"], branch="p", path="a.txt", content="a\n", message="A change"
    )
    requests = f"{API_PREFIX}/projects/anna.k/no-run/merge-requests"
    made = await client.post(
        requests, json={"title": "A change", "sourceBranch": "p", "targetBranch": "main"}
    )

    listed = await client.get(f"{requests}/{made.json()['number']}/findings")
    assert listed.json() == []
