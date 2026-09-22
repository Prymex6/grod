"""Git over HTTPS, served by the `git http-backend` program.

Clone, fetch and push all speak the "smart HTTP" protocol. Instead of
reimplementing it, Grod runs git's own CGI program and passes its answer on.
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from grod.config import get_settings

HEADER_SEPARATOR = b"\r\n\r\n"
STATUS_HEADER = "status"
DEFAULT_STATUS = 200
UPLOAD_PACK = "git-upload-pack"
RECEIVE_PACK = "git-receive-pack"


@dataclass(frozen=True)
class CgiResponse:
    """What git's CGI program answered."""

    status: int
    headers: dict[str, str]
    body: bytes


def _parse_status(value: str) -> int:
    return int(value.split()[0])


async def run_http_backend(
    *,
    project_id: UUID,
    suffix: str,
    method: str,
    query_string: str,
    content_type: str,
    body: bytes,
    remote_user: str,
) -> CgiResponse:
    """Hand one Git request over to git http-backend and return its answer."""
    settings = get_settings()
    environment = {
        "GIT_PROJECT_ROOT": str(settings.repositories_path.resolve()),
        # Grod decides who may read or write before calling this.
        "GIT_HTTP_EXPORT_ALL": "1",
        "PATH_INFO": f"/{project_id}.git{suffix}",
        "REQUEST_METHOD": method,
        "QUERY_STRING": query_string,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)),
        "REMOTE_USER": remote_user,
        "GIT_COMMITTER_NAME": remote_user or "grod",
        "GIT_COMMITTER_EMAIL": f"{remote_user or 'grod'}@grod",
    }

    process = await asyncio.create_subprocess_exec(
        settings.git_binary,
        "http-backend",
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate(body)

    head, _, payload = stdout.partition(HEADER_SEPARATOR)
    headers: dict[str, str] = {}
    status = DEFAULT_STATUS
    for line in head.decode(errors="replace").splitlines():
        name, _, value = line.partition(":")
        name = name.strip().lower()
        value = value.strip()
        if name == STATUS_HEADER:
            status = _parse_status(value)
        elif name:
            headers[name] = value

    return CgiResponse(status=status, headers=headers, body=payload)


def service_of(query_string: str, suffix: str) -> str | None:
    """Name the Git service a request is asking for, if any."""
    if suffix.endswith(f"/{RECEIVE_PACK}"):
        return RECEIVE_PACK
    if suffix.endswith(f"/{UPLOAD_PACK}"):
        return UPLOAD_PACK
    for part in query_string.split("&"):
        name, _, value = part.partition("=")
        if name == "service":
            return value or None
    return None
