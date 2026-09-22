"""Names that stand in front of what the platform runs."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

ROUTES = f"{API_PREFIX}/routes"
ROUTE_NAME = "my-site"
TRAFFIC = f"/-/traffic/{ROUTE_NAME}"
ANSWER = {"kto": "an application behind a route"}
BACKEND_PORT = 14321


@pytest.fixture
async def backend() -> AsyncIterator[str]:
    """A tiny server the routes can point at, running for one test."""
    app = FastAPI()

    @app.get("/")
    async def root() -> dict[str, str]:
        return ANSWER

    @app.get("/path/deeper")
    async def deeper(question: str = "") -> dict[str, str]:
        return {"path": "next", "question": question}

    @app.post("/echo")
    async def echo(body: dict[str, Any]) -> dict[str, Any]:
        return {"received": body}

    config = uvicorn.Config(app, host="127.0.0.1", port=BACKEND_PORT, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    yield f"http://127.0.0.1:{BACKEND_PORT}"

    server.should_exit = True
    await task


@pytest.fixture
async def route(client: httpx.AsyncClient, account: dict[str, Any], backend: str) -> dict[str, Any]:
    del account
    response = await client.post(
        ROUTES, json={"name": ROUTE_NAME, "targetKind": "address", "target": backend}
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_a_route_hands_the_call_over(
    client: httpx.AsyncClient, route: dict[str, Any]
) -> None:
    assert route["url"].endswith(f"/-/traffic/{ROUTE_NAME}/")

    answered = await client.get(f"{TRAFFIC}/")

    assert answered.status_code == httpx.codes.OK, answered.text
    assert answered.json() == ANSWER


async def test_the_path_and_the_question_travel_along(
    client: httpx.AsyncClient, route: dict[str, Any]
) -> None:
    del route
    answered = await client.get(f"{TRAFFIC}/path/deeper", params={"question": "how-many"})

    assert answered.json() == {"path": "next", "question": "how-many"}


async def test_a_body_travels_along_too(client: httpx.AsyncClient, route: dict[str, Any]) -> None:
    del route
    answered = await client.post(f"{TRAFFIC}/echo", json={"number": 7})

    assert answered.json() == {"received": {"number": 7}}


async def test_a_private_route_is_not_open_to_everybody(
    client: httpx.AsyncClient, account: dict[str, Any], backend: str
) -> None:
    del account
    await client.post(
        ROUTES,
        json={"name": "hidden", "targetKind": "address", "target": backend, "public": False},
    )

    mine = await client.get("/-/traffic/hidden/")
    assert mine.status_code == httpx.codes.OK, "the owner goes through"

    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.get("/-/traffic/hidden/")

    assert refused.status_code == httpx.codes.NOT_FOUND


async def test_a_route_to_nothing_says_so(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(
        ROUTES, json={"name": "nowhere", "targetKind": "application", "target": "no-such-target"}
    )

    answered = await client.get("/-/traffic/nowhere/")

    assert answered.status_code == httpx.codes.BAD_GATEWAY


async def test_a_name_belongs_to_one_route(
    client: httpx.AsyncClient, route: dict[str, Any], backend: str
) -> None:
    del route
    again = await client.post(
        ROUTES, json={"name": ROUTE_NAME, "targetKind": "address", "target": backend}
    )

    assert again.status_code == httpx.codes.CONFLICT


async def test_a_route_that_is_gone_answers_nothing(
    client: httpx.AsyncClient, route: dict[str, Any]
) -> None:
    del route
    removed = await client.delete(f"{ROUTES}/{ROUTE_NAME}")

    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(f"{TRAFFIC}/")).status_code == httpx.codes.NOT_FOUND
