"""Watching whether an address still answers."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Response
from sqlalchemy.ext.asyncio import AsyncSession

from grod.main import API_PREFIX
from grod.monitoring import service, watcher
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

CHECKS = f"{API_PREFIX}/checks"
CHECK_NAME = "my-site"
WATCHED_PORT = 14322

# The tiny server answers with whatever this says, so a test can make it fail.
answer_status = 200


@pytest.fixture
async def watched() -> AsyncIterator[str]:
    """A server the checks can look at, running for one test."""
    global answer_status
    answer_status = 200
    app = FastAPI()

    @app.get("/")
    async def root() -> Response:
        return Response(status_code=answer_status, content="all right")

    config = uvicorn.Config(app, host="127.0.0.1", port=WATCHED_PORT, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    yield f"http://127.0.0.1:{WATCHED_PORT}/"

    server.should_exit = True
    await task


@pytest.fixture
async def check(client: httpx.AsyncClient, account: dict[str, Any], watched: str) -> dict[str, Any]:
    del account
    response = await client.post(
        CHECKS, json={"name": CHECK_NAME, "url": watched, "intervalSeconds": 10}
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_a_new_check_has_not_looked_yet(
    client: httpx.AsyncClient, check: dict[str, Any]
) -> None:
    assert check["state"] == "unknown"
    assert check["lastCheckedAt"] is None

    listed = await client.get(CHECKS)
    assert [item["name"] for item in listed.json()] == [CHECK_NAME]


async def test_a_look_at_an_address_that_answers(
    client: httpx.AsyncClient, check: dict[str, Any]
) -> None:
    del check
    looked = await client.post(f"{CHECKS}/{CHECK_NAME}/run")

    assert looked.status_code == httpx.codes.OK, looked.text
    assert looked.json()["state"] == "up"
    assert looked.json()["lastError"] == ""
    assert looked.json()["uptime"] == 100.0

    results = await client.get(f"{CHECKS}/{CHECK_NAME}/results")
    assert len(results.json()) == 1
    assert results.json()[0]["statusCode"] == 200


async def test_a_look_at_an_address_that_answers_wrongly(
    client: httpx.AsyncClient, check: dict[str, Any]
) -> None:
    del check
    global answer_status
    answer_status = 500

    looked = await client.post(f"{CHECKS}/{CHECK_NAME}/run")

    assert looked.json()["state"] == "down"
    assert "500" in looked.json()["lastError"]
    assert looked.json()["uptime"] == 0.0


async def test_a_look_at_an_address_that_is_not_there(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(
        CHECKS, json={"name": "unreachable", "url": "http://127.0.0.1:1/", "timeoutSeconds": 2}
    )

    looked = await client.post(f"{CHECKS}/unreachable/run")

    assert looked.json()["state"] == "down"
    assert looked.json()["lastError"] != ""


async def test_the_uptime_counts_both_kinds_of_look(
    client: httpx.AsyncClient, check: dict[str, Any]
) -> None:
    del check
    global answer_status

    await client.post(f"{CHECKS}/{CHECK_NAME}/run")
    answer_status = 500
    await client.post(f"{CHECKS}/{CHECK_NAME}/run")
    answer_status = 200
    read = await client.post(f"{CHECKS}/{CHECK_NAME}/run")

    assert read.json()["uptime"] == pytest.approx(66.67, abs=0.01)


async def test_a_check_that_is_switched_off_is_not_due(
    client: httpx.AsyncClient, check: dict[str, Any], db_session: AsyncSession
) -> None:
    del check
    await client.patch(f"{CHECKS}/{CHECK_NAME}", json={"enabled": False})

    due = await service.due_checks(db_session)

    assert due == [], "nothing is watched while it is switched off"


async def test_the_loop_looks_at_what_is_due(
    client: httpx.AsyncClient, check: dict[str, Any], db_session: AsyncSession
) -> None:
    del check
    del db_session
    # The loop does one round by hand, the way it does on its own timer.
    await watcher._tick()

    read = await client.get(f"{CHECKS}/{CHECK_NAME}")
    assert read.json()["state"] == "up"
    assert read.json()["lastCheckedAt"] is not None


async def test_somebody_elses_check_is_not_visible(
    client: httpx.AsyncClient, check: dict[str, Any]
) -> None:
    del check
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(f"{CHECKS}/{CHECK_NAME}")).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(CHECKS)).json() == []
