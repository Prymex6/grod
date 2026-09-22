"""Reading the pipeline file, running its jobs and the runner API."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grod.ci import config as pipeline_config
from grod.ci import triggers
from grod.main import API_PREFIX
from grod.repositories import git, pushes
from grod.repositories import service as projects
from tests.test_repositories import (
    OWNER_LOGIN,
    SLUG,
    create_project,
    run_git,
    seed_repository,
)

BASE = f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}"
PIPELINES = f"{BASE}/pipelines"
RUNNERS = f"{BASE}/runners"
RUNNER_API = f"{API_PREFIX}/runner"

CONFIG = """stages:
  - build
  - test
variables:
  COLOUR: red
jobs:
  build:
    stage: build
    script:
      - echo "building"
  test:
    stage: test
    image: python:3.14
    script: echo "testing"
"""


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client)


async def push_config(work_dir: Path, project_id: str, *, text: str = CONFIG) -> None:
    """Put the pipeline file in the repository of a project."""
    bare = git.repository_path(UUID(project_id))
    config = work_dir / ".grod" / "ci.yml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", "Add the pipeline file", cwd=work_dir)
    await run_git("push", str(bare), "main", cwd=work_dir)


@pytest.fixture
async def ready(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A project whose main branch describes a pipeline, with one run of it."""
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_config(work, project["id"])
    started = await client.post(PIPELINES, json={"ref": "main"})
    assert started.status_code == httpx.codes.CREATED, started.text
    return {"project": project, "work": work, "pipeline": started.json()}


async def take_runner_token(client: httpx.AsyncClient) -> str:
    response = await client.post(RUNNERS, json={"name": "my-runner", "tags": "shell"})
    assert response.status_code == httpx.codes.CREATED, response.text
    token: str = response.json()["token"]
    return token


def test_the_file_may_use_one_line_scripts() -> None:
    config = pipeline_config.parse(CONFIG)

    assert config.stages == ["build", "test"]
    assert config.jobs["test"].script == ['echo "testing"']
    assert [name for name, _ in config.ordered_jobs()] == ["build", "test"]


def test_a_stage_that_was_never_declared_is_refused() -> None:
    with pytest.raises(pipeline_config.ConfigError):
        pipeline_config.parse("stages: [build]\njobs:\n  x:\n    stage: unknown\n    script: ls\n")


def test_a_file_that_is_not_yaml_is_refused() -> None:
    with pytest.raises(pipeline_config.ConfigError):
        pipeline_config.parse("jobs: [[[")


async def test_a_run_of_the_file_becomes_a_pipeline(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    listed = await client.get(PIPELINES)

    assert listed.status_code == httpx.codes.OK, listed.text
    pipelines = listed.json()
    assert len(pipelines) == 1
    assert pipelines[0]["ref"] == "main"
    assert pipelines[0]["state"] == "pending"
    assert [job["name"] for job in pipelines[0]["jobs"]] == ["build", "test"]


async def test_a_push_starts_a_pipeline_for_every_branch_it_moved(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path, db_session: AsyncSession
) -> None:
    """The platform serves the push itself, so it compares the tips around it."""
    work = tmp_path / "work"
    await seed_repository(project["id"], work)

    found = await projects.find(db_session, owner_login=OWNER_LOGIN, slug=SLUG)
    assert found is not None
    before = await pushes.branch_tips(found.project)

    await push_config(work, project["id"])
    after = await pushes.branch_tips(found.project)
    started = await triggers.after_push(
        db_session, project=found.project, before=before, after=after, pusher=None
    )

    assert started == [1], "the branch with the file got a pipeline"
    listed = await client.get(PIPELINES)
    assert [item["ref"] for item in listed.json()] == ["main"]


async def test_a_project_without_the_file_starts_nothing(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")

    listed = await client.get(PIPELINES)
    assert listed.json() == []

    by_hand = await client.post(PIPELINES, json={"ref": "main"})
    assert by_hand.status_code == httpx.codes.NOT_FOUND


async def test_a_runner_takes_the_stages_one_after_another(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    token = await take_runner_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post(f"{RUNNER_API}/jobs/request", headers=headers)
    assert first.status_code == httpx.codes.OK, first.text
    job = first.json()
    assert job["name"] == "build"
    assert job["variables"] == {"COLOUR": "red"}
    assert job["script"] == ['echo "building"']

    # The second stage waits for the first one to finish well.
    waiting = await client.post(f"{RUNNER_API}/jobs/request", headers=headers)
    assert waiting.json() is None

    running = await client.get(f"{PIPELINES}/1")
    assert running.json()["state"] == "running"

    await client.patch(
        f"{RUNNER_API}/jobs/{job['id']}",
        json={"log": "buduje\n", "state": "success"},
        headers=headers,
    )

    second = await client.post(f"{RUNNER_API}/jobs/request", headers=headers)
    assert second.json()["name"] == "test"
    await client.patch(
        f"{RUNNER_API}/jobs/{second.json()['id']}", json={"state": "success"}, headers=headers
    )

    finished = await client.get(f"{PIPELINES}/1")
    assert finished.json()["state"] == "success"

    log = await client.get(f"{BASE}/jobs/{job['id']}/log")
    assert log.json()["log"] == "buduje\n"


async def test_a_failed_job_stops_the_rest(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    token = await take_runner_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    job = (await client.post(f"{RUNNER_API}/jobs/request", headers=headers)).json()
    await client.patch(f"{RUNNER_API}/jobs/{job['id']}", json={"state": "failed"}, headers=headers)

    pipeline = (await client.get(f"{PIPELINES}/1")).json()
    assert pipeline["state"] == "failed"
    states = {item["name"]: item["state"] for item in pipeline["jobs"]}
    assert states == {"build": "failed", "test": "canceled"}

    nothing_left = await client.post(f"{RUNNER_API}/jobs/request", headers=headers)
    assert nothing_left.json() is None


async def test_a_runner_needs_a_token(client: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    del ready
    without = await client.post(f"{RUNNER_API}/jobs/request")
    assert without.status_code == httpx.codes.UNAUTHORIZED

    wrong = await client.post(
        f"{RUNNER_API}/jobs/request", headers={"Authorization": "Bearer grodrun_nonsense"}
    )
    assert wrong.status_code == httpx.codes.UNAUTHORIZED


async def test_a_runner_fetches_the_tree_of_its_job(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    token = await take_runner_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    job = (await client.post(f"{RUNNER_API}/jobs/request", headers=headers)).json()

    archive = await client.get(f"{RUNNER_API}/jobs/{job['id']}/archive", headers=headers)

    assert archive.status_code == httpx.codes.OK, archive.text
    assert archive.headers["content-type"] == "application/x-tar"
    # A tar archive names its entries in clear text.
    assert b"README.md" in archive.content
    assert b".grod/ci.yml" in archive.content


async def test_a_pipeline_may_be_canceled(client: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    del ready
    canceled = await client.post(f"{PIPELINES}/1/cancel")

    assert canceled.status_code == httpx.codes.OK, canceled.text
    assert canceled.json()["state"] == "canceled"
    assert all(job["state"] == "canceled" for job in canceled.json()["jobs"])
