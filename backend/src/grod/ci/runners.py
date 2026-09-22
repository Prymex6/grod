"""Registering runners and letting one prove who it is."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts import passwords
from grod.ci.models import Runner
from grod.repositories.models import Project

PREFIX = "grodrun"
SECRET_BYTES = 32
TOKEN_PARTS = 3


@dataclass(frozen=True)
class NewRunner:
    """A freshly registered runner; the secret is shown only once."""

    runner: Runner
    value: str


def _format(runner_id: UUID, secret: str) -> str:
    return f"{PREFIX}_{runner_id.hex}_{secret}"


def _parse(value: str) -> tuple[UUID, str] | None:
    # The secret is url-safe base64, so it may contain underscores itself.
    parts = value.split("_", TOKEN_PARTS - 1)
    if len(parts) != TOKEN_PARTS or parts[0] != PREFIX:
        return None
    try:
        return UUID(hex=parts[1]), parts[2]
    except ValueError:
        return None


async def register(
    session: AsyncSession, *, name: str, project: Project | None, tags: str = ""
) -> NewRunner:
    """Create a runner and return the token it will authenticate with."""
    secret = secrets.token_urlsafe(SECRET_BYTES)
    runner = Runner(
        name=name,
        project_id=project.id if project else None,
        token_hash=passwords.hash_password(secret),
        tags=tags,
    )
    session.add(runner)
    await session.commit()
    return NewRunner(runner=runner, value=_format(runner.id, secret))


async def authenticate(session: AsyncSession, value: str) -> Runner | None:
    """Return the runner this token belongs to, if the secret matches."""
    parsed = _parse(value)
    if parsed is None:
        return None
    runner_id, secret = parsed

    runner = await session.get(Runner, runner_id)
    if runner is None or not runner.active:
        return None
    if not passwords.verify_password(secret, runner.token_hash):
        return None

    runner.last_seen_at = datetime.now(UTC)
    await session.commit()
    return runner


async def list_for_project(session: AsyncSession, *, project: Project) -> list[Runner]:
    """Return the runners registered for a project, newest first."""
    result = await session.execute(
        select(Runner).where(Runner.project_id == project.id).order_by(Runner.created_at.desc())
    )
    return list(result.scalars())


async def remove(session: AsyncSession, *, runner: Runner) -> None:
    """Take a runner off a project."""
    await session.delete(runner)
    await session.commit()
