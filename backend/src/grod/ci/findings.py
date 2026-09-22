"""Pulling what a tool complained about out of the log it printed.

Almost every linter and compiler says the same thing in the same shape —
`main.py:12:5: something is wrong` — so nothing has to be taught to talk to
us. The job runs whatever the project already runs, and what it prints
lands next to the lines it is about.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.ci.models import Job, JobFinding

# path:line[:column]: message — the shape gcc started and everybody copied.
LINE_RULE = re.compile(
    r"^(?P<path>[^\s:][^:]*?):(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<message>\S.*)$"
)
# Anything longer than this is not a remark about one line.
MAX_MESSAGE_LENGTH = 500
MAX_PATH_LENGTH = 1000
# One badly behaved job must not fill the table.
MAX_FINDINGS = 200
# Words that start a line of a summary rather than a remark about a place.
SUMMARY_STARTS = ("http://", "https://", "warning:", "error:", "note:")


@dataclass(frozen=True)
class Finding:
    """One remark about one line, before it is written down."""

    path: str
    line: int
    column: int | None
    message: str


def _clean_path(path: str) -> str | None:
    """The path as the repository knows it, or None when it is not one.

    A tool may print an absolute path from inside its container, which says
    nothing about where the file lives in the repository; a line wrapped in
    quotes is something a script echoed, not something a tool reported.
    """
    cleaned = path.strip().replace("\\", "/").removeprefix("./")
    if not cleaned or cleaned.startswith(("/", '"', "'")) or len(cleaned) > MAX_PATH_LENGTH:
        return None
    if cleaned.lower().startswith(SUMMARY_STARTS):
        return None
    return cleaned


def read_log(log: str) -> list[Finding]:
    """Every remark a log holds, in the order the tool printed them."""
    found: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()

    for raw in log.splitlines():
        line = raw.strip()
        # The runner prefixes the commands it ran; those are not remarks.
        if line.startswith("$ "):
            continue

        match = LINE_RULE.match(line)
        if match is None:
            continue

        path = _clean_path(match.group("path"))
        if path is None:
            continue

        message = match.group("message").strip()[:MAX_MESSAGE_LENGTH]
        number = int(match.group("line"))
        address = (path, number, message)
        if address in seen:
            continue
        seen.add(address)

        column = match.group("column")
        found.append(
            Finding(
                path=path,
                line=number,
                column=int(column) if column else None,
                message=message,
            )
        )
        if len(found) >= MAX_FINDINGS:
            break
    return found


async def keep(session: AsyncSession, *, job: Job) -> int:
    """Write down what one job complained about. Returns how many remarks."""
    await forget(session, job=job)

    found = read_log(job.log)
    session.add_all(
        JobFinding(
            job_id=job.id,
            tool=job.name,
            path=finding.path,
            line=finding.line,
            column=finding.column,
            message=finding.message,
        )
        for finding in found
    )
    await session.commit()
    return len(found)


async def forget(session: AsyncSession, *, job: Job) -> None:
    """Remove what an earlier run of the same job left behind."""
    result = await session.execute(select(JobFinding).where(JobFinding.job_id == job.id))
    for finding in result.scalars():
        await session.delete(finding)


async def list_for_jobs(session: AsyncSession, *, job_ids: list[UUID]) -> list[JobFinding]:
    """Everything the given jobs complained about, by file and line."""
    if not job_ids:
        return []
    result = await session.execute(
        select(JobFinding)
        .where(JobFinding.job_id.in_(job_ids))
        .order_by(JobFinding.path, JobFinding.line)
    )
    return list(result.scalars())
