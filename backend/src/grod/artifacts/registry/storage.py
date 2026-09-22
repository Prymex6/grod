"""The only place that puts image blobs on disk and takes them off again.

Blobs are named after what they contain, so the same layer pushed twice lands
on the same file and the name can never be talked into pointing somewhere else.
"""

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

from grod.artifacts.registry.models import DIGEST_PATTERN
from grod.config import get_settings

DIGEST_RULE = re.compile(DIGEST_PATTERN)
CHUNK_SIZE = 1024 * 1024
ALGORITHM = "sha256"


class InvalidDigestError(Exception):
    """The digest is not a sha256 the way the registry writes them."""


class NoSuchUploadError(Exception):
    """Nothing is being uploaded under that identifier."""


def _checked(digest: str) -> str:
    """Refuse anything that is not a plain sha256 digest.

    The digest becomes a file name, so this is what keeps a name like
    `../../secret` out of the registry folder.
    """
    if DIGEST_RULE.match(digest) is None:
        raise InvalidDigestError(digest)
    return digest


def blob_path(project_id: UUID, digest: str) -> Path:
    """Where one blob of a project lies."""
    # The colon is not a file name character everywhere, so it becomes a dash.
    name = _checked(digest).replace(":", "-")
    return get_settings().registry_path / str(project_id) / "blobs" / name


def upload_path(upload_id: UUID) -> Path:
    """Where an upload collects its bytes until it is finished."""
    return get_settings().registry_path / "uploads" / str(upload_id)


def start_upload() -> UUID:
    """Open an empty upload and return the identifier it answers to."""
    upload_id = uuid4()
    path = upload_path(upload_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return upload_id


def _append_bytes(path: Path, chunk: bytes) -> None:
    with path.open("ab") as file:
        file.write(chunk)


async def append(upload_id: UUID, content: AsyncIterator[bytes]) -> int:
    """Add to an upload and return how many bytes it holds now."""
    path = upload_path(upload_id)
    if not path.is_file():
        raise NoSuchUploadError(str(upload_id))
    async for chunk in content:
        await asyncio.to_thread(_append_bytes, path, chunk)
    return path.stat().st_size


def _digest_of(path: Path) -> str:
    digest = hashlib.new(ALGORITHM)
    with path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            digest.update(chunk)
    return f"{ALGORITHM}:{digest.hexdigest()}"


async def finish(upload_id: UUID, *, project_id: UUID, digest: str) -> int:
    """Put a finished upload in its place, or refuse it. Returns its size.

    The bytes are weighed before they are kept: a blob whose contents do not
    match the digest the client promised is thrown away.
    """
    staged = upload_path(upload_id)
    if not staged.is_file():
        raise NoSuchUploadError(str(upload_id))

    found = await asyncio.to_thread(_digest_of, staged)
    if found != _checked(digest):
        await asyncio.to_thread(staged.unlink, True)
        raise InvalidDigestError(digest)

    target = blob_path(project_id, digest)
    target.parent.mkdir(parents=True, exist_ok=True)
    size = staged.stat().st_size
    await asyncio.to_thread(staged.replace, target)
    return size


async def cancel(upload_id: UUID) -> None:
    """Throw an unfinished upload away."""
    await asyncio.to_thread(upload_path(upload_id).unlink, True)


async def remove_blob(project_id: UUID, digest: str) -> None:
    """Take one blob off the disk."""
    await asyncio.to_thread(blob_path(project_id, digest).unlink, True)
