"""Keeping API descriptions and reading what is inside them."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.apidocs.models import NAME_PATTERN, ApiDoc, DocSource

NAME_RULE = re.compile(NAME_PATTERN)
FETCH_TIMEOUT_SECONDS = 20.0
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_ERROR_LENGTH = 1000
METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


class InvalidNameError(Exception):
    """A description is named like a host name."""


class NameTakenError(Exception):
    """The account already has a description with that name."""


class InvalidDocumentError(Exception):
    """The document is not an OpenAPI description the platform can read."""


class CannotFetchError(Exception):
    """The address did not give the document."""


@dataclass(frozen=True)
class Operation:
    """One thing an API can do."""

    method: str
    path: str
    summary: str
    description: str
    tags: list[str]


def parse_document(text: str) -> dict[str, Any]:
    """Read a description written as JSON or as YAML."""
    if len(text.encode()) > MAX_DOCUMENT_BYTES:
        raise InvalidDocumentError("The document is too large")

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise InvalidDocumentError(str(error)) from error

    if not isinstance(loaded, dict):
        raise InvalidDocumentError("The document has to be an object")
    if "openapi" not in loaded and "swagger" not in loaded:
        raise InvalidDocumentError("This is not an OpenAPI description")
    return loaded


def describe(document: dict[str, Any]) -> tuple[str, str]:
    """The title and the version the document gives itself."""
    info = document.get("info") or {}
    return str(info.get("title", "")), str(info.get("version", ""))


def operations(document: dict[str, Any]) -> list[Operation]:
    """Everything the described API can do, by path and method."""
    found: list[Operation] = []
    paths = document.get("paths") or {}
    if not isinstance(paths, dict):
        return found

    for path, entry in paths.items():
        if not isinstance(entry, dict):
            continue
        for method, operation in entry.items():
            if method.lower() not in METHODS or not isinstance(operation, dict):
                continue
            tags = operation.get("tags") or []
            found.append(
                Operation(
                    method=method.upper(),
                    path=str(path),
                    summary=str(operation.get("summary", "")),
                    description=str(operation.get("description", "")),
                    tags=[str(tag) for tag in tags if isinstance(tag, str)],
                )
            )
    return found


async def find(session: AsyncSession, *, owner: User, name: str) -> ApiDoc | None:
    """Return one description of an account by name."""
    result = await session.execute(
        select(ApiDoc).where(ApiDoc.owner_id == owner.id, ApiDoc.name == name.lower())
    )
    return result.scalar_one_or_none()


async def find_public(session: AsyncSession, *, name: str) -> ApiDoc | None:
    """Return a description anybody may read, by name."""
    result = await session.execute(
        select(ApiDoc).where(ApiDoc.name == name.lower(), ApiDoc.public.is_(True))
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    document: str = "",
    url: str = "",
    public: bool = False,
) -> ApiDoc:
    """Keep a new description, either sent in or fetched from an address."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    doc = ApiDoc(
        owner_id=owner.id,
        name=address,
        source=DocSource.URL if url else DocSource.UPLOADED,
        url=url,
        public=public,
    )
    if document:
        _write_document(doc, parse_document(document))

    session.add(doc)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error

    if url:
        await refresh(session, doc=doc)
    return doc


async def replace_document(session: AsyncSession, *, doc: ApiDoc, document: str) -> ApiDoc:
    """Put a new version of the description in place of the old one."""
    _write_document(doc, parse_document(document))
    await session.commit()
    return doc


async def refresh(session: AsyncSession, *, doc: ApiDoc) -> ApiDoc:
    """Fetch the description again from the address it lives at."""
    if doc.source != DocSource.URL or not doc.url:
        raise CannotFetchError("This description has no address")

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            answer = await client.get(doc.url, follow_redirects=True)
            answer.raise_for_status()
        parsed = parse_document(answer.text)
    except (httpx.HTTPError, InvalidDocumentError) as error:
        doc.last_error = str(error)[:MAX_ERROR_LENGTH]
        await session.commit()
        raise CannotFetchError(str(error)) from error

    _write_document(doc, parsed)
    await session.commit()
    return doc


def _write_document(doc: ApiDoc, parsed: dict[str, Any]) -> None:
    """Keep the parsed document and what it says about itself."""
    doc.document = json.dumps(parsed)
    doc.title, doc.version = describe(parsed)
    doc.fetched_at = datetime.now(UTC)
    doc.last_error = ""


async def set_public(session: AsyncSession, *, doc: ApiDoc, public: bool) -> ApiDoc:
    """Open a description to everybody, or close it again."""
    doc.public = public
    await session.commit()
    return doc


async def delete(session: AsyncSession, *, doc: ApiDoc) -> None:
    """Forget a description."""
    await session.delete(doc)
    await session.commit()


def document_of(doc: ApiDoc) -> dict[str, Any]:
    """The description itself."""
    parsed: dict[str, Any] = json.loads(doc.document or "{}")
    return parsed
