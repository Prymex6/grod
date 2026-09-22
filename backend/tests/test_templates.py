"""Putting something out for everybody, and taking it as your own."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from grod.main import API_PREFIX
from tests.conftest import ACCOUNT_EMAIL, ACCOUNT_PASSWORD
from tests.test_collaboration import sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    SLUG,
    create_project,
    register_other,
    seed_repository,
)

MARKET = f"{API_PREFIX}/market"
TEMPLATE = "api-template"


@pytest.fixture
async def template(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A project with code in it, put out as a template."""
    del account
    project = await create_project(client)
    await seed_repository(project["id"], tmp_path / "work")

    response = await client.post(
        MARKET,
        json={
            "slug": TEMPLATE,
            "title": "API template",
            "description": "A starting point for a new API.",
            "kind": "template",
            "owner": "anna.k",
            "project": SLUG,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_what_stands_on_the_fair_is_visible_to_everybody(
    client: httpx.AsyncClient, template: dict[str, Any]
) -> None:
    del template
    # A visitor with no account at all still sees the catalog.
    client.cookies.clear()
    listed = await client.get(MARKET)

    assert listed.status_code == httpx.codes.OK, listed.text
    assert [item["slug"] for item in listed.json()] == [TEMPLATE]
    assert listed.json()[0]["author"] == "anna.k"
    assert listed.json()[0]["taken"] == 0


async def test_a_template_becomes_a_project_of_the_taker(
    client: httpx.AsyncClient, template: dict[str, Any]
) -> None:
    del template
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    taken = await client.post(
        f"{MARKET}/{TEMPLATE}/take-template",
        json={"slug": "my-api", "name": "My API"},
    )
    assert taken.status_code == httpx.codes.OK, taken.text
    assert taken.json()["address"] == "piotr.m/my-api"

    # The code really came along, not just the project row.
    file = await client.get(
        f"{API_PREFIX}/projects/piotr.m/my-api/file", params={"path": "README.md"}
    )
    assert file.status_code == httpx.codes.OK, file.text
    assert "Gr" in file.json()["text"]

    # And the fair counts that somebody took it.
    assert (await client.get(f"{MARKET}/{TEMPLATE}")).json()["taken"] == 1


async def test_the_copy_is_the_takers_own_and_the_template_may_go(
    client: httpx.AsyncClient, template: dict[str, Any]
) -> None:
    """Taking something down from the fair must not take away what people made."""
    del template
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    await client.post(
        f"{MARKET}/{TEMPLATE}/take-template", json={"slug": "my-api", "name": "My API"}
    )

    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    removed = await client.delete(f"{MARKET}/{TEMPLATE}")
    assert removed.status_code == httpx.codes.NO_CONTENT

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    still = await client.get(
        f"{API_PREFIX}/projects/piotr.m/my-api/file", params={"path": "README.md"}
    )
    assert still.status_code == httpx.codes.OK


async def test_somebody_elses_project_may_not_be_put_out_as_a_template(
    client: httpx.AsyncClient, template: dict[str, Any]
) -> None:
    del template
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    refused = await client.post(
        MARKET,
        json={
            "slug": "impersonating",
            "title": "Somebody else's",
            "kind": "template",
            "owner": "anna.k",
            "project": SLUG,
        },
    )
    # A private project is not even visible, so it answers like a missing one.
    assert refused.status_code in {httpx.codes.NOT_FOUND, httpx.codes.FORBIDDEN}


async def test_an_application_becomes_a_container_of_the_taker(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    made = await client.post(
        MARKET,
        json={
            "slug": "ready-nginx",
            "title": "Ready-made nginx",
            "kind": "application",
            "image": "nginx:1.27-alpine",
        },
    )
    assert made.status_code == httpx.codes.CREATED, made.text

    taken = await client.post(f"{MARKET}/ready-nginx/take-application", json={"name": "my-nginx"})
    assert taken.status_code == httpx.codes.OK, taken.text

    apps = await client.get(f"{API_PREFIX}/apps")
    assert [item["name"] for item in apps.json()] == ["my-nginx"]
    assert apps.json()[0]["image"] == "nginx:1.27-alpine"
    # Nothing runs yet: taking it describes the application, it does not start it.
    assert apps.json()[0]["state"] == "stopped"


async def test_an_application_needs_an_image_and_a_template_needs_a_project(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    without_image = await client.post(
        MARKET, json={"slug": "no-image", "title": "No image", "kind": "application"}
    )
    assert without_image.status_code == httpx.codes.BAD_REQUEST

    without_project = await client.post(
        MARKET, json={"slug": "no-project", "title": "No project", "kind": "template"}
    )
    assert without_project.status_code == httpx.codes.BAD_REQUEST


async def test_taking_it_off_the_fair_hides_it_from_everybody_but_the_author(
    client: httpx.AsyncClient, template: dict[str, Any]
) -> None:
    del template
    hidden = await client.patch(f"{MARKET}/{TEMPLATE}", params={"published": "false"})
    assert hidden.status_code == httpx.codes.OK, hidden.text

    assert (await client.get(MARKET)).json() == []
    # The author still sees their own, so they can put it back.
    assert [item["slug"] for item in (await client.get(f"{MARKET}/mine")).json()] == [TEMPLATE]
    assert (await client.get(f"{MARKET}/{TEMPLATE}")).status_code == httpx.codes.NOT_FOUND
