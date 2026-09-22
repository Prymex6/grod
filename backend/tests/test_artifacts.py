"""Secrets of a project and the files it publishes."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from grod.artifacts import crypto, service
from grod.main import API_PREFIX
from tests.test_ci import CONFIG, push_config
from tests.test_collaboration import sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    OWNER_LOGIN,
    SLUG,
    create_project,
    register_other,
    seed_repository,
)

BASE = f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}"
SECRETS = f"{BASE}/secrets"
PACKAGES = f"{BASE}/packages"
RUNNER_API = f"{API_PREFIX}/runner"
SECRET_VALUE = "server-password-12345"


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client)


def test_a_secret_never_lies_in_the_database_in_clear() -> None:
    stored = crypto.encrypt(SECRET_VALUE)

    assert SECRET_VALUE not in stored
    assert crypto.decrypt(stored) == SECRET_VALUE


async def test_the_api_gives_back_names_but_never_values(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    kept = await client.put(
        SECRETS, json={"name": "DEPLOY_TOKEN", "value": SECRET_VALUE, "masked": True}
    )
    assert kept.status_code == httpx.codes.CREATED, kept.text
    assert "value" not in kept.json()

    listed = await client.get(SECRETS)
    assert [item["name"] for item in listed.json()] == ["DEPLOY_TOKEN"]
    assert SECRET_VALUE not in listed.text


async def test_a_secret_is_named_like_a_shell_variable(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    refused = await client.put(SECRETS, json={"name": "no such thing", "value": "x"})

    assert refused.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_writing_a_secret_again_replaces_it(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.put(SECRETS, json={"name": "KEY", "value": "first-value"})
    await client.put(SECRETS, json={"name": "KEY", "value": "second-value"})

    listed = await client.get(SECRETS)
    assert len(listed.json()) == 1, "one name keeps one value"

    removed = await client.delete(f"{SECRETS}/KEY")
    assert removed.status_code == httpx.codes.NO_CONTENT
    assert await client.get(SECRETS) is not None


async def test_a_guest_may_not_see_the_secrets(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await client.put(SECRETS, json={"name": "KEY", "value": SECRET_VALUE})

    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.get(SECRETS)

    assert refused.status_code in {httpx.codes.FORBIDDEN, httpx.codes.NOT_FOUND}


async def test_a_job_takes_the_secrets_as_variables(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_config(work, project["id"], text=CONFIG)
    await client.put(SECRETS, json={"name": "TOKEN", "value": SECRET_VALUE, "masked": True})
    await client.put(
        SECRETS, json={"name": "PROTECTED_ONLY", "value": "protected-secret", "protected": True}
    )
    await client.post(f"{BASE}/pipelines", json={"ref": "main"})

    registered = await client.post(f"{BASE}/runners", json={"name": "runner", "tags": ""})
    headers = {"Authorization": f"Bearer {registered.json()['token']}"}
    job = (await client.post(f"{RUNNER_API}/jobs/request", headers=headers)).json()

    assert job["variables"]["TOKEN"] == SECRET_VALUE, "a job can use the secret"
    assert "PROTECTED_ONLY" not in job["variables"], "main is not protected here"

    # Even when a script prints it, the log shows stars instead.
    await client.patch(
        f"{RUNNER_API}/jobs/{job['id']}",
        json={"log": f"echo {SECRET_VALUE}\n"},
        headers=headers,
    )
    log = await client.get(f"{BASE}/jobs/{job['id']}/log")
    assert SECRET_VALUE not in log.json()["log"]
    assert service.MASK in log.json()["log"]


async def test_a_protected_secret_reaches_a_protected_branch(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_config(work, project["id"], text=CONFIG)
    await client.post(f"{BASE}/protected-branches", json={"pattern": "main"})
    await client.put(
        SECRETS, json={"name": "PROTECTED_ONLY", "value": "protected-secret", "protected": True}
    )
    await client.post(f"{BASE}/pipelines", json={"ref": "main"})

    registered = await client.post(f"{BASE}/runners", json={"name": "runner", "tags": ""})
    headers = {"Authorization": f"Bearer {registered.json()['token']}"}
    job = (await client.post(f"{RUNNER_API}/jobs/request", headers=headers)).json()

    assert job["variables"]["PROTECTED_ONLY"] == "protected-secret"


async def test_a_published_file_comes_back_as_it_went_in(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    content = b"zawartosc paczki\n" * 100
    address = f"{PACKAGES}/tool/1.0.0/tool.tar.gz"

    published = await client.put(address, content=content)
    assert published.status_code == httpx.codes.CREATED, published.text
    assert published.json()["size"] == len(content)

    listed = await client.get(PACKAGES)
    assert [item["filename"] for item in listed.json()] == ["tool.tar.gz"]

    downloaded = await client.get(address)
    assert downloaded.content == content

    removed = await client.delete(f"{PACKAGES}/{published.json()['id']}")
    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(address)).status_code == httpx.codes.NOT_FOUND


async def test_publishing_the_same_address_replaces_the_file(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    address = f"{PACKAGES}/tool/1.0.0/file.txt"
    await client.put(address, content=b"the first version")
    await client.put(address, content=b"the second version")

    listed = await client.get(PACKAGES)
    assert len(listed.json()) == 1

    downloaded = await client.get(address)
    assert downloaded.content == b"the second version"


async def test_a_stranger_may_not_publish(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    refused = await client.put(f"{PACKAGES}/tool/1.0.0/file.txt", content=b"someone elses")

    assert refused.status_code in {httpx.codes.FORBIDDEN, httpx.codes.NOT_FOUND}
