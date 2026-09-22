"""Endpoints for pipelines of a project and for the runners it uses."""

import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import service as accounts
from grod.accounts.dependencies import CurrentUser, OptionalUser
from grod.accounts.schemas import ApiModel
from grod.artifacts import service as artifacts
from grod.ci import config as pipeline_config
from grod.ci import runners, service
from grod.ci.models import FINISHED_STATES, Job, Pipeline, Runner, RunState
from grod.collaboration.router import NOT_ALLOWED_DETAIL, readable
from grod.community.models import Group
from grod.db import get_db_session
from grod.repositories import git
from grod.repositories import service as project_service
from grod.repositories.models import NAME_MAX_LENGTH, Project

router = APIRouter(prefix="/projects/{owner}/{slug}", tags=["ci"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

PIPELINE_NOT_FOUND = "No such pipeline"
MAX_PIPELINES = 50


class PipelineStart(ApiModel):
    """Run the pipeline of a branch by hand."""

    ref: str = Field(min_length=1, max_length=200)


class JobView(ApiModel):
    """One job as the console shows it."""

    id: UUID
    name: str
    stage: str
    state: RunState
    image: str | None
    script: list[str]
    started_at: datetime | None
    finished_at: datetime | None


class PipelineView(ApiModel):
    """A pipeline with the jobs it runs."""

    id: UUID
    number: int
    ref: str
    commit: str
    commit_subject: str
    state: RunState
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    jobs: list[JobView]


class JobLogView(ApiModel):
    """What a job has printed so far."""

    id: UUID
    state: RunState
    log: str


class RunnerCreate(ApiModel):
    """Register a runner for this project."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    tags: str = Field(default="", max_length=200)


class RunnerView(ApiModel):
    """A runner as the settings page shows it."""

    id: UUID
    name: str
    tags: str
    active: bool
    created_at: datetime
    last_seen_at: datetime | None


class NewRunnerView(RunnerView):
    """A freshly registered runner, with the token shown only once."""

    token: str


def _job_view(job: Job) -> JobView:
    return JobView(
        id=job.id,
        name=job.name,
        stage=job.stage,
        state=job.state,
        image=job.image,
        script=job.script.split("\n") if job.script else [],
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _pipeline_view(pipeline: Pipeline, jobs: list[Job]) -> PipelineView:
    return PipelineView(
        id=pipeline.id,
        number=pipeline.number,
        ref=pipeline.ref,
        commit=pipeline.commit,
        commit_subject=pipeline.commit_subject,
        state=pipeline.state,
        created_at=pipeline.created_at,
        started_at=pipeline.started_at,
        finished_at=pipeline.finished_at,
        jobs=[_job_view(job) for job in jobs],
    )


def _runner_view(runner: Runner) -> RunnerView:
    return RunnerView(
        id=runner.id,
        name=runner.name,
        tags=runner.tags,
        active=runner.active,
        created_at=runner.created_at,
        last_seen_at=runner.last_seen_at,
    )


@router.get("/pipelines")
async def list_pipelines(
    owner: str,
    slug: str,
    db: DbSession,
    user: OptionalUser,
    limit: Annotated[int, Query(le=MAX_PIPELINES)] = 20,
) -> list[PipelineView]:
    """Return the pipelines of a project, newest first."""
    project, _ = await readable(db, owner, slug, user)
    found = await service.list_pipelines(db, project=project, limit=limit)
    return [
        _pipeline_view(pipeline, await service.list_jobs(db, pipeline=pipeline))
        for pipeline in found
    ]


@router.post("/pipelines", status_code=status.HTTP_201_CREATED)
async def start_pipeline(
    owner: str, slug: str, body: PipelineStart, db: DbSession, user: CurrentUser
) -> PipelineView:
    """Run the pipeline of a branch by hand. It takes the right to push."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    try:
        commit = await git.resolve_ref(project.id, body.ref)
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such branch") from None

    try:
        started = await service.start(
            db, project=project, ref=body.ref, commit=commit, triggered_by=user
        )
    except service.NoConfigError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"The branch has no {pipeline_config.CONFIG_PATH}",
        ) from None
    except pipeline_config.ConfigError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None

    return _pipeline_view(started.pipeline, started.jobs)


@router.get("/pipelines/{number}")
async def read_pipeline(
    owner: str, slug: str, number: int, db: DbSession, user: OptionalUser
) -> PipelineView:
    """Return one pipeline with its jobs."""
    project, _ = await readable(db, owner, slug, user)
    found = await service.find(db, project=project, number=number)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=PIPELINE_NOT_FOUND)
    return _pipeline_view(found.pipeline, found.jobs)


@router.post("/pipelines/{number}/cancel")
async def cancel_pipeline(
    owner: str, slug: str, number: int, db: DbSession, user: CurrentUser
) -> PipelineView:
    """Stop a pipeline that is still running."""
    project, access = await readable(db, owner, slug, user)
    if not access.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    found = await service.find(db, project=project, number=number)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=PIPELINE_NOT_FOUND)

    await service.cancel(db, pipeline=found.pipeline)
    jobs = await service.list_jobs(db, pipeline=found.pipeline)
    return _pipeline_view(found.pipeline, jobs)


@router.get("/jobs/{job_id}/log")
async def read_job_log(
    owner: str, slug: str, job_id: UUID, db: DbSession, user: OptionalUser
) -> JobLogView:
    """Return what a job printed."""
    project, _ = await readable(db, owner, slug, user)
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such job")
    pipeline = await db.get(Pipeline, job.pipeline_id)
    if pipeline is None or pipeline.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such job")
    return JobLogView(id=job.id, state=job.state, log=job.log)


