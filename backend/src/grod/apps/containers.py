"""The only place in Grod that runs the `docker` program.

Everything the platform does with containers passes through here, so the
container engine can later be replaced (Podman, a remote daemon, or an own
runtime) without touching the rest of the code. This mirrors the rule that
keeps every `git` call in one module.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from grod.config import get_settings

# Grod puts this label on everything it creates, so it never touches a
# container somebody started by hand on the same machine.
OWNER_LABEL = "grod.owned"
NAME_LABEL = "grod.application"
LOG_TAIL = 200
STOP_TIMEOUT_SECONDS = 10
# A terminal inside the container, with a fallback for images without bash.
SHELL_COMMAND = (
    "if command -v script >/dev/null 2>&1; then "
    'script -qc "${SHELL:-/bin/sh}" /dev/null; '
    "else ${SHELL:-/bin/sh}; fi"
)


class ContainerError(Exception):
    """The engine refused to do what it was asked."""


@dataclass(frozen=True)
class ContainerState:
    """What the engine says about one container."""

    running: bool
    exit_code: int | None
    started_at: str | None
    finished_at: str | None


async def _run(*arguments: str, timeout: float = 120.0) -> bytes:
    """Run docker and return its output, or raise with what it complained about."""
    settings = get_settings()
    try:
        process = await asyncio.create_subprocess_exec(
            settings.docker_binary,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise ContainerError("No container engine on this machine") from error

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as error:
        process.kill()
        raise ContainerError("The engine did not answer in time") from error

    if process.returncode != 0:
        raise ContainerError(stderr.decode(errors="replace").strip())
    return stdout


async def available() -> bool:
    """Whether a container engine answers at all."""
    try:
        await _run("version", "--format", "{{.Server.Version}}", timeout=10.0)
    except ContainerError:
        return False
    return True


async def pull(image: str) -> None:
    """Fetch an image so starting it afterwards is quick."""
    await _run("pull", image, timeout=600.0)


async def run(
    *,
    name: str,
    image: str,
    command: list[str],
    environment: dict[str, str],
    port: int | None,
    host_port: int | None,
    memory_mb: int,
    cpus: float,
) -> str:
    """Start a container in the background and return its identifier."""
    arguments = [
        "run",
        "--detach",
        "--name",
        name,
        "--label",
        f"{OWNER_LABEL}=true",
        "--label",
        f"{NAME_LABEL}={name}",
        "--restart",
        "unless-stopped",
        f"--memory={memory_mb}m",
        f"--cpus={cpus}",
        # An application never reaches the engine that runs it.
        "--security-opt",
        "no-new-privileges",
    ]
    for key, value in environment.items():
        arguments += ["--env", f"{key}={value}"]
    if port is not None and host_port is not None:
        arguments += ["--publish", f"127.0.0.1:{host_port}:{port}"]

    arguments.append(image)
    arguments += command

    output = await _run(*arguments, timeout=300.0)
    return output.decode().strip()


async def run_idle(
    *,
    name: str,
    image: str,
    memory_mb: int,
    cpus: float,
    workdir: str,
) -> str:
    """Start a container that only waits, so somebody can work inside it.

    It gets no network and no ports: a workspace is a place to run code that
    came out of a repository, not a way to reach the machine underneath.
    """
    output = await _run(
        "run",
        "--detach",
        "--name",
        name,
        "--label",
        f"{OWNER_LABEL}=true",
        "--label",
        f"{NAME_LABEL}={name}",
        "--network",
        "none",
        f"--memory={memory_mb}m",
        f"--cpus={cpus}",
        "--security-opt",
        "no-new-privileges",
        "--workdir",
        workdir,
        "--entrypoint",
        "sh",
        image,
        "-c",
        "while true; do sleep 3600; done",
        timeout=300.0,
    )
    return output.decode().strip()


async def copy_into(container_id: str, *, archive: bytes, path: str) -> None:
    """Unpack a tar archive inside a container."""
    await _run_with_input("cp", "-", f"{container_id}:{path}", stdin=archive, timeout=120.0)


async def copy_out(container_id: str, *, path: str) -> bytes:
    """Return what is under a path inside a container, as a tar archive."""
    return await _run("cp", f"{container_id}:{path}", "-", timeout=120.0)


async def _run_with_input(*arguments: str, stdin: bytes, timeout: float) -> bytes:
    """Run docker with something on its standard input."""
    settings = get_settings()
    try:
        process = await asyncio.create_subprocess_exec(
            settings.docker_binary,
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise ContainerError("No container engine on this machine") from error

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout=timeout)
    except TimeoutError as error:
        process.kill()
        raise ContainerError("The engine did not answer in time") from error

    if process.returncode != 0:
        raise ContainerError(stderr.decode(errors="replace").strip())
    return stdout


async def open_shell(container_id: str) -> asyncio.subprocess.Process:
    """Start a shell inside a container and hand back its pipes.

    The shell runs under a terminal the container provides itself (`script`),
    because the side Grod holds is a socket, not a terminal — without it there
    would be no prompt and no line editing.
    """
    settings = get_settings()
    try:
        return await asyncio.create_subprocess_exec(
            settings.docker_binary,
            "exec",
            "--interactive",
            container_id,
            "sh",
            "-c",
            SHELL_COMMAND,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as error:
        raise ContainerError("No container engine on this machine") from error


async def stop(container_id: str) -> None:
    """Stop a container, giving it a moment to finish what it is doing."""
    await _run("stop", "--timeout", str(STOP_TIMEOUT_SECONDS), container_id, timeout=60.0)


async def remove(container_id: str) -> None:
    """Remove a container, stopping it first if it still runs."""
    await _run("rm", "--force", container_id, timeout=60.0)


async def names_starting_with(prefix: str) -> list[str]:
    """The containers Grod started whose name begins that way, running or not.

    Used to find containers nothing points at any more, so one that outlived
    its row does not sit on the machine forever.
    """
    output = await _run(
        "ps",
        "--all",
        "--filter",
        f"label={OWNER_LABEL}=true",
        "--format",
        "{{.Names}}",
        timeout=30.0,
    )
    return [name for name in output.decode(errors="replace").split() if name.startswith(prefix)]


async def logs(container_id: str, *, tail: int = LOG_TAIL) -> str:
    """Return what a container printed, newest lines last."""
    output = await _run("logs", "--tail", str(tail), container_id, timeout=30.0)
    return output.decode(errors="replace")


async def state(container_id: str) -> ContainerState | None:
    """Ask the engine how a container is doing; None when it is gone."""
    try:
        output = await _run("inspect", "--format", "{{json .State}}", container_id, timeout=30.0)
    except ContainerError:
        return None

    payload: dict[str, Any] = json.loads(output.decode() or "{}")
    return ContainerState(
        running=bool(payload.get("Running")),
        exit_code=payload.get("ExitCode"),
        started_at=payload.get("StartedAt"),
        finished_at=payload.get("FinishedAt"),
    )


@dataclass(frozen=True)
class RunOutcome:
    """What a one-shot container did."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


async def run_once(
    *,
    image: str,
    command: list[str],
    environment: dict[str, str],
    stdin: bytes,
    memory_mb: int,
    cpus: float,
    timeout: float,
) -> RunOutcome:
    """Run a container, feed it one input and wait for it to finish.

    Nothing is left behind: the container removes itself, has no network and
    cannot reach the engine that started it.
    """
    settings = get_settings()
    arguments = [
        "run",
        "--rm",
        "--interactive",
        "--network",
        "none",
        "--label",
        f"{OWNER_LABEL}=true",
        f"--memory={memory_mb}m",
        f"--cpus={cpus}",
        "--security-opt",
        "no-new-privileges",
    ]
    for key, value in environment.items():
        arguments += ["--env", f"{key}={value}"]
    arguments.append(image)
    arguments += command

    try:
        process = await asyncio.create_subprocess_exec(
            settings.docker_binary,
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise ContainerError("No container engine on this machine") from error

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        return RunOutcome(exit_code=-1, stdout="", stderr="", timed_out=True)

    return RunOutcome(
        exit_code=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        timed_out=False,
    )
