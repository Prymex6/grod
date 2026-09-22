"""Keeping functions and really running them."""

import asyncio
from typing import Any

import httpx
import pytest

from grod.apps import containers
from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

FUNCTIONS = f"{API_PREFIX}/functions"
FUNCTION_NAME = "greeting"

ENGINE_IS_THERE = asyncio.run(containers.available())
needs_engine = pytest.mark.skipif(
    not ENGINE_IS_THERE, reason="this machine has no container engine"
)


@pytest.fixture
async def function(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    response = await client.post(FUNCTIONS, json={"name": FUNCTION_NAME, "runtime": "python"})
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_a_new_function_starts_with_the_example(
    client: httpx.AsyncClient, function: dict[str, Any]
) -> None:
    assert "json" in function["source"], "the example reads the event and answers"
    assert function["calls"] == 0

    listed = await client.get(FUNCTIONS)
    assert [item["name"] for item in listed.json()] == [FUNCTION_NAME]


async def test_a_name_is_taken_only_once_per_account(
    client: httpx.AsyncClient, function: dict[str, Any]
) -> None:
    del function
    again = await client.post(FUNCTIONS, json={"name": FUNCTION_NAME})
    assert again.status_code == httpx.codes.CONFLICT


async def test_somebody_elses_function_is_not_visible(
    client: httpx.AsyncClient, function: dict[str, Any]
) -> None:
    del function
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(f"{FUNCTIONS}/{FUNCTION_NAME}")).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(FUNCTIONS)).json() == []


async def test_the_code_of_a_function_may_be_changed(
    client: httpx.AsyncClient, function: dict[str, Any]
) -> None:
    del function
    changed = await client.patch(
        f"{FUNCTIONS}/{FUNCTION_NAME}",
        json={"source": "print('a new version')\n", "timeoutSeconds": 5},
    )

    assert changed.status_code == httpx.codes.OK, changed.text
    assert changed.json()["source"] == "print('a new version')\n"
    assert changed.json()["timeoutSeconds"] == 5


@needs_engine
async def test_a_function_answers_what_it_printed(
    client: httpx.AsyncClient, function: dict[str, Any]
) -> None:
    del function
    answered = await client.post(f"{FUNCTIONS}/{FUNCTION_NAME}/call", json={"name": "Bartek"})

    assert answered.status_code == httpx.codes.OK, answered.text
    body = answered.json()
    assert body["ok"] is True, body["error"]
    assert body["answer"] == {"hello": "Bartek"}
    assert body["durationMs"] > 0

    read = await client.get(f"{FUNCTIONS}/{FUNCTION_NAME}")
    assert read.json()["calls"] == 1
    assert read.json()["failures"] == 0


@needs_engine
async def test_a_function_that_breaks_says_why(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(
        FUNCTIONS,
        json={
            "name": "bursting",
            "runtime": "python",
            "source": "raise ValueError('it did not work')\n",
        },
    )

    answered = await client.post(f"{FUNCTIONS}/bursting/call", json={})

    assert answered.json()["ok"] is False
    assert "it did not work" in answered.json()["error"]

    read = await client.get(f"{FUNCTIONS}/bursting")
    assert read.json()["failures"] == 1


@needs_engine
async def test_a_function_that_never_ends_is_cut_short(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(
        FUNCTIONS,
        json={
            "name": "eternal",
            "runtime": "python",
            "source": "import time\ntime.sleep(60)\n",
            "timeoutSeconds": 3,
        },
    )

    answered = await client.post(f"{FUNCTIONS}/eternal/call", json={})

    assert answered.json()["ok"] is False
    assert answered.json()["timedOut"] is True
