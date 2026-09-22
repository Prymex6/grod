"""Queues that carry messages, with at-least-once delivery."""

import asyncio
from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

QUEUES = f"{API_PREFIX}/queues"
QUEUE_NAME = "orders"
QUEUE = f"{QUEUES}/{QUEUE_NAME}"


@pytest.fixture
async def queue(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    response = await client.post(
        QUEUES, json={"name": QUEUE_NAME, "visibilitySeconds": 1, "maxAttempts": 2}
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_a_message_comes_out_the_way_it_went_in(
    client: httpx.AsyncClient, queue: dict[str, Any]
) -> None:
    del queue
    published = await client.post(f"{QUEUE}/messages", json={"order": 7, "product": "honey"})
    assert published.status_code == httpx.codes.CREATED, published.text

    received = await client.post(f"{QUEUE}/receive")
    messages = received.json()

    assert len(messages) == 1
    assert messages[0]["body"] == {"order": 7, "product": "honey"}
    assert messages[0]["attempts"] == 1
    assert messages[0]["receipt"] != ""


async def test_an_unanswered_message_comes_back(
    client: httpx.AsyncClient, queue: dict[str, Any]
) -> None:
    del queue
    await client.post(f"{QUEUE}/messages", json={"numer": 1})
    first = (await client.post(f"{QUEUE}/receive")).json()[0]

    # Nothing acknowledges it, so once the time runs out it is handed out again.
    assert (await client.post(f"{QUEUE}/receive")).json() == []
    await asyncio.sleep(1.2)
    again = (await client.post(f"{QUEUE}/receive")).json()

    assert len(again) == 1
    assert again[0]["id"] == first["id"]
    assert again[0]["attempts"] == 2, "the second try is counted"


async def test_an_acknowledged_message_never_comes_back(
    client: httpx.AsyncClient, queue: dict[str, Any]
) -> None:
    del queue
    await client.post(f"{QUEUE}/messages", json={"numer": 2})
    message = (await client.post(f"{QUEUE}/receive")).json()[0]

    acknowledged = await client.post(
        f"{QUEUE}/messages/{message['id']}/ack", params={"receipt": message["receipt"]}
    )

    assert acknowledged.status_code == httpx.codes.NO_CONTENT
    await asyncio.sleep(1.2)
    assert (await client.post(f"{QUEUE}/receive")).json() == []

    read = await client.get(QUEUE)
    assert read.json()["waiting"] == 0
    assert read.json()["taken"] == 0


async def test_a_stale_receipt_is_refused(client: httpx.AsyncClient, queue: dict[str, Any]) -> None:
    del queue
    await client.post(f"{QUEUE}/messages", json={"numer": 3})
    first = (await client.post(f"{QUEUE}/receive")).json()[0]
    await asyncio.sleep(1.2)
    # Somebody else has it now, with a receipt of their own.
    await client.post(f"{QUEUE}/receive")

    refused = await client.post(
        f"{QUEUE}/messages/{first['id']}/ack", params={"receipt": first["receipt"]}
    )

    assert refused.status_code == httpx.codes.NOT_FOUND


async def test_a_message_tried_too_often_is_set_aside(
    client: httpx.AsyncClient, queue: dict[str, Any]
) -> None:
    del queue
    await client.post(f"{QUEUE}/messages", json={"numer": 4})

    # The queue allows two tries; the third hand-out puts it aside instead.
    for _ in range(3):
        await client.post(f"{QUEUE}/receive")
        await asyncio.sleep(1.2)

    dead = await client.get(f"{QUEUE}/dead")
    assert [item["body"] for item in dead.json()] == [{"numer": 4}]

    read = await client.get(QUEUE)
    assert read.json()["dead"] == 1
    assert read.json()["waiting"] == 0


async def test_several_messages_come_in_one_go(
    client: httpx.AsyncClient, queue: dict[str, Any]
) -> None:
    del queue
    for number in range(3):
        await client.post(f"{QUEUE}/messages", json={"numer": number})

    received = await client.post(f"{QUEUE}/receive", params={"limit": 3})

    assert [item["body"]["numer"] for item in received.json()] == [0, 1, 2], "oldest first"


async def test_purging_empties_the_queue(client: httpx.AsyncClient, queue: dict[str, Any]) -> None:
    del queue
    await client.post(f"{QUEUE}/messages", json={"numer": 5})

    purged = await client.post(f"{QUEUE}/purge")

    assert purged.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(QUEUE)).json()["waiting"] == 0


async def test_somebody_elses_queue_is_not_visible(
    client: httpx.AsyncClient, queue: dict[str, Any]
) -> None:
    del queue
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(QUEUE)).status_code == httpx.codes.NOT_FOUND
    assert (await client.post(f"{QUEUE}/messages", json={})).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(QUEUES)).json() == []
