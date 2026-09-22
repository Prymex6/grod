"""Queues and the messages that travel through them.

The messages live in Valkey: a list holds what is waiting and a sorted set
holds what somebody has taken, scored by the moment it has to come back. A
message is delivered at least once — whoever takes it has to say it is done,
or it goes round again.
"""

import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from grod.accounts.models import User
from grod.accounts.sessions import get_client
from grod.queues.models import NAME_PATTERN, Queue

NAME_RULE = re.compile(NAME_PATTERN)
RECEIPT_BYTES = 16
MAX_BODY_LENGTH = 256 * 1024
MAX_BATCH = 10

WAITING_PREFIX = "queues:waiting:"
TAKEN_PREFIX = "queues:taken:"
BODIES_PREFIX = "queues:bodies:"
DEAD_PREFIX = "queues:dead:"


class InvalidNameError(Exception):
    """A queue is named like a host name."""


class NameTakenError(Exception):
    """The account already has a queue with that name."""


class MessageTooLargeError(Exception):
    """The body is larger than a message may be."""


@dataclass(frozen=True)
class Message:
    """One message as it leaves the queue."""

    id: str
    body: Any
    attempts: int
    receipt: str


@dataclass(frozen=True)
class QueueDepth:
    """How much is in a queue right now."""

    waiting: int
    taken: int
    dead: int


def _text(value: object) -> str:
    """Read an answer of Valkey as text; the client decodes for us."""
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _keys(queue: Queue) -> tuple[str, str, str, str]:
    """The four Valkey keys one queue uses."""
    name = str(queue.id)
    return (
        f"{WAITING_PREFIX}{name}",
        f"{TAKEN_PREFIX}{name}",
        f"{BODIES_PREFIX}{name}",
        f"{DEAD_PREFIX}{name}",
    )


async def find(session: AsyncSession, *, owner: User, name: str) -> Queue | None:
    """Return one queue of an account by name."""
    result = await session.execute(
        select(Queue).where(Queue.owner_id == owner.id, Queue.name == name.lower())
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    owner: User,
    name: str,
    visibility_seconds: int,
    max_attempts: int,
) -> Queue:
    """Create a queue."""
    address = name.lower()
    if NAME_RULE.match(address) is None:
        raise InvalidNameError(name)

    queue = Queue(
        owner_id=owner.id,
        name=address,
        visibility_seconds=visibility_seconds,
        max_attempts=max_attempts,
    )
    session.add(queue)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise NameTakenError(name) from error
    return queue


async def delete(session: AsyncSession, *, queue: Queue) -> None:
    """Remove a queue together with everything waiting in it."""
    await get_client().delete(*_keys(queue))
    await session.delete(queue)
    await session.commit()


async def publish(queue: Queue, body: Any) -> str:  # noqa: ANN401  (whatever JSON was sent)
    """Put a message at the end of the queue and return its identifier."""
    encoded = json.dumps(body)
    if len(encoded) > MAX_BODY_LENGTH:
        raise MessageTooLargeError(len(encoded))

    waiting, _, bodies, _ = _keys(queue)
    message_id = secrets.token_hex(RECEIPT_BYTES)

    client = get_client()
    pipeline = client.pipeline()
    pipeline.hset(bodies, message_id, json.dumps({"body": body, "attempts": 0}))
    pipeline.lpush(waiting, message_id)
    await pipeline.execute()
    return message_id


async def receive(queue: Queue, *, limit: int = 1) -> list[Message]:
    """Take messages off the queue and hide them for a while."""
    await _return_expired(queue)

    waiting, taken, bodies, dead = _keys(queue)
    client = get_client()
    deadline = time.time() + queue.visibility_seconds
    messages: list[Message] = []

    for _ in range(min(limit, MAX_BATCH)):
        popped = await client.rpop(waiting)
        if popped is None:
            break
        message_id = _text(popped)

        stored = await client.hget(bodies, message_id)
        if stored is None:
            # The body is gone, so there is nothing to hand over.
            continue

        record = json.loads(_text(stored))
        record["attempts"] += 1
        if record["attempts"] > queue.max_attempts:
            # It has been tried enough times; it waits for a person instead.
            await client.hset(dead, message_id, json.dumps(record))
            await client.hdel(bodies, message_id)
            continue

        receipt = secrets.token_hex(RECEIPT_BYTES)
        record["receipt"] = receipt
        await client.hset(bodies, message_id, json.dumps(record))
        await client.zadd(taken, {message_id: deadline})
        messages.append(
            Message(
                id=message_id, body=record["body"], attempts=record["attempts"], receipt=receipt
            )
        )

    return messages


async def _return_expired(queue: Queue) -> int:
    """Put back everything whose time ran out; returns how many came back."""
    waiting, taken, _, _ = _keys(queue)
    client = get_client()

    overdue = await client.zrangebyscore(taken, "-inf", time.time())
    if not overdue:
        return 0

    pipeline = client.pipeline()
    for entry in overdue:
        message_id = _text(entry)
        pipeline.lpush(waiting, message_id)
        pipeline.zrem(taken, message_id)
    await pipeline.execute()
    return len(overdue)


async def acknowledge(queue: Queue, *, message_id: str, receipt: str) -> bool:
    """Say a message is done with, so it never comes back."""
    _, taken, bodies, _ = _keys(queue)
    client = get_client()

    stored = await client.hget(bodies, message_id)
    if stored is None:
        return False
    record = json.loads(_text(stored))
    if record.get("receipt") != receipt:
        # Somebody else holds this message now; their receipt is the valid one.
        return False

    pipeline = client.pipeline()
    pipeline.zrem(taken, message_id)
    pipeline.hdel(bodies, message_id)
    await pipeline.execute()
    return True


async def depth(queue: Queue) -> QueueDepth:
    """Count what the queue holds."""
    waiting, taken, _, dead = _keys(queue)
    client = get_client()
    return QueueDepth(
        waiting=await client.llen(waiting),
        taken=await client.zcard(taken),
        dead=await client.hlen(dead),
    )


async def purge(queue: Queue) -> None:
    """Throw away everything the queue holds."""
    await get_client().delete(*_keys(queue))


async def dead_messages(queue: Queue, *, limit: int = 100) -> list[Message]:
    """Return the messages that were tried too many times."""
    _, _, _, dead = _keys(queue)
    client = get_client()

    found: list[Message] = []
    for message_id, stored in (await client.hgetall(dead)).items():
        record = json.loads(_text(stored))
        found.append(
            Message(
                id=_text(message_id),
                body=record["body"],
                attempts=record["attempts"],
                receipt="",
            )
        )
        if len(found) >= limit:
            break
    return found


def queue_id(queue: Queue) -> UUID:
    """The identifier, spelled out for the places that need it."""
    return queue.id
