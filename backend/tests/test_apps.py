"""Describing applications and really running them as containers."""

import asyncio
from typing import Any

import httpx
import pytest

from grod.apps import containers
from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

APPS = f"{API_PREFIX}/apps"
APP_NAME = "my-app"
# Small enough that the test suite does not wait for a download.
TEST_IMAGE = "alpine:3.21"
START_TIMEOUT_SECONDS = 20

# Asked once, while the tests are collected, so every case can skip quickly.
ENGINE_IS_THERE = asyncio.run(containers.available())
needs_engine = pytest.mark.skipif(
    not ENGINE_IS_THERE, reason="this machine has no container engine"
)


@pytest.fixture
async def application(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    response = await client.post(
        APPS,
        json={
            "name": APP_NAME,
            "image": TEST_IMAGE,
            "command": "sleep 300",
            "environment": {"COLOUR": "amber"},
            "memoryMb": 64,
            "cpus": 0.25,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_an_application_starts_out_stopped(
    client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    assert application["state"] == "stopped"
    assert application["environment"] == {"COLOUR": "amber"}
    assert application["hostPort"] is None, "a port is only opened when one is asked for"

    listed = await client.get(APPS)
    assert [item["name"] for item in listed.json()] == [APP_NAME]


async def test_a_name_is_taken_only_once_per_account(
    client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    del application
    again = await client.post(APPS, json={"name": APP_NAME, "image": TEST_IMAGE})
    assert again.status_code == httpx.codes.CONFLICT

    wrong = await client.post(APPS, json={"name": "My app", "image": TEST_IMAGE})
    assert wrong.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_an_application_with_a_port_gets_one_on_the_host(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    created = await client.post(
        APPS, json={"name": "web-service", "image": TEST_IMAGE, "port": 8080}
    )

    assert created.status_code == httpx.codes.CREATED, created.text
    assert created.json()["hostPort"] is not None
    assert created.json()["url"].endswith(str(created.json()["hostPort"]))


async def test_somebody_elses_application_is_not_visible(
    client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    del application
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(f"{APPS}/{APP_NAME}")).status_code == httpx.codes.NOT_FOUND
    assert (await client.post(f"{APPS}/{APP_NAME}/start")).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(APPS)).json() == []


async def test_the_engine_is_reported(client: httpx.AsyncClient, account: dict[str, Any]) -> None:
    del account
    answer = await client.get(f"{APPS}/engine")

    assert answer.status_code == httpx.codes.OK
    assert answer.json()["available"] == ENGINE_IS_THERE


@needs_engine
async def test_an_application_really_runs(
    client: httpx.AsyncClient, application: dict[str, Any]
) -> None:
    """The whole way: start a container, read its log, stop it and remove it."""
    del application
    started = await client.post(f"{APPS}/{APP_NAME}/start")

    assert started.status_code == httpx.codes.OK, started.text
    assert started.json()["state"] == "running", started.json()["lastError"]

    read = await client.get(f"{APPS}/{APP_NAME}")
    assert read.json()["state"] == "running"

    stopped = await client.post(f"{APPS}/{APP_NAME}/stop")
    assert stopped.json()["state"] == "stopped"

    removed = await client.delete(f"{APPS}/{APP_NAME}")
    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(f"{APPS}/{APP_NAME}")).status_code == httpx.codes.NOT_FOUND


@needs_engine
async def test_an_application_that_prints_keeps_its_log(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(
        APPS,
        json={
            "name": "chatty",
            "image": TEST_IMAGE,
            "command": "sh -c 'echo hello-from-apps; sleep 60'",
            "memoryMb": 64,
            "cpus": 0.25,
        },
    )
    await client.post(f"{APPS}/chatty/start")
    await asyncio.sleep(2)

    log = await client.get(f"{APPS}/chatty/logs")

    assert "hello-from-apps" in log.json()["log"]
    await client.delete(f"{APPS}/chatty")


@needs_engine
async def test_an_image_that_does_not_exist_is_reported(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(
        APPS, json={"name": "no-such-image", "image": "grod/no-such-image-anywhere:0.0.1"}
    )

    started = await client.post(f"{APPS}/no-such-image/start")

    assert started.json()["state"] == "failed"
    assert started.json()["lastError"] != "", "the console shows what the engine said"
    await client.delete(f"{APPS}/no-such-image")
