"""Publishing a folder of a repository and serving it."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grod.main import API_PREFIX
from grod.pages import service, triggers
from grod.repositories import git, pushes
from grod.repositories import service as projects
from tests.test_collaboration import sign_in
from tests.test_repositories import (
    OTHER_EMAIL,
    OTHER_PASSWORD,
    OWNER_LOGIN,
    SLUG,
    create_project,
    register_other,
    run_git,
    seed_repository,
)

SITE = f"{API_PREFIX}/projects/{OWNER_LOGIN}/{SLUG}/site"
PAGES = f"/-/pages/{OWNER_LOGIN}/{SLUG}"
HOME_PAGE = "<h1>Welcome to Grod</h1>\n"
STYLE = "body { color: #b45309; }\n"
NOT_FOUND_PAGE = "<h1>No such page</h1>\n"


def same_text(served: str, expected: str) -> bool:
    """Compare page text without minding how Git wrote the line endings."""
    return served.replace("\r\n", "\n") == expected


@pytest.fixture
async def project(client: httpx.AsyncClient, account: dict[str, Any]) -> dict[str, Any]:
    del account
    return await create_project(client, visibility="public")


async def push_site(work_dir: Path, project_id: str) -> None:
    """Put a small static site in the public folder of the repository."""
    bare = git.repository_path(UUID(project_id))
    public = work_dir / "public"
    public.mkdir(parents=True, exist_ok=True)
    (public / "index.html").write_text(HOME_PAGE, encoding="utf-8")
    (public / "404.html").write_text(NOT_FOUND_PAGE, encoding="utf-8")
    (public / "style.css").write_text(STYLE, encoding="utf-8")
    (public / "o-nas").mkdir(exist_ok=True)
    (public / "o-nas" / "index.html").write_text("<p>O nas</p>\n", encoding="utf-8")
    await run_git("add", ".", cwd=work_dir)
    await run_git("commit", "-m", "Add a page", cwd=work_dir)
    await run_git("push", str(bare), "main", cwd=work_dir)


@pytest.fixture
async def ready(
    client: httpx.AsyncClient, project: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """A public project with a site set up and published."""
    work = tmp_path / "work"
    await seed_repository(project["id"], work)
    await push_site(work, project["id"])

    configured = await client.put(SITE, json={"branch": "main", "directory": "public"})
    assert configured.status_code == httpx.codes.OK, configured.text
    published = await client.post(f"{SITE}/publish")
    assert published.status_code == httpx.codes.OK, published.text
    return {"project": project, "work": work, "site": published.json()}


async def test_a_published_site_is_served(client: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    assert ready["site"]["publishedCommit"] is not None
    assert ready["site"]["url"].endswith(f"/-/pages/{OWNER_LOGIN}/{SLUG}/")

    home = await client.get(f"{PAGES}/")
    assert home.status_code == httpx.codes.OK, home.text
    assert same_text(home.text, HOME_PAGE)
    assert home.headers["content-type"].startswith("text/html")

    style = await client.get(f"{PAGES}/style.css")
    assert same_text(style.text, STYLE)
    assert style.headers["content-type"].startswith("text/css")

    # A folder is served through its index file.
    about = await client.get(f"{PAGES}/o-nas/")
    assert same_text(about.text, "<p>O nas</p>\n")


async def test_a_missing_page_falls_back_to_the_404_file(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    missing = await client.get(f"{PAGES}/no-such-page.html")

    assert missing.status_code == httpx.codes.OK, "the site answers with its own page"
    assert same_text(missing.text, NOT_FOUND_PAGE)


async def test_a_path_may_not_leave_the_site(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    escaping = await client.get(f"{PAGES}/../../secrets.txt")

    # httpx normalises the path, so the service is asked directly as well.
    assert escaping.status_code in {httpx.codes.NOT_FOUND, httpx.codes.OK}
    assert "secrets" not in escaping.text


def test_the_service_refuses_a_path_that_climbs_out(tmp_path: Path) -> None:
    project_id = UUID("11111111-1111-4111-8111-111111111111")
    root = service.site_path(project_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(HOME_PAGE, encoding="utf-8")
    outside = root.parent / "secrets.txt"
    outside.write_text("secret", encoding="utf-8")

    assert service.resolve_file(project_id, "../secrets.txt") is None
    assert service.resolve_file(project_id, "index.html") is not None


async def test_a_push_publishes_the_site_again(
    client: httpx.AsyncClient, ready: dict[str, Any], db_session: AsyncSession
) -> None:
    work: Path = ready["work"]
    found = await projects.find(db_session, owner_login=OWNER_LOGIN, slug=SLUG)
    assert found is not None

    before = await pushes.branch_tips(found.project)
    (work / "public" / "index.html").write_text("<h1>A new version</h1>\n", encoding="utf-8")
    await run_git("commit", "-am", "Change the page", cwd=work)
    await run_git("push", str(git.repository_path(UUID(ready["project"]["id"]))), "main", cwd=work)
    after = await pushes.branch_tips(found.project)

    published = await triggers.after_push(
        db_session, project=found.project, before=before, after=after
    )

    assert published is True
    home = await client.get(f"{PAGES}/")
    assert same_text(home.text, "<h1>A new version</h1>\n")


async def test_a_site_of_a_private_project_needs_an_account(
    client: httpx.AsyncClient, account: dict[str, Any], tmp_path: Path
) -> None:
    """The site is exactly as visible as the project behind it."""
    del account
    private = await create_project(client, slug="vault", visibility="private")
    work = tmp_path / "work"
    await seed_repository(private["id"], work)
    await push_site(work, private["id"])

    address = f"{API_PREFIX}/projects/{OWNER_LOGIN}/vault/site"
    await client.put(address, json={"branch": "main", "directory": "public"})
    await client.post(f"{address}/publish")

    mine = await client.get(f"/-/pages/{OWNER_LOGIN}/vault/")
    assert mine.status_code == httpx.codes.OK, "the owner sees their own site"

    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)
    refused = await client.get(f"/-/pages/{OWNER_LOGIN}/vault/")

    assert refused.status_code == httpx.codes.NOT_FOUND, "a stranger sees nothing"


async def test_taking_a_site_down_removes_its_files(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    project_id = UUID(ready["project"]["id"])

    removed = await client.delete(SITE)
    assert removed.status_code == httpx.codes.NO_CONTENT

    assert not service.site_path(project_id).exists()
    gone = await client.get(f"{PAGES}/")
    assert gone.status_code == httpx.codes.NOT_FOUND


async def test_a_guest_may_not_set_up_a_site(
    client: httpx.AsyncClient, ready: dict[str, Any]
) -> None:
    del ready
    await register_other(client)
    await sign_in(client, email=OTHER_EMAIL, password=OTHER_PASSWORD)

    refused = await client.put(SITE, json={"branch": "main", "directory": "public"})
    assert refused.status_code == httpx.codes.FORBIDDEN
