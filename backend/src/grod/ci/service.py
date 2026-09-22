"""Starting pipelines, handing jobs to runners and keeping the states in step."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.ci import config as pipeline_config
from grod.ci import findings
from grod.ci.models import FINISHED_STATES, Job, Pipeline, Runner, RunState
from grod.repositories import git
from grod.repositories.models import Project

FIRST_NUMBER = 1
NUMBER_ATTEMPTS = 5
MAX_LOG_LENGTH = 1_000_000


class NoConfigError(Exception):
    """The project does not describe a pipeline at this commit."""


@dataclass(frozen=True)
class PipelineWithJobs:
    """A pipeline and everything it runs."""

    pipeline: Pipeline
    jobs: list[Job]


async def _next_number(session: AsyncSession, project: Project) -> int:
    highest = await session.execute(
        select(func.max(Pipeline.number)).where(Pipeline.project_id == project.id)
    )
    return (highest.scalar() or 0) + FIRST_NUMBER


async def read_config(project: Project, commit: str) -> pipeline_config.PipelineConfig:
    """Read the pipeline file from the repository at one commit."""
    try:
        blob = await git.read_blob(project.id, ref=commit, path=pipeline_config.CONFIG_PATH)
    except (git.RefNotFoundError, git.PathNotFoundError) as error:
        raise NoConfigError(pipeline_config.CONFIG_PATH) from error
    try:
        text = blob.decode()
    except UnicodeDecodeError as error:
        raise NoConfigError(pipeline_config.CONFIG_PATH) from error
    return pipeline_config.parse(text)


async def start(
    session: AsyncSession,
    *,
    project: Project,
    ref: str,
    commit: str,
    triggered_by: User | None = None,
) -> PipelineWithJobs:
    """Create a pipeline with one job per entry of the file, ready to be taken."""
    config = await read_config(project, commit)

    subject = ""
    history = await git.list_commits(project.id, ref=commit, limit=1)
    if history:
        subject = history[0].subject

    pipeline = None
    for _ in range(NUMBER_ATTEMPTS):
        pipeline = Pipeline(
            project_id=project.id,
            number=await _next_number(session, project),
            ref=ref,
            commit=commit,
            commit_subject=subject,
            triggered_by_id=triggered_by.id if triggered_by else None,
        )
        session.add(pipeline)
        try:
            await session.flush()
        except IntegrityError:
            # Two pushes at once can pick the same number; try the next one.
            await session.rollback()
            pipeline = None
            continue
        break
    if pipeline is None:
        raise NoConfigError(pipeline_config.CONFIG_PATH)

    jobs = [
        Job(
            pipeline_id=pipeline.id,
            name=name,
            stage=job.stage,
            stage_order=config.stages.index(job.stage),
            image=job.image,
            script="\n".join(job.script),
            variables=json.dumps({**config.variables, **job.variables}),
        )
        for name, job in config.ordered_jobs()
    ]
    session.add_all(jobs)
    await session.commit()
    return PipelineWithJobs(pipeline=pipeline, jobs=jobs)


async def find(session: AsyncSession, *, project: Project, number: int) -> PipelineWithJobs | None:
    """Return one pipeline of a project with its jobs."""
    result = await session.execute(
        select(Pipeline).where(Pipeline.project_id == project.id, Pipeline.number == number)
    )
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        return None
    return PipelineWithJobs(pipeline=pipeline, jobs=await list_jobs(session, pipeline=pipeline))


async def newest_for_ref(session: AsyncSession, *, project: Project, ref: str) -> Pipeline | None:
    """The last run of one branch, which is the one worth looking at."""
    result = await session.execute(
        select(Pipeline)
        .where(Pipeline.project_id == project.id, Pipeline.ref == ref)
        .order_by(Pipeline.created_at.desc())
    )
    return result.scalars().first()


async def list_jobs(session: AsyncSession, *, pipeline: Pipeline) -> list[Job]:
    """Return the jobs of a pipeline in the order they run."""
    result = await session.execute(
        select(Job).where(Job.pipeline_id == pipeline.id).order_by(Job.stage_order, Job.name)
    )
    return list(result.scalars())


async def list_pipelines(session: AsyncSession, *, project: Project, limit: int) -> list[Pipeline]:
    """Return the pipelines of a project, newest first."""
    result = await session.execute(
        select(Pipeline)
        .where(Pipeline.project_id == project.id)
        .order_by(Pipeline.number.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def take_next_job(session: AsyncSession, *, runner: Runner) -> Job | None:
    """Hand the runner the next job it may take, and mark it as running.

    A job only starts once every earlier stage of its pipeline has finished
    well, so the stages of a pipeline run one after another.
    """
    query = (
        select(Job, Pipeline)
        .join(Pipeline, Pipeline.id == Job.pipeline_id)
        .where(Job.state == RunState.PENDING, Pipeline.state != RunState.CANCELED)
        .order_by(Pipeline.number, Job.stage_order, Job.name)
        # Two runners may ask at the same moment, so the row is locked.
        .with_for_update(skip_locked=True, of=Job)
    )
    if runner.project_id is not None:
        query = query.where(Pipeline.project_id == runner.project_id)

    result = await session.execute(query)
    for row in result.all():
        job: Job = row[0]
        pipeline: Pipeline = row[1]
        if await _earlier_stages_pending(session, pipeline=pipeline, stage_order=job.stage_order):
            continue
        now = datetime.now(UTC)
        job.state = RunState.RUNNING
        job.runner_id = runner.id
        job.started_at = now
        if pipeline.state == RunState.PENDING:
            pipeline.state = RunState.RUNNING
            pipeline.started_at = now
        runner.last_seen_at = now
        await session.commit()
        return job

    runner.last_seen_at = datetime.now(UTC)
    await session.commit()
    return None


async def _earlier_stages_pending(
    session: AsyncSession, *, pipeline: Pipeline, stage_order: int
) -> bool:
    """Whether anything before this stage is still running or has failed."""
    result = await session.execute(
        select(Job.state).where(
            Job.pipeline_id == pipeline.id,
            Job.stage_order < stage_order,
        )
    )
    states = list(result.scalars())
    return any(state != RunState.SUCCESS for state in states)


async def append_log(session: AsyncSession, *, job: Job, text: str) -> Job:
    """Add what the runner printed to the log of a job."""
    job.log = (job.log + text)[-MAX_LOG_LENGTH:]
    await session.commit()
    return job


async def finish_job(session: AsyncSession, *, job: Job, state: RunState) -> Job:
    """Record how a job ended and work out what that means for its pipeline."""
    job.state = state
    job.finished_at = datetime.now(UTC)
    await session.commit()
    # Whatever the tools complained about is read out of the log now, while
    # the job is settled; a later run of the same job replaces it.
    await findings.keep(session, job=job)
    await _settle_pipeline(session, pipeline_id=job.pipeline_id)
    return job


async def _settle_pipeline(session: AsyncSession, *, pipeline_id: UUID) -> None:
    """Set the state of a pipeline from the states of its jobs."""
    pipeline = await session.get(Pipeline, pipeline_id)
    if pipeline is None:
        return

    result = await session.execute(select(Job.state).where(Job.pipeline_id == pipeline_id))
    states = list(result.scalars())

    if any(state == RunState.FAILED for state in states):
        # A failed job stops the ones that have not started yet.
        await session.execute(
            select(Job).where(Job.pipeline_id == pipeline_id, Job.state == RunState.PENDING)
        )
        for job in await list_jobs(session, pipeline=pipeline):
            if job.state == RunState.PENDING:
                job.state = RunState.CANCELED
                job.finished_at = datetime.now(UTC)
        pipeline.state = RunState.FAILED
    elif all(state == RunState.SUCCESS for state in states):
        pipeline.state = RunState.SUCCESS
    elif all(state in FINISHED_STATES for state in states):
        pipeline.state = RunState.CANCELED
    else:
        await session.commit()
        return

    pipeline.finished_at = datetime.now(UTC)
    await session.commit()


async def cancel(session: AsyncSession, *, pipeline: Pipeline) -> Pipeline:
    """Stop a pipeline: everything that has not finished becomes canceled."""
    now = datetime.now(UTC)
    for job in await list_jobs(session, pipeline=pipeline):
        if job.state not in FINISHED_STATES:
            job.state = RunState.CANCELED
            job.finished_at = now
    pipeline.state = RunState.CANCELED
    pipeline.finished_at = now
    await session.commit()
    return pipeline
