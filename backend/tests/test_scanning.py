"""Finding secrets left in the code, and what happens to them after."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grod.main import API_PREFIX
from grod.repositories import git
from grod.repositories.models import Project
from grod.scanning import rules, service, triggers
from tests.conftest import ACCOUNT_EMAIL, ACCOUNT_PASSWORD
from tests.test_collaboration import OTHER_LOGIN, sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    SLUG,
    create_project,
    register_other,
    run_git,
    seed_repository,
)

FINDINGS = f"{API_PREFIX}/projects/anna.k/{SLUG}/findings"
MEMBERS = f"{API_PREFIX}/projects/anna.k/{SLUG}/members"

# Made up on purpose: the shape is real, the value is not. It may not read like
# a placeholder either, because the scanner leaves those alone.
AWS_KEY = "AKIAQJ7K2M9XPLRT4W6Z"
GROD_TOKEN = "grod_" + "a" * 32 + "_" + "Zm9vYmFyYmF6cXV4MTIzNDU2"
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----"
LEAKED = f"KEY = '{AWS_KEY}'\n"
CLEANED = "KEY = os.environ['KEY']\n"


def test_the_shapes_of_a_secret_are_recognised() -> None:
    found = service.scan_text(f"key = '{AWS_KEY}'", path="deploy.py")
    assert [hit.rule for hit in found] == ["aws-access-key"]

    assert [hit.rule for hit in service.scan_text(PRIVATE_KEY, path="id_rsa")] == ["private-key"]
    assert [hit.rule for hit in service.scan_text(GROD_TOKEN, path="script.sh")] == ["grod-token"]

    url = "DATABASE_URL=postgres://grod:secretpassword@localhost:5432/grod"
    assert [hit.rule for hit in service.scan_text(url, path=".env")] == ["database-url"]


def test_the_value_itself_is_never_written_down() -> None:
    hit = service.scan_text(f"key = '{AWS_KEY}'", path="deploy.py")[0]

    assert AWS_KEY not in hit.snippet
    assert hit.snippet.startswith("key = 'AKIA")
    assert hit.fingerprint == service.fingerprint(AWS_KEY)
    assert AWS_KEY not in hit.fingerprint


def test_a_line_may_ask_to_be_left_alone() -> None:
    assert service.scan_text(f"key = '{AWS_KEY}'  # scanning:ignore", path="a.py") == []
    # An example in a README is not a leak either.
    assert service.scan_text(f"key = '{AWS_KEY}'  # example", path="README.md") == []


def test_generated_files_are_not_looked_through() -> None:
    assert rules.skipped("package-lock.json")
    assert rules.skipped("node_modules/biblioteka/index.js")
    assert rules.skipped("static/app.min.js")
    assert not rules.skipped("src/main.py")


async def write_deploy(project_id: str, work_dir: Path, text: str) -> None:
    """Put deploy.py into the repository of a project and push it."""
    (work_dir / "deploy.py").write_text(text, encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", "Change the deployment", cwd=work_dir)
    await run_git("push", str(git.repository_path(UUID(project_id))), "main", cwd=work_dir)


@pytest.fixture
async def leaky(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> tuple[str, Path]:
    """A project whose repository holds a leaked key, and its working copy."""
    del account
    project = await create_project(client)
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await write_deploy(project["id"], work, LEAKED)
    return str(project["id"]), work


async def test_a_scan_finds_what_was_committed(
    client: httpx.AsyncClient, leaky: tuple[str, Path]
) -> None:
    del leaky
    scanned = await client.post(f"{FINDINGS}/scan")
    assert scanned.status_code == httpx.codes.OK, scanned.text
    assert scanned.json()["opened"] == 1
    assert scanned.json()["openTotal"] == 1

    listed = await client.get(FINDINGS)
    assert [item["rule"] for item in listed.json()] == ["aws-access-key"]
    assert listed.json()[0]["path"] == "deploy.py"
    assert listed.json()[0]["state"] == "open"
    assert AWS_KEY not in listed.text, "the secret never leaves the repository"


async def test_taking_the_secret_out_closes_the_finding(
    client: httpx.AsyncClient, leaky: tuple[str, Path]
) -> None:
    project_id, work = leaky
    await client.post(f"{FINDINGS}/scan")

    await write_deploy(project_id, work, CLEANED)
    again = await client.post(f"{FINDINGS}/scan")

    assert again.json()["closed"] == 1
    assert again.json()["openTotal"] == 0
    assert [item["state"] for item in (await client.get(FINDINGS)).json()] == ["fixed"]


async def test_a_finding_can_be_called_fine_and_stays_that_way(
    client: httpx.AsyncClient, leaky: tuple[str, Path]
) -> None:
    del leaky
    await client.post(f"{FINDINGS}/scan")

    finding_id = (await client.get(FINDINGS)).json()[0]["id"]
    changed = await client.patch(f"{FINDINGS}/{finding_id}", json={"state": "ignored"})
    assert changed.json()["state"] == "ignored"

    # A scan that meets it again leaves the decision alone.
    await client.post(f"{FINDINGS}/scan")
    assert [item["state"] for item in (await client.get(FINDINGS)).json()] == ["ignored"]


async def test_a_moved_branch_brings_the_scan_with_it(
    client: httpx.AsyncClient, db_session: AsyncSession, leaky: tuple[str, Path]
) -> None:
    """Nobody has to remember to ask: the push itself sets the scan going."""
    project_id, _ = leaky
    project = await db_session.get(Project, UUID(project_id))
    assert project is not None
    tip = await git.resolve_ref(project.id, "main")

    # A push that left the default branch where it was changes nothing.
    await triggers.after_push(
        db_session, project=project, before={"main": tip}, after={"main": tip}
    )
    assert (await client.get(FINDINGS)).json() == []

    await triggers.after_push(db_session, project=project, before={}, after={"main": tip})
    listed = await client.get(FINDINGS)
    assert [item["rule"] for item in listed.json()] == ["aws-access-key"]


async def test_somebody_who_may_not_push_is_not_told_where_the_secret_is(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    """Pointing a reader at the line with the password is worse than silence."""
    del account
    await create_project(client)
    await register_other(client)
    # Registering signs the client in as the other account, so come back first.
    await sign_in(client, email=ACCOUNT_EMAIL, password=ACCOUNT_PASSWORD)
    added = await client.post(MEMBERS, json={"login": OTHER_LOGIN, "role": "guest"})
    assert added.status_code == httpx.codes.CREATED, added.text

    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.get(FINDINGS)
    assert refused.status_code == httpx.codes.FORBIDDEN
