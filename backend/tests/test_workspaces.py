"""A container with the code inside, and work carried back out."""

import asyncio
import io
import tarfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from grod.apps import containers
from grod.main import API_PREFIX
from grod.workspaces import service
from grod.workspaces.models import WORKDIR, Workspace
from tests.test_repositories import SLUG, create_project, seed_repository

WORKSPACES = f"{API_PREFIX}/workspaces"
PROJECT = f"{API_PREFIX}/projects/anna.k/{SLUG}"
NAME = "my-workspace"
# Small enough that the suite does not wait for a download.
TEST_IMAGE = "alpine:3.21"

# The name Git gives to an empty file, which is the same everywhere.
EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

ENGINE_IS_THERE = asyncio.run(containers.available())
needs_engine = pytest.mark.skipif(
    not ENGINE_IS_THERE, reason="this machine has no container engine"
)


def tar_of(files: dict[str, bytes], *, root: str = "workspaces") -> bytes:
    """Build the kind of archive `docker cp` hands over."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for path, content in files.items():
            info = tarfile.TarInfo(f"{root}/{path}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return raw.getvalue()


def test_the_name_of_a_file_is_the_one_git_would_give_it() -> None:
    assert service.blob_name(b"") == EMPTY_BLOB


def test_what_git_keeps_about_itself_never_comes_back() -> None:
    held = service.read_archive(
        tar_of({"main.py": b"print(1)\n", ".git/config": b"[core]\n", "a/.git/x": b"x"})
    )

    assert sorted(held) == ["main.py"]
    assert held["main.py"] == b"print(1)\n"


def test_an_archive_larger_than_a_commit_may_carry_is_refused() -> None:
    too_big = {"big.bin": b"x" * (service.MAX_TOTAL_BYTES + 1)}

    with pytest.raises(service.TooMuchError):
        service.read_archive(tar_of(too_big))


@pytest.fixture
async def workspace(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A project with one commit, and a workspace described over its main branch."""
    del account
    project = await create_project(client)
    await seed_repository(project["id"], tmp_path / "work")

    response = await client.post(
        WORKSPACES,
        json={
            "name": NAME,
            "owner": "anna.k",
            "slug": SLUG,
            "branch": "main",
            "image": TEST_IMAGE,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_a_workspace_is_described_before_anything_runs(
    client: httpx.AsyncClient, workspace: dict[str, Any]
) -> None:
    assert workspace["state"] == "stopped"
    assert workspace["project"] == f"anna.k/{SLUG}"
    assert workspace["branch"] == "main"

    listed = await client.get(WORKSPACES)
    assert [item["name"] for item in listed.json()] == [NAME]


async def test_the_same_name_twice_is_refused(
    client: httpx.AsyncClient, workspace: dict[str, Any]
) -> None:
    del workspace
    again = await client.post(
        WORKSPACES,
        json={"name": NAME, "owner": "anna.k", "slug": SLUG, "branch": "main"},
    )
    assert again.status_code == httpx.codes.CONFLICT


async def test_looking_into_a_workspace_that_does_not_run_says_so(
    client: httpx.AsyncClient, workspace: dict[str, Any]
) -> None:
    del workspace
    answer = await client.get(f"{WORKSPACES}/{NAME}/changes")
    assert answer.status_code == httpx.codes.CONFLICT


@needs_engine
async def test_the_code_goes_in_and_the_work_comes_back(
    client: httpx.AsyncClient, workspace: dict[str, Any]
) -> None:
    """The whole way: start, change something inside, save it as a commit."""
    del workspace
    started = await client.post(f"{WORKSPACES}/{NAME}/start")
    assert started.status_code == httpx.codes.OK, started.text
    assert started.json()["state"] == "running", started.json()["lastError"]

    # Nothing was touched yet, so there is nothing to carry back.
    assert (await client.get(f"{WORKSPACES}/{NAME}/changes")).json() == []

    # Somebody works in the container; the test writes the file the same way.
    read = await client.get(f"{WORKSPACES}/{NAME}")
    container = f"grod-workspaces-{read.json()['id']}"
    await containers.copy_into(
        container,
        archive=tar_of({"src/main.py": b"print('zmienione')\n"}, root="."),
        path=WORKDIR,
    )

    changed = await client.get(f"{WORKSPACES}/{NAME}/changes")
    assert [item["path"] for item in changed.json()] == ["src/main.py"]
    assert changed.json()[0]["removed"] is False

    saved = await client.post(
        f"{WORKSPACES}/{NAME}/save", json={"message": "A change from the workspace"}
    )
    assert saved.status_code == httpx.codes.OK, saved.text
    assert saved.json()["files"] == 1

    file = await client.get(f"{PROJECT}/file", params={"path": "src/main.py"})
    assert file.json()["text"] == "print('zmienione')\n"
    history = await client.get(f"{PROJECT}/commits")
    assert history.json()[0]["subject"] == "A change from the workspace"

    # Saving again with nothing new makes no commit at all.
    again = await client.post(f"{WORKSPACES}/{NAME}/save", json={"message": "Nothing"})
    assert again.json()["files"] == 0

    removed = await client.delete(f"{WORKSPACES}/{NAME}")
    assert removed.status_code == httpx.codes.NO_CONTENT


@needs_engine
async def test_stopping_a_workspace_takes_its_container_with_it(
    client: httpx.AsyncClient, workspace: dict[str, Any]
) -> None:
    del workspace
    await client.post(f"{WORKSPACES}/{NAME}/start")
    stopped = await client.post(f"{WORKSPACES}/{NAME}/stop")

    assert stopped.json()["state"] == "stopped"
    assert (await client.get(f"{WORKSPACES}/{NAME}/changes")).status_code == (httpx.codes.CONFLICT)
    await client.delete(f"{WORKSPACES}/{NAME}")


@needs_engine
async def test_a_container_nothing_points_at_is_swept_away(
    client: httpx.AsyncClient, workspace: dict[str, Any], db_session: AsyncSession
) -> None:
    """Taking a workspace down can fail; the listing clears up what was left."""
    del workspace
    await client.post(f"{WORKSPACES}/{NAME}/start")
    read = await client.get(f"{WORKSPACES}/{NAME}")
    left_behind = f"grod-workspaces-{read.json()['id']}"

    # The row goes without the container, the way a failed removal leaves it.
    await db_session.execute(delete(Workspace))
    await db_session.commit()

    assert (await client.get(WORKSPACES)).json() == []
    assert left_behind not in await containers.names_starting_with("grod-workspaces-")
