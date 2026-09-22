"""Starting, stopping and watching the applications of an account."""

import json
import re
import shlex
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.apps import containers
from grod.apps.models import NAME_PATTERN, Application, AppState
from grod.config import get_settings

NAME_RULE = re.compile(NAME_PATTERN)
# The name of the container, so two accounts may use the same application name.
CONTAINER_PREFIX = "grod-app"
MAX_ERROR_LENGTH = 2000


class InvalidNameError(Exception):
    """An application is named like a host name."""


class NameTakenError(Exception):
    """The account already has an application with that name."""


class NoFreePortError(Exception):
    """Every port of the range is taken."""


class EngineUnavailableError(Exception):
    """No container engine answers on this machine."""


def container_name(application: Application) -> str:
    """The name the engine knows this application by."""
    return f"{CONTAINER_PREFIX}-{application.id}"


async def find(session: AsyncSession, *, owner: User, name: str) -> Application | None:
    """Return one application of an account by name."""
    result = await session.execute(
        select(Application).where(
            Application.owner_id == owner.id, Application.name == name.lower()
        )
    )
    return result.scalar_one_or_none()


async def _free_port(session: AsyncSession) -> int:
    """Pick a port of the range that no application holds."""
    settings = get_settings()
    result = await session.execute(
        select(Application.host_port).where(Application.host_port.is_not(None))
    )
    taken = set(result.scalars())
    for port in range(settings.app_port_first, settings.app_port_last + 1):
        if port not in taken:
            return port
    raise NoFreePortError


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    image: str,
    command: str = "",
    environment: dict[str, str] | None = None,
    port: int | None = None,
    memory_mb: int,
    cpus: float,
) -> Application:
    """Describe an application. Nothing runs until it is started."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    application = Application(
        owner_id=owner.id,
        name=address,
        image=image,
        command=command,
        environment=json.dumps(environment or {}),
        port=port,
        host_port=await _free_port(session) if port is not None else None,
        memory_mb=memory_mb,
        cpus=str(cpus),
    )
    session.add(application)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return application


async def start(session: AsyncSession, *, application: Application) -> Application:
    """Run the application, replacing a container that is already there."""
    if not await containers.available():
        raise EngineUnavailableError

    await _forget_container(application)

    environment: dict[str, str] = json.loads(application.environment or "{}")
    try:
        container_id = await containers.run(
            name=container_name(application),
            image=application.image,
            command=shlex.split(application.command) if application.command else [],
            environment=environment,
            port=application.port,
            host_port=application.host_port,
            memory_mb=application.memory_mb,
            cpus=float(application.cpus),
        )
    except containers.ContainerError as error:
        application.state = AppState.FAILED
        application.container_id = None
        application.last_error = str(error)[:MAX_ERROR_LENGTH]
        await session.commit()
        return application

    application.container_id = container_id
    application.state = AppState.RUNNING
    application.last_error = ""
    await session.commit()
    return application


async def stop(session: AsyncSession, *, application: Application) -> Application:
    """Stop the application and forget its container."""
    await _forget_container(application)
    application.container_id = None
    application.state = AppState.STOPPED
    await session.commit()
    return application


async def _forget_container(application: Application) -> None:
    """Remove the container of an application, if there is one."""
    name = container_name(application)
    try:
        await containers.remove(name)
    except containers.ContainerError:
        # There was nothing to remove, which is exactly what was wanted.
        return


async def delete(session: AsyncSession, *, application: Application) -> None:
    """Remove an application together with its container."""
    await _forget_container(application)
    await session.delete(application)
    await session.commit()


async def refresh(session: AsyncSession, *, application: Application) -> Application:
    """Ask the engine how the application is really doing."""
    if application.container_id is None:
        return application

    found = await containers.state(application.container_id)
    if found is None:
        application.state = AppState.STOPPED
        application.container_id = None
    elif found.running:
        application.state = AppState.RUNNING
    else:
        application.state = AppState.FAILED if found.exit_code else AppState.STOPPED
    await session.commit()
    return application


async def logs(application: Application, *, tail: int = containers.LOG_TAIL) -> str:
    """Return what the application printed."""
    if application.container_id is None:
        return ""
    try:
        return await containers.logs(application.container_id, tail=tail)
    except containers.ContainerError:
        return ""


async def owner_of(session: AsyncSession, application: Application) -> User | None:
    """Return the account an application belongs to."""
    return await session.get(User, application.owner_id)


def environment_of(application: Application) -> dict[str, str]:
    """Read the variables of an application."""
    values: dict[str, str] = json.loads(application.environment or "{}")
    return values


def application_id(application: Application) -> UUID:
    """The identifier, spelled out for the places that need it."""
    return application.id
