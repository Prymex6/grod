"""Projects, reading a repository, access tokens and Git over HTTP."""

import asyncio
import base64
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from grod.main import API_PREFIX
from grod.repositories import git, ssh_server
from grod.repositories.models import Visibility

PROJECTS = f"{API_PREFIX}/projects"
TOKENS = f"{API_PREFIX}/tokens"
SLUG = "my-project"
OWNER_LOGIN = "anna.k"
OTHER_EMAIL = "piotr.m@grod.dev"
OTHER_PASSWORD = "another-strong-password"
FILE_CONTENT = "Welcome to Grod!\n"


async def run_git(*arguments: str, cwd: Path) -> None:
    """Run git in a working copy; only tests use a worktree."""
    process = await asyncio.create_subprocess_exec(
        "git",
        *arguments,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode(errors="replace")


async def create_project(
    client: httpx.AsyncClient, *, slug: str = SLUG, visibility: str = "private"
) -> dict[str, Any]:
    response = await client.post(
        PROJECTS,
        json={
            "slug": slug,
            "name": "My project",
            "description": "A description",
            "visibility": visibility,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, Any] = response.json()
    return created


async def seed_repository(project_id: str, work_dir: Path) -> str:
    """Put one commit and one tag into the bare repository of a project."""
    bare = git.repository_path(UUID(project_id))
    work_dir.mkdir(parents=True, exist_ok=True)
    await run_git("init", "--initial-branch=main", ".", cwd=work_dir)
    await run_git("config", "user.email", "anna.k@grod.dev", cwd=work_dir)
    await run_git("config", "user.name", "Anna Kowalska", cwd=work_dir)
    (work_dir / "README.md").write_text(FILE_CONTENT, encoding="utf-8")
    (work_dir / "src").mkdir(exist_ok=True)
    (work_dir / "src" / "main.py").write_text("print('grod')\n", encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", "First commit", cwd=work_dir)
    await run_git("tag", "v1.0.0", cwd=work_dir)
    await run_git("push", str(bare), "main", "--tags", cwd=work_dir)
    return str(bare)


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client)


async def register_other(client: httpx.AsyncClient) -> None:
    """Sign the client in as a different account."""
    response = await client.post(
        f"{API_PREFIX}/auth/register",
        json={"email": OTHER_EMAIL, "displayName": "Piotr M", "password": OTHER_PASSWORD},
    )
    assert response.status_code == httpx.codes.CREATED, response.text


async def test_creating_a_project_makes_an_empty_repository(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    created = await create_project(client)

    assert created["empty"] is True
    assert created["defaultBranch"] == "main"
    assert created["cloneUrl"] == f"http://localhost:5173/{OWNER_LOGIN}/{SLUG}.git"
    assert git.repository_path(UUID(created["id"])).exists()


async def test_the_same_address_cannot_be_used_twice(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    duplicate = await client.post(
        PROJECTS, json={"slug": SLUG, "name": "Another", "visibility": "private"}
    )

    assert duplicate.status_code == httpx.codes.CONFLICT


async def test_an_address_with_spaces_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    response = await client.post(
        PROJECTS, json={"slug": "not allowed", "name": "A bad address", "visibility": "private"}
    )

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


async def test_a_private_project_is_invisible_to_others(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)

    response = await client.get(f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}")

    assert response.status_code == httpx.codes.NOT_FOUND, "a private project must look missing"


async def test_a_public_project_is_readable_without_an_account(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await create_project(client, slug="open-source", visibility="public")
    client.cookies.clear()

    response = await client.get(f"{PROJECTS}/{OWNER_LOGIN}/open-source")

    assert response.status_code == httpx.codes.OK
    assert (await client.get(f"{PROJECTS}/explore")).json()[0]["slug"] == "open-source"


async def test_reading_the_repository_after_a_push(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")
    base = f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}"

    tree = await client.get(f"{base}/tree")
    assert tree.status_code == httpx.codes.OK
    assert [entry["name"] for entry in tree.json()] == ["src", "README.md"], "folders come first"

    inner = await client.get(f"{base}/tree", params={"path": "src"})
    assert [entry["path"] for entry in inner.json()] == ["src/main.py"]

    file = await client.get(f"{base}/file", params={"path": "README.md"})
    assert file.json()["text"] == FILE_CONTENT
    assert file.json()["binary"] is False

    commits = await client.get(f"{base}/commits")
    assert [commit["subject"] for commit in commits.json()] == ["First commit"]
    assert commits.json()[0]["authorEmail"] == "anna.k@grod.dev"

    assert [ref["name"] for ref in (await client.get(f"{base}/branches")).json()] == ["main"]
    assert [ref["name"] for ref in (await client.get(f"{base}/tags")).json()] == ["v1.0.0"]
    assert (await client.get(f"{base}")).json()["empty"] is False


async def test_missing_file_and_branch_are_reported(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")
    base = f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}"

    assert (
        await client.get(f"{base}/file", params={"path": "no-such-file.txt"})
    ).status_code == httpx.codes.NOT_FOUND
    assert (
        await client.get(f"{base}/tree", params={"ref": "no-such-branch"})
    ).status_code == httpx.codes.NOT_FOUND


async def test_deleting_a_project_removes_the_repository(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    path = git.repository_path(UUID(project["id"]))

    response = await client.delete(f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}")

    assert response.status_code == httpx.codes.NO_CONTENT
    assert not path.exists()


async def test_tokens_are_created_listed_and_removed(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    created = await client.post(
        TOKENS, json={"name": "Laptop", "scopes": ["repo:read", "repo:write"]}
    )
    assert created.status_code == httpx.codes.CREATED, created.text
    assert created.json()["value"].startswith("grod_")

    listed = await client.get(TOKENS)
    assert [token["name"] for token in listed.json()] == ["Laptop"]
    assert "value" not in listed.text, "the secret is shown only once"

    removed = await client.delete(f"{TOKENS}/{created.json()['id']}")
    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(TOKENS)).json() == []


async def test_a_token_with_an_unknown_scope_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    response = await client.post(TOKENS, json={"name": "Bad", "scopes": ["everything"]})

    assert response.status_code == httpx.codes.BAD_REQUEST


def basic_header(token: str) -> dict[str, str]:
    """Git sends the token as the password of a Basic header."""
    encoded = base64.b64encode(f"git:{token}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


async def make_token(client: httpx.AsyncClient, *, scopes: list[str]) -> str:
    created = await client.post(TOKENS, json={"name": "For cloning", "scopes": scopes})
    assert created.status_code == httpx.codes.CREATED, created.text
    return str(created.json()["value"])


async def test_clone_of_a_private_project_needs_a_token(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")
    token = await make_token(client, scopes=["repo:read"])
    address = f"/{OWNER_LOGIN}/{SLUG}.git/info/refs?service=git-upload-pack"

    # A browser session must not open the Git endpoints: a cookie would let
    # another site push on the account's behalf.
    with_session_only = await client.get(address)
    client.cookies.clear()
    anonymous = await client.get(address)
    with_token = await client.get(address, headers=basic_header(token))

    assert with_session_only.status_code == httpx.codes.UNAUTHORIZED
    assert anonymous.status_code == httpx.codes.UNAUTHORIZED
    assert with_token.status_code == httpx.codes.OK
    assert b"service=git-upload-pack" in with_token.content


async def test_push_needs_a_token_that_may_write(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    read_only = await make_token(client, scopes=["repo:read"])
    writing = await make_token(client, scopes=["repo:read", "repo:write"])
    address = f"/{OWNER_LOGIN}/{SLUG}.git/info/refs?service=git-receive-pack"
    client.cookies.clear()

    refused = await client.get(address, headers=basic_header(read_only))
    allowed = await client.get(address, headers=basic_header(writing))

    assert refused.status_code == httpx.codes.UNAUTHORIZED
    assert allowed.status_code == httpx.codes.OK
    assert b"service=git-receive-pack" in allowed.content


async def test_a_public_project_can_be_cloned_anonymously(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> None:
    del account
    created = await create_project(client, slug="open-source", visibility="public")
    await seed_repository(created["id"], tmp_path / "work")
    client.cookies.clear()

    response = await client.get(f"/{OWNER_LOGIN}/open-source.git/info/refs?service=git-upload-pack")

    assert response.status_code == httpx.codes.OK
    assert b"refs/heads/main" in response.content


async def test_visibility_values_are_the_documented_three() -> None:
    assert [item.value for item in Visibility] == ["private", "internal", "public"]


SSH_KEYS = f"{API_PREFIX}/ssh-keys"
# A throwaway ed25519 public key, generated only for this test suite.
SAMPLE_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ0p9VJTHsQZMTLqGMkCBBsFXDGKrOB7dPbXbF0gQxDF test@grod"
)


async def test_ssh_keys_are_added_listed_and_removed(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    added = await client.post(SSH_KEYS, json={"name": "Laptop", "publicKey": SAMPLE_KEY})
    assert added.status_code == httpx.codes.CREATED, added.text
    assert added.json()["algorithm"] == "ssh-ed25519"
    assert added.json()["fingerprint"].startswith("SHA256:")

    listed = await client.get(SSH_KEYS)
    assert [key["name"] for key in listed.json()] == ["Laptop"]

    removed = await client.delete(f"{SSH_KEYS}/{added.json()['id']}")
    assert removed.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(SSH_KEYS)).json() == []


async def test_the_same_ssh_key_cannot_be_added_twice(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    await client.post(SSH_KEYS, json={"name": "Laptop", "publicKey": SAMPLE_KEY})

    again = await client.post(SSH_KEYS, json={"name": "The same", "publicKey": SAMPLE_KEY})

    assert again.status_code == httpx.codes.CONFLICT


async def test_text_that_is_not_a_key_is_refused(
    client: httpx.AsyncClient, account: dict[str, Any]
) -> None:
    del account
    response = await client.post(
        SSH_KEYS, json={"name": "Rubbish", "publicKey": "this is not a key"}
    )

    assert response.status_code == httpx.codes.BAD_REQUEST


def test_the_ssh_command_of_a_clone_is_understood() -> None:
    service, owner, slug = ssh_server.parse_command("git-upload-pack '/bartek/grod.git'")

    assert (service, owner, slug) == ("git-upload-pack", "bartek", "grod")


def test_the_ssh_command_of_a_push_is_understood() -> None:
    service, owner, slug = ssh_server.parse_command("git-receive-pack 'bartek/grod'")

    assert (service, owner, slug) == ("git-receive-pack", "bartek", "grod")


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "git-upload-pack",
        "git-upload-pack '/bartek'",
        "git-upload-pack '/bartek/grod/extra.git'",
        "",
    ],
)
def test_other_ssh_commands_are_refused(command: str) -> None:
    with pytest.raises(ssh_server.GitCommandError):
        ssh_server.parse_command(command)


async def test_search_finds_lines_in_the_repository(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")
    base = f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}"

    found = await client.get(f"{base}/search", params={"q": "Welcome"})

    assert found.status_code == httpx.codes.OK, found.text
    matches = found.json()
    assert {match["path"] for match in matches} == {"README.md"}
    assert matches[0]["lineNumber"] == 1
    assert "Welcome to Grod" in matches[0]["line"]


async def test_search_ignores_case_and_answers_nothing_when_absent(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    await seed_repository(project["id"], tmp_path / "work")
    base = f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}"

    upper = await client.get(f"{base}/search", params={"q": "WELCOME"})
    missing = await client.get(f"{base}/search", params={"q": "nothing-like-this-here"})

    assert len(upper.json()) == 1, "search ignores case"
    assert missing.json() == []


async def test_search_needs_at_least_two_characters(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    response = await client.get(f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}/search", params={"q": "a"})

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY


PROTECTED = "protected-branches"


async def try_push(*arguments: str, cwd: Path) -> tuple[int, str]:
    """Run git push and return its exit code with what it printed."""
    process = await asyncio.create_subprocess_exec(
        "git",
        "push",
        *arguments,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    return process.returncode or 0, stderr.decode(errors="replace")


async def test_protected_branch_refuses_history_rewrites(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    work = tmp_path / "work"
    bare = await seed_repository(project["id"], work)
    base = f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}"

    protect = await client.post(f"{base}/{PROTECTED}", json={"pattern": "main"})
    assert protect.status_code == httpx.codes.CREATED, protect.text

    # An ordinary commit on top of the branch is still welcome.
    (work / "README.md").write_text("Nowa linia\n", encoding="utf-8")
    await run_git("commit", "-am", "An ordinary change", cwd=work)
    code, _ = await try_push(bare, "main", cwd=work)
    assert code == 0, "a fast-forward push must still work"

    # Rewriting what is already there must be refused.
    await run_git("commit", "--amend", "-m", "Rewritten history", cwd=work)
    code, output = await try_push("--force", bare, "main", cwd=work)
    assert code != 0
    assert "protected" in output

    code, output = await try_push(bare, "--delete", "main", cwd=work)
    assert code != 0
    assert "cannot be deleted" in output


async def test_protection_rules_are_listed_and_dropped(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    work = tmp_path / "work"
    bare = await seed_repository(project["id"], work)
    base = f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}"
    await client.post(f"{base}/{PROTECTED}", json={"pattern": "main"})

    listed = await client.get(f"{base}/{PROTECTED}")
    assert [rule["pattern"] for rule in listed.json()] == ["main"]

    again = await client.post(f"{base}/{PROTECTED}", json={"pattern": "main"})
    assert again.status_code == httpx.codes.CONFLICT

    dropped = await client.delete(f"{base}/{PROTECTED}/main")
    assert dropped.status_code == httpx.codes.NO_CONTENT
    assert (await client.get(f"{base}/{PROTECTED}")).json() == []

    # With the rule gone, a force push goes through again.
    await run_git("commit", "--amend", "-m", "Rewritten again", cwd=work)
    code, output = await try_push("--force", bare, "main", cwd=work)
    assert code == 0, output


async def test_only_the_owner_may_protect_a_branch(
    client: httpx.AsyncClient, project: dict[str, Any]
) -> None:
    del project
    await register_other(client)

    response = await client.post(
        f"{PROJECTS}/{OWNER_LOGIN}/{SLUG}/{PROTECTED}", json={"pattern": "main"}
    )

    assert response.status_code == httpx.codes.NOT_FOUND, "a private project stays hidden"
