"""Endpoints for queues and the messages in them."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.dependencies import CurrentUser
from grod.accounts.schemas import ApiModel
from grod.db import get_db_session
from grod.iam import scope
from grod.iam import service as iam
from grod.iam.dependencies import CurrentActor
from grod.iam.models import ResourceKind, Role
from grod.queues import service
from grod.queues.models import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_VISIBILITY_SECONDS,
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    Queue,
)
from grod.quotas import service as quotas
from grod.quotas.errors import refusal
from grod.quotas.service import Thing

router = APIRouter(prefix="/queues", tags=["queues"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

NOT_FOUND_DETAIL = "No such queue"
MIN_VISIBILITY_SECONDS = 1
MAX_VISIBILITY_SECONDS = 3600
MIN_ATTEMPTS = 1
MAX_ATTEMPTS = 100


class QueueCreate(ApiModel):
    """A new queue."""

    name: str = Field(pattern=NAME_PATTERN, min_length=3, max_length=NAME_MAX_LENGTH)
    visibility_seconds: int = Field(
        default=DEFAULT_VISIBILITY_SECONDS,
        ge=MIN_VISIBILITY_SECONDS,
        le=MAX_VISIBILITY_SECONDS,
    )
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=MIN_ATTEMPTS, le=MAX_ATTEMPTS)


class QueueView(ApiModel):
    """A queue with what it holds right now."""

    id: str
    name: str
    visibility_seconds: int
    max_attempts: int
    waiting: int
    taken: int
    dead: int
    created_at: datetime


class MessageView(ApiModel):
    """One message handed to whoever asked for it."""

    id: str
    body: Any
    attempts: int
    receipt: str


class PublishedView(ApiModel):
    """The identifier of a message that was just put in."""

    id: str


async def _view(queue: Queue) -> QueueView:
    depth = await service.depth(queue)
    return QueueView(
        id=str(queue.id),
        name=queue.name,
        visibility_seconds=queue.visibility_seconds,
        max_attempts=queue.max_attempts,
        waiting=depth.waiting,
        taken=depth.taken,
        dead=depth.dead,
        created_at=queue.created_at,
    )


def _message_view(message: service.Message) -> MessageView:
    return MessageView(
        id=message.id, body=message.body, attempts=message.attempts, receipt=message.receipt
    )


async def _allowed(db: AsyncSession, name: str, actor: iam.Actor, needed: Role) -> Queue:
    """Find a queue this actor may do that much with."""
    queue = await scope.allowed(
        db, Queue, actor=actor, kind=ResourceKind.QUEUE, name=name, needed=needed
    )
    if queue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return queue


@router.get("")
async def list_queues(db: DbSession, actor: CurrentActor) -> list[QueueView]:
    """Return the queues the caller may see."""
    found = await scope.visible(db, Queue, actor=actor, kind=ResourceKind.QUEUE)
    return [await _view(queue) for queue in found]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_queue(body: QueueCreate, db: DbSession, user: CurrentUser) -> QueueView:
    """Create a queue."""
    try:
        await quotas.ensure_room_for_one_more(db, owner_id=user.id, thing=Thing.QUEUE)
    except quotas.OverQuotaError as error:
        raise refusal(error) from None

    try:
        queue = await service.create(
            db,
            owner=user,
            name=body.name,
            visibility_seconds=body.visibility_seconds,
            max_attempts=body.max_attempts,
        )
    except service.InvalidNameError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid name") from None
    except service.NameTakenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="You already have a queue with that name"
        ) from None
    return await _view(queue)


@router.get("/{name}")
async def read_queue(name: str, db: DbSession, actor: CurrentActor) -> QueueView:
    """Return one queue with what it holds."""
    return await _view(await _allowed(db, name, actor, Role.VIEWER))


@router.post("/{name}/messages", status_code=status.HTTP_201_CREATED)
async def publish_message(
    name: str,
    # Without Body() FastAPI would read a bare value as a query parameter.
    message: Annotated[Any, Body()],  # noqa: ANN401  (whatever JSON the caller sent)
    db: DbSession,
    actor: CurrentActor,
) -> PublishedView:
    """Put a message at the end of the queue."""
    queue = await _allowed(db, name, actor, Role.OPERATOR)
    try:
        message_id = await service.publish(queue, message)
    except service.MessageTooLargeError:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The message is too large"
        ) from None
    return PublishedView(id=message_id)


@router.post("/{name}/receive")
async def receive_messages(
    name: str,
    db: DbSession,
    actor: CurrentActor,
    limit: Annotated[int, Query(le=service.MAX_BATCH)] = 1,
) -> list[MessageView]:
    """Take messages off the queue; they come back unless they are acknowledged."""
    queue = await _allowed(db, name, actor, Role.OPERATOR)
    return [_message_view(message) for message in await service.receive(queue, limit=limit)]


@router.post("/{name}/messages/{message_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_message(
    name: str, message_id: str, receipt: str, db: DbSession, actor: CurrentActor
) -> None:
    """Say a message is done with, so it never comes back."""
    queue = await _allowed(db, name, actor, Role.OPERATOR)
    if not await service.acknowledge(queue, message_id=message_id, receipt=receipt):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No such message, or the receipt is stale"
        )


@router.get("/{name}/dead")
async def read_dead_messages(name: str, db: DbSession, actor: CurrentActor) -> list[MessageView]:
    """Return the messages that were tried too many times."""
    queue = await _allowed(db, name, actor, Role.VIEWER)
    return [_message_view(message) for message in await service.dead_messages(queue)]


@router.post("/{name}/purge", status_code=status.HTTP_204_NO_CONTENT)
async def purge_queue(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Throw away everything the queue holds."""
    queue = await _allowed(db, name, actor, Role.ADMIN)
    await service.purge(queue)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue(name: str, db: DbSession, actor: CurrentActor) -> None:
    """Remove a queue together with everything in it."""
    queue = await _allowed(db, name, actor, Role.ADMIN)
    await service.delete(db, queue=queue)
