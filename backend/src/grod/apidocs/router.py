"""Endpoints for the API descriptions the platform keeps."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.apidocs import service
from grod.apidocs.models import (
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    URL_MAX_LENGTH,
    ApiDoc,
    DocSource,
)
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor, OptionalActor
from grod.iam.models import ResourceKind, Role

router = APIRouter(prefix="/apis", tags=["apidocs"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such description"


class DocCreate(ApiModel):
    """A new description: sent in, or fetched from an address."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)
    document: str = Field(default="", max_length=service.MAX_DOCUMENT_BYTES)
    url: str = Field(default="", max_length=URL_MAX_LENGTH)
    public: bool = False


class DocReplace(ApiModel):
    """A new version of a description."""

    document: str = Field(min_length=1, max_length=service.MAX_DOCUMENT_BYTES)


class OperationView(ApiModel):
    """One thing an API can do."""

    method: str
    path: str
    summary: str
    description: str
    tags: list[str]


class DocView(ApiModel):
    """A description as the console lists it."""

    id: str
    name: str
    source: DocSource
    url: str
    title: str
    version: str
    public: bool
    operations: int
    fetched_at: datetime | None
    last_error: str
    created_at: datetime


class DocDetailView(DocView):
    """A description together with what it says the API can do."""

    paths: list[OperationView]


def _view(doc: ApiDoc) -> DocView:
    return DocView(
        id=str(doc.id),
        name=doc.name,
        source=doc.source,
        url=doc.url,
        title=doc.title,
        version=doc.version,
        public=doc.public,
        operations=len(service.operations(service.document_of(doc))),
        fetched_at=doc.fetched_at,
        last_error=doc.last_error,
        created_at=doc.created_at,
    )


def _detail_view(doc: ApiDoc) -> DocDetailView:
    found = service.operations(service.document_of(doc))
    return DocDetailView(
        **_view(doc).model_dump(),
        paths=[
            OperationView(
                method=operation.method,
                path=operation.path,
                summary=operation.summary,
                description=operation.description,
                tags=operation.tags,
            )
            for operation in found
        ],
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> ApiDoc:
    """Find a description this actor may do that much with."""
    doc = await scope.allowed(
        db, ApiDoc, actor=actor, kind=ResourceKind.API_DOC, name=name, needed=needed
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return doc


async def _readable(db: AsyncSession, name: str, actor: iam.Actor | None) -> ApiDoc:
    """A description the caller may read: one they were let into, or a public one."""
    if actor is not None:
        mine = await scope.allowed(
            db, ApiDoc, actor=actor, kind=ResourceKind.API_DOC, name=name, needed=Role.VIEWER
        )
        if mine is not None:
            return mine
    doc = await service.find_public(db, name=name)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return doc


@router.get("")
async def list_docs(db: DbSession, actor: CurrentActor) -> list[DocView]:
    """Return the descriptions the caller may see."""
    found = await scope.visible(db, ApiDoc, actor=actor, kind=ResourceKind.API_DOC)
    return [_view(doc) for doc in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_doc(body: DocCreate, db: DbSession, user: CurrentUser) -> DocView:
    """Keep a new description."""
    if not body.document and not body.url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Send a document or an address to fetch it from"
        )
    try:
        doc = await service.create(
            db,
            owner=user,
            name=body.name,
            document=body.document,
            url=body.url,
            public=body.public,
        )
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a description with that name"
        ) from None
    except service.InvalidDocumentError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except service.CannotFetchError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None
    return _view(doc)


@router.get("/{name}")
async def read_doc(name: str, db: DbSession, actor: OptionalActor) -> DocDetailView:
    """Return one description with everything the API can do."""
    return _detail_view(await _readable(db, name, actor))


@router.get("/{name}/document")
async def read_document(name: str, db: DbSession, actor: OptionalActor) -> dict[str, Any]:
    """Return the description itself, as it was written."""
    doc = await _readable(db, name, actor)
    return service.document_of(doc)


@router.put("/{name}/document")
async def replace_document(
    name: str, body: DocReplace, db: DbSession, actor: CurrentActor
) -> DocView:
    """Put a new version of the description in place of the old one."""
    doc = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        await service.replace_document(db, doc=doc, document=body.document)
    except service.InvalidDocumentError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    return _view(doc)


@router.post("/{name}/refresh")
async def refresh_doc(name: str, db: DbSession, actor: CurrentActor) -> DocView:
    """Fetch the description again from the address it lives at."""
    doc = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        await service.refresh(db, doc=doc)
    except service.CannotFetchError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None
    return _view(doc)


@router.patch("/{name}")
async def change_doc(name: str, public: bool, db: DbSession, actor: CurrentActor) -> DocView:
    """Open a description to everybody, or close it again."""
    doc = await _allowed(db, name, actor, Role.ADMIN)
    return _view(await service.set_public(db, doc=doc, public=public))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Forget a description."""
    doc = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, doc=doc)
