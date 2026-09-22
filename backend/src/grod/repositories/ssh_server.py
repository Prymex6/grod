"""Git over SSH.

A `git clone ssh://git@grod.example/<login>/<project>.git` opens a session
here. The account is recognised by its public key, Grod checks whether it may
read or write, and only then git's own upload-pack or receive-pack runs.
"""

import asyncio
import logging
import shlex
from pathlib import Path
from typing import Any

import asyncssh

from grod.accounts import service as accounts
from grod.config import get_settings
from grod.db import get_session_factory
from grod.repositories import after_push, git, pushes, service, ssh_keys

logger = logging.getLogger(__name__)

UPLOAD_PACK = "git-upload-pack"
RECEIVE_PACK = "git-receive-pack"
COMMAND_PARTS = 2
ADDRESS_PARTS = 2
USER_ID_KEY = "grod_user_id"
CHUNK_SIZE = 64 * 1024
# Messages for the Git client; they travel as bytes over the session.
NO_ACCESS_MESSAGE = b"No such project, or you have no access to it.\n"
NOT_OWNER_MESSAGE = b"Only the owner may push to this project.\n"
UNSUPPORTED_COMMAND_MESSAGE = b"Grod serves git clone, fetch and push only.\n"


class GitCommandError(Exception):
    """The client asked for something other than a Git service."""


class GitServiceError(Exception):
    """The git program could not be started."""


def parse_command(command: str) -> tuple[str, str, str]:
    """Split `git-upload-pack '/login/project.git'` into service, login, slug."""
    try:
        parts = shlex.split(command)
    except ValueError as error:
        raise GitCommandError(command) from error
    if len(parts) != COMMAND_PARTS or parts[0] not in {UPLOAD_PACK, RECEIVE_PACK}:
        raise GitCommandError(command)

    address = parts[1].strip("/")
    address = address.removesuffix(".git")
    pieces = address.split("/")
    if len(pieces) != ADDRESS_PARTS or not all(pieces):
        raise GitCommandError(command)
    return parts[0], pieces[0], pieces[1]


class GitSshServer(asyncssh.SSHServer):
    """One connection: who is on the other side, proven by a public key."""

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        self._connection = conn

    def begin_auth(self, username: str) -> bool:
        del username
        # Signing in without a key is never allowed.
        return True

    def public_key_auth_supported(self) -> bool:
        return True

    async def validate_public_key(self, username: str, key: asyncssh.SSHKey) -> bool:
        """Accept the key when some account has registered it."""
        if username != get_settings().ssh_user:
            return False
        async with get_session_factory()() as session:
            user = await ssh_keys.find_owner(session, fingerprint=key.get_fingerprint())
        if user is None:
            return False
        self._connection.set_extra_info(**{USER_ID_KEY: user.id})
        return True


async def _run_git_service(
    process: asyncssh.SSHServerProcess[bytes], service_name: str, path: Path
) -> None:
    """Hand the session over to git's own upload-pack or receive-pack."""
    settings = get_settings()
    subprocess = await asyncio.create_subprocess_exec(
        settings.git_binary,
        service_name.removeprefix("git-"),
        str(path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if subprocess.stdin is None or subprocess.stdout is None or subprocess.stderr is None:
        raise GitServiceError(service_name)
    git_stdin, git_stdout, git_stderr = subprocess.stdin, subprocess.stdout, subprocess.stderr

    async def to_client(pipe: asyncio.StreamReader, sink: Any) -> None:  # noqa: ANN401
        while True:
            chunk = await pipe.read(CHUNK_SIZE)
            if not chunk:
                break
            sink.write(chunk)
            await sink.drain()

    async def from_client() -> None:
        while True:
            chunk = await process.stdin.read(CHUNK_SIZE)
            if not chunk:
                break
            git_stdin.write(chunk)
            await git_stdin.drain()
        git_stdin.close()

    await asyncio.gather(
        from_client(),
        to_client(git_stdout, process.stdout),
        to_client(git_stderr, process.stderr),
    )
    process.exit(await subprocess.wait())


async def handle_session(process: asyncssh.SSHServerProcess[bytes]) -> None:
    """Check the request, then let git do the talking."""
    user_id = process.channel.get_connection().get_extra_info(USER_ID_KEY)
    command = process.command or ""

    try:
        service_name, owner_login, slug = parse_command(command)
    except GitCommandError:
        process.stderr.write(UNSUPPORTED_COMMAND_MESSAGE)
        process.exit(1)
        return

    async with get_session_factory()() as session:
        user = None if user_id is None else await accounts.get_by_id(session, user_id)
        found = await service.find(session, owner_login=owner_login, slug=slug)

        access = (
            await service.access_of(session, project=found.project, user=user)
            if found is not None
            else None
        )
        if found is None or access is None or not access.read:
            process.stderr.write(NO_ACCESS_MESSAGE)
            process.exit(1)
            return
        if service_name == RECEIVE_PACK and not access.write:
            process.stderr.write(NOT_OWNER_MESSAGE)
            process.exit(1)
            return
        path = git.repository_path(found.project.id)
        project = found.project
        pusher = user
        # The tips before the push tell the pipelines which branches it moved.
        before = await pushes.branch_tips(project) if service_name == RECEIVE_PACK else {}

    await _run_git_service(process, service_name, path)

    if service_name == RECEIVE_PACK:
        async with get_session_factory()() as session:
            merged = await session.merge(project)
            await after_push.handle(session, project=merged, before=before, pusher=pusher)


def ensure_host_key() -> Path:
    """Create the server's own key on first run and return its path."""
    path = get_settings().ssh_host_key_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        key = asyncssh.generate_private_key("ssh-ed25519")
        path.write_bytes(key.export_private_key())
        path.chmod(0o600)
    return path


async def serve() -> None:
    """Run the SSH server until the process is stopped."""
    settings = get_settings()
    await asyncssh.create_server(
        GitSshServer,
        settings.ssh_host,
        settings.ssh_port,
        server_host_keys=[str(ensure_host_key())],
        process_factory=handle_session,
        # Git sends packfiles, so the session carries bytes, not text.
        encoding=None,
    )
    logger.info("Git over SSH listening on port %s", settings.ssh_port)
    await asyncio.Event().wait()


def main() -> None:
    """Entry point of the `grod-ssh` command."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Git over SSH stopped")


if __name__ == "__main__":
    main()