@router.get("/runners")
async def list_runners(owner: str, slug: str, db: DbSession, user: CurrentUser) -> list[RunnerView]:
    """Return the runners registered for a project."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)
    return [_runner_view(runner) for runner in await runners.list_for_project(db, project=project)]


@router.post("/runners", status_code=status.HTTP_201_CREATED)
async def register_runner(
    owner: str, slug: str, body: RunnerCreate, db: DbSession, user: CurrentUser
) -> NewRunnerView:
    """Register a runner and hand back the token it signs in with."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    created = await runners.register(db, name=body.name, project=project, tags=body.tags)
    return NewRunnerView(**_runner_view(created.runner).model_dump(), token=created.value)


@router.delete("/runners/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_runner(
    owner: str, slug: str, runner_id: UUID, db: DbSession, user: CurrentUser
) -> None:
    """Take a runner off a project."""
    project, access = await readable(db, owner, slug, user)
    if not access.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED_DETAIL)

    runner = await db.get(Runner, runner_id)
    if runner is None or runner.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such runner")
    await runners.remove(db, runner=runner)


async def namespace_of(db: AsyncSession, project: Project) -> str:
    """Return the first part of the address of a project."""
    if project.group_id is not None:
        group = await db.get(Group, project.group_id)
        if group is not None:
            return group.slug
    owner = await accounts.find_by_id(db, project.owner_id)
    return owner.login if owner else ""


# The runner talks to the platform through its own prefix, with its own token.
runner_router = APIRouter(prefix="/runner", tags=["ci"])


class JobForRunner(ApiModel):
    """Everything a runner needs to carry a job out."""

    id: UUID
    name: str
    stage: str
    image: str | None
    script: list[str]
    variables: dict[str, str]
    project: str
    ref: str
    commit: str
    # Where the runner fetches the tree of that commit, as a tar archive.
    archive_url: str


class JobUpdate(ApiModel):
    """What a runner reports while a job runs and when it ends."""

    log: str = Field(default="", max_length=service.MAX_LOG_LENGTH)
    state: RunState | None = None


async def _runner_of(db: AsyncSession, token: str | None) -> Runner:
    """Find the runner behind the token, or refuse the call."""
    if token is None or not token.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="A runner token is required")
    runner = await runners.authenticate(db, token.removeprefix("Bearer ").strip())
    if runner is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Unknown runner token")
    return runner


def _job_for_runner(
    job: Job, pipeline: Pipeline, address: str, secrets: dict[str, str]
) -> JobForRunner:
    variables: dict[str, str] = {**json.loads(job.variables or "{}"), **secrets}
    return JobForRunner(
        id=job.id,
        name=job.name,
        stage=job.stage,
        image=job.image,
        script=job.script.split("\n") if job.script else [],
        variables=variables,
        project=address,
        ref=pipeline.ref,
        commit=pipeline.commit,
        archive_url=f"/runner/jobs/{job.id}/archive",
    )


@runner_router.post("/jobs/request")
async def request_job(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> JobForRunner | None:
    """Hand the runner the next job it may take, or nothing at all."""
    runner = await _runner_of(db, authorization)
    job = await service.take_next_job(db, runner=runner)
    if job is None:
        return None

    pipeline = await db.get(Pipeline, job.pipeline_id)
    if pipeline is None:
        return None
    project = await db.get(Project, pipeline.project_id)
    if project is None:
        return None

    # Secrets become variables of the job; the protected ones only on a
    # protected branch, so a pushed branch cannot print them.
    protected = await project_service.branch_is_protected(db, project=project, branch=pipeline.ref)
    secrets = await artifacts.secrets_for_job(db, project=project, protected_branch=protected)

    address = await namespace_of(db, project)
    return _job_for_runner(job, pipeline, f"{address}/{project.slug}", secrets)


@runner_router.patch("/jobs/{job_id}")
async def update_job(
    job_id: UUID,
    body: JobUpdate,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> JobLogView:
    """Take the output of a running job, and its result once it ends."""
    runner = await _runner_of(db, authorization)
    job = await db.get(Job, job_id)
    if job is None or job.runner_id != runner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such job")

    if body.log:
        # A masked secret never reaches the log, even when a script prints it.
        pipeline = await db.get(Pipeline, job.pipeline_id)
        text = body.log
        if pipeline is not None:
            project = await db.get(Project, pipeline.project_id)
            if project is not None:
                kept = await artifacts.list_secrets(db, project=project)
                values = await artifacts.secrets_for_job(db, project=project, protected_branch=True)
                text = artifacts.mask(text, values, {item.name for item in kept if item.masked})
        await service.append_log(db, job=job, text=text)
    if body.state is not None:
        if body.state not in FINISHED_STATES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="A runner only reports how a job ended"
            )
        await service.finish_job(db, job=job, state=body.state)

    return JobLogView(id=job.id, state=job.state, log=job.log)


@runner_router.get("/jobs/{job_id}/archive")
async def read_job_archive(
    job_id: UUID, db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> Response:
    """Return the tree the job is to work on, as a tar archive."""
    runner = await _runner_of(db, authorization)
    job = await db.get(Job, job_id)
    if job is None or job.runner_id != runner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such job")

    pipeline = await db.get(Pipeline, job.pipeline_id)
    if pipeline is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such job")

    try:
        content = await git.archive(pipeline.project_id, pipeline.commit)
    except git.RefNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="The commit is gone") from None
    return Response(content=content, media_type="application/x-tar")
