"""Keeping functions and running them when somebody calls.

A call starts a container that lives only as long as the call does: the source
travels in an environment variable, the event arrives on standard input and
whatever the function prints comes back as the answer. There is no warm
process yet, so the first fraction of a second is the container starting.
"""

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.apps import containers
from grod.functions.models import NAME_PATTERN, Function, Runtime

NAME_RULE = re.compile(NAME_PATTERN)
MAX_ANSWER_LENGTH = 100_000
MAX_ERROR_LENGTH = 4000
MILLISECONDS = 1000

# The image each runtime runs in, and how it is told to read the source.
RUNTIME_IMAGE = {
    Runtime.PYTHON: "python:3.13-alpine",
    Runtime.NODE: "node:22-alpine",
}
RUNTIME_FILE = {Runtime.PYTHON: "handler.py", Runtime.NODE: "handler.js"}
RUNTIME_COMMAND = {Runtime.PYTHON: "python", Runtime.NODE: "node"}

# The source arrives base64-encoded so no quoting of the code is ever needed.
BOOTSTRAP = 'echo "$GROD_SOURCE" | base64 -d > /tmp/{file} && exec {command} /tmp/{file}'

EXAMPLE_SOURCE = {
    Runtime.PYTHON: (
        "import json, sys\n\n"
        "event = json.load(sys.stdin) if not sys.stdin.isatty() else {}\n"
        'print(json.dumps({"hello": event.get("name", "world")}))\n'
    ),
    Runtime.NODE: (
        "const chunks = [];\n"
        "process.stdin.on('data', (chunk) => chunks.push(chunk));\n"
        "process.stdin.on('end', () => {\n"
        "  const event = chunks.length ? JSON.parse(chunks.join('')) : {};\n"
        "  console.log(JSON.stringify({ hello: event.name ?? 'world' }));\n"
        "});\n"
    ),
}


class InvalidNameError(Exception):
    """A function is named like a host name."""


class NameTakenError(Exception):
    """The account already has a function with that name."""


class EngineUnavailableError(Exception):
    """No container engine answers on this machine."""


@dataclass(frozen=True)
class CallResult:
    """What one call of a function produced."""

    ok: bool
    answer: Any
    output: str
    error: str
    duration_ms: int
    timed_out: bool


async def find(session: AsyncSession, *, owner: User, name: str) -> Function | None:
    """Return one function of an account by name."""
    result = await session.execute(
        select(Function).where(Function.owner_id == owner.id, Function.name == name.lower())
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    runtime: Runtime,
    source: str,
    timeout_seconds: int,
    memory_mb: int,
) -> Function:
    """Keep a new function. Nothing runs until somebody calls it."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    function = Function(
        owner_id=owner.id,
        name=address,
        runtime=runtime,
        source=source or EXAMPLE_SOURCE[runtime],
        timeout_seconds=timeout_seconds,
        memory_mb=memory_mb,
    )
    session.add(function)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return function


async def update(
    session: AsyncSession,
    *,
    function: Function,
    source: str | None = None,
    timeout_seconds: int | None = None,
    memory_mb: int | None = None,
) -> Function:
    """Change the code of a function, or the room it runs in."""
    if source is not None:
        function.source = source
    if timeout_seconds is not None:
        function.timeout_seconds = timeout_seconds
    if memory_mb is not None:
        function.memory_mb = memory_mb
    await session.commit()
    return function


async def delete(session: AsyncSession, *, function: Function) -> None:
    """Forget a function."""
    await session.delete(function)
    await session.commit()


async def call(
    session: AsyncSession,
    *,
    function: Function,
    event: Any,  # noqa: ANN401  (whatever JSON the caller sent)
) -> CallResult:
    """Run the function once with this event and record how it went."""
    if not await containers.available():
        raise EngineUnavailableError

    runtime = Runtime(function.runtime)
    source = base64.b64encode(function.source.encode()).decode()
    started = time.monotonic()

    outcome = await containers.run_once(
        image=RUNTIME_IMAGE[runtime],
        command=[
            "sh",
            "-c",
            BOOTSTRAP.format(file=RUNTIME_FILE[runtime], command=RUNTIME_COMMAND[runtime]),
        ],
        environment={"GROD_SOURCE": source},
        stdin=json.dumps(event).encode(),
        memory_mb=function.memory_mb,
        cpus=1.0,
        timeout=float(function.timeout_seconds),
    )
    duration = int((time.monotonic() - started) * MILLISECONDS)

    result = _read_outcome(outcome, duration)
    await _record(session, function=function, result=result)
    return result


def _read_outcome(outcome: containers.RunOutcome, duration: int) -> CallResult:
    """Turn what the container did into the answer of the call."""
    if outcome.timed_out:
        return CallResult(
            ok=False,
            answer=None,
            output="",
            error="The function ran out of time",
            duration_ms=duration,
            timed_out=True,
        )

    output = outcome.stdout[:MAX_ANSWER_LENGTH]
    if outcome.exit_code != 0:
        return CallResult(
            ok=False,
            answer=None,
            output=output,
            error=outcome.stderr[:MAX_ERROR_LENGTH],
            duration_ms=duration,
            timed_out=False,
        )

    # What the function printed is the answer; JSON when it looks like JSON.
    answer: Any = output
    try:
        answer = json.loads(output)
    except json.JSONDecodeError:
        answer = output.strip()

    return CallResult(
        ok=True, answer=answer, output=output, error="", duration_ms=duration, timed_out=False
    )


async def _record(session: AsyncSession, *, function: Function, result: CallResult) -> None:
    """Keep the counters the console shows."""
    function.calls += 1
    if not result.ok:
        function.failures += 1
    function.last_called_at = datetime.now(UTC)
    function.last_duration_ms = result.duration_ms
    function.last_error = result.error
    await session.commit()
