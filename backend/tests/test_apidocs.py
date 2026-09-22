"""API descriptions the platform keeps and reads."""

import json
from typing import Any

import httpx
import pytest

from grod.apidocs import service
from grod.main import API_PREFIX
from tests.test_collaboration import sign_in
from tests.test_repositories import OTHER_EMAIL, OTHER_PASSWORD, register_other

APIS = f"{API_PREFIX}/apis"
DOC_NAME = "shop-api"
DOC = f"{APIS}/{DOC_NAME}"

DOCUMENT = {
    "openapi": "3.1.0",
    "info": {"title": "Shop API", "version": "2.0.0"},
    "paths": {
        "/products": {
            "get": {"summary": "List the products", "tags": ["products"]},
            "post": {"summary": "Add a product", "tags": ["products"]},
        },
        "/basket/{id}": {
            "get": {"summary": "Show the basket", "tags": ["basket"]},
            "parameters": [{"name": "id", "in": "path"}],
        },
    },
}

YAML_DOCUMENT = """openapi: 3.1.0
info:
  title: An API from YAML
  version: 1.0.0
paths:
  /zdrowie:
    get:
      summary: Czy zyje
"""


@pytest.fixture
async def doc(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    response = await client.post(APIS, json={"name": DOC_NAME, "document": json.dumps(DOCUMENT)})
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


def test_a_description_may_be_written_as_yaml() -> None:
    parsed = service.parse_document(YAML_DOCUMENT)

    assert service.describe(parsed) == ("An API from YAML", "1.0.0")
    assert [operation.path for operation in service.operations(parsed)] == ["/zdrowie"]


def test_something_that_is_not_a_description_is_refused() -> None:
    with pytest.raises(service.InvalidDocumentError):
        service.parse_document('{"anything": true}')
    with pytest.raises(service.InvalidDocumentError):
        service.parse_document("this is not a document")


def test_the_parameters_of_a_path_are_not_an_operation() -> None:
    found = service.operations(DOCUMENT)

    methods = {(operation.method, operation.path) for operation in found}
    assert methods == {
        ("GET", "/products"),
        ("POST", "/products"),
        ("GET", "/basket/{id}"),
    }, "the shared parameters entry is not a method"


async def test_a_kept_description_says_what_the_api_does(
    client: httpx.AsyncClient, doc: dict[str, Any]
) -> None:
    assert doc["title"] == "Shop API"
    assert doc["version"] == "2.0.0"
    assert doc["operations"] == 3

    read = await client.get(DOC)
    assert {item["summary"] for item in read.json()["paths"]} == {
        "List the products",
        "Add a product",
        "Show the basket",
    }


async def test_the_document_itself_comes_back(
    client: httpx.AsyncClient, doc: dict[str, Any]
) -> None:
    del doc
    answered = await client.get(f"{DOC}/document")

    assert answered.json()["info"]["title"] == "Shop API"


async def test_a_new_version_replaces_the_old_one(
    client: httpx.AsyncClient, doc: dict[str, Any]
) -> None:
    del doc
    replaced = await client.put(f"{DOC}/document", json={"document": YAML_DOCUMENT})

    assert replaced.status_code == httpx.codes.OK, replaced.text
    assert replaced.json()["title"] == "An API from YAML"
    assert replaced.json()["operations"] == 1


async def test_a_document_that_makes_no_sense_is_refused(
    client: httpx.AsyncClient, doc: dict[str, Any]
) -> None:
    del doc
    refused = await client.put(f"{DOC}/document", json={"document": '{"nic": 1}'})

    assert refused.status_code == httpx.codes.BAD_REQUEST


async def test_a_private_description_stays_private(
    client: httpx.AsyncClient, doc: dict[str, Any]
) -> None:
    del doc
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    assert (await client.get(DOC)).status_code == httpx.codes.NOT_FOUND
    assert (await client.get(APIS)).json() == []


async def test_a_public_description_is_open_to_everybody(
    client: httpx.AsyncClient, doc: dict[str, Any]
) -> None:
    del doc
    opened = await client.patch(DOC, params={"public": "true"})
    assert opened.json()["public"] is True

    client.cookies.clear()
    read = await client.get(DOC)

    assert read.status_code == httpx.codes.OK, "a visitor without an account may read it"
    assert read.json()["title"] == "Shop API"


async def test_a_description_fetched_from_an_address(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    """The platform can describe itself: its own OpenAPI document."""
    del account
    created = await client.post(
        APIS,
        json={
            "name": "sam-grod",
            "document": json.dumps(DOCUMENT),
        },
    )
    assert created.status_code == httpx.codes.CREATED

    # Fetching again only works for a description that has an address.
    refused = await client.post(f"{APIS}/sam-grod/refresh")
    assert refused.status_code == httpx.codes.BAD_GATEWAY
