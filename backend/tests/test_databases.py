"""Databases handed out with their own role, really created on the server."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from grod.databases import postgres
from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

DATABASES = f"{API_PREFIX}/databases"
DATABASE_NAME = "shop"


@pytest.fixture
async def database(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    del account
    response = await client.post(DATABASES, json={"name": DATABASE_NAME})
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    yield created
    # Every test leaves the server as it found it.
    await client.delete(f"{DATABASES}/{DATABASE_NAME}")


def test_only_identifiers_the_platform_builds_are_accepted() -> None:
    assert postgres._checked("grod_db_abc123") == "grod_db_abc123"

    for wrong in ('a"b', "drop table users", "grod-db", "", "1abc"):
        with pytest.raises(postgres.InvalidIdentifierError):
            postgres._checked(wrong)


async def test_a_database_is_really_created_and_can_be_used(
    client: httpx.AsyncClient, database: dict[str, Any]
) -> None:
    assert database["databaseName"].startswith("grod_db_")
    assert database["roleName"].startswith("grod_user_")

    connection = await client.get(f"{DATABASES}/{DATABASE_NAME}/connection")
    url = connection.json()["url"]
    assert connection.json()["password"] != ""

    # The address really works: connect with it and write something.
    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://"))
    try:
        async with engine.begin() as own:
            await own.execute(sqlalchemy.text("CREATE TABLE products (name text)"))
            await own.execute(sqlalchemy.text("INSERT INTO products VALUES ('honey')"))
        async with engine.connect() as own:
            result = await own.execute(sqlalchemy.text("SELECT name FROM products"))
            assert result.scalar_one() == "honey"
    finally:
        await engine.dispose()


async def test_a_new_password_replaces_the_old_one(
    client: httpx.AsyncClient, database: dict[str, Any]
) -> None:
    del database
    before = (await client.get(f"{DATABASES}/{DATABASE_NAME}/connection")).json()["password"]

    rotated = await client.post(f"{DATABASES}/{DATABASE_NAME}/rotate-password")

    assert rotated.status_code == httpx.codes.OK, rotated.text
    assert rotated.json()["password"] != before

    engine = create_async_engine(
        rotated.json()["url"].replace("postgresql://", "postgresql+asyncpg://")
    )
    try:
        async with engine.connect() as own:
            assert (await own.execute(sqlalchemy.text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_the_listing_never_carries_the_password(
    client: httpx.AsyncClient, database: dict[str, Any]
) -> None:
    del database
    listed = await client.get(DATABASES)

    assert [item["name"] for item in listed.json()] == [DATABASE_NAME]
    assert "password" not in listed.text


async def test_a_name_is_taken_only_once_per_account(
    client: httpx.AsyncClient, database: dict[str, Any]
) -> None:
    del database
    again = await client.post(DATABASES, json={"name": DATABASE_NAME})

    assert again.status_code == httpx.codes.CONFLICT


async def test_somebody_elses_database_is_not_visible(
    client: httpx.AsyncClient, database: dict[str, Any]
) -> None:
    del database
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(f"{DATABASES}/{DATABASE_NAME}")).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(DATABASES)).json() == []
    # Signing back in keeps the fixture able to clean up.
    await sign_in(client, email="anna.k@grod.dev", password="correct-horse-battery")


async def test_removing_a_database_takes_it_off_the_server(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    created = await client.post(DATABASES, json={"name": "to-delete"})
    name = created.json()["databaseName"]

    removed = await client.delete(f"{DATABASES}/to-delete")

    assert removed.status_code == httpx.codes.NO_CONTENT
    assert await postgres.size_of(name) == 0, "the database is gone from the server"
