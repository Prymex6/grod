"""Test fixtures: a throwaway database and a clean Valkey namespace."""

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.sql import text

TEST_DATABASE = "grod_test"
# Where the services are is a property of the machine, not of the tests, so it
# comes from the environment. The defaults are what infra/docker-compose.yml
# publishes; a build server can point them anywhere.
POSTGRES = os.environ.get("GROD_TEST_POSTGRES", "postgresql+asyncpg://grod:grod@localhost:5433")
TEST_DATABASE_URL = f"{POSTGRES}/{TEST_DATABASE}"
MAINTENANCE_DATABASE_URL = f"{POSTGRES}/postgres"
# Database 15 of Valkey is reserved for tests and flushed before each one.
TEST_VALKEY_URL = os.environ.get("GROD_TEST_VALKEY", "redis://localhost:6380/15")
TABLES = (
    "users",
    "oauth_clients",
    "oauth_grants",
    "passkeys",
    "projects",
    "access_tokens",
    "ssh_keys",
    "protected_branches",
    "project_members",
    "issues",
    "issue_comments",
    "merge_requests",
    "merge_request_comments",
    "merge_queue",
    "required_checks",
    "approvals",
    "project_stars",
    "groups",
    "group_members",
    "runners",
    "pipelines",
    "jobs",
    "job_findings",
    "sites",
    "secrets",
    "packages",
    "container_blobs",
    "container_manifests",
    "container_tags",
    "findings",
    "account_limits",
    "workspaces",
    "offerings",
    "buckets",
    "stored_objects",
    "applications",
    "functions",
    "managed_databases",
    "queues",
    "routes",
    "checks",
    "check_results",
    "error_sources",
    "error_issues",
    "error_reports",
    "api_docs",
    "service_accounts",
    "grants",
)

os.environ["GROD_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["GROD_VALKEY_URL"] = TEST_VALKEY_URL
# Everything the suite writes to disk lives in throwaway directories, so a test
# run never leaves anything in the var/ folder of whoever is working here.
_SCRATCH = Path(tempfile.gettempdir())
os.environ["GROD_REPOSITORIES_PATH"] = str(_SCRATCH / "grod-test-repositories")
os.environ["GROD_PACKAGES_PATH"] = str(_SCRATCH / "grod-test-packages")
os.environ["GROD_REGISTRY_PATH"] = str(_SCRATCH / "grod-test-registry")
os.environ["GROD_STORAGE_PATH"] = str(_SCRATCH / "grod-test-storage")
os.environ["GROD_PAGES_PATH"] = str(_SCRATCH / "grod-test-pages")
# Tests never send email; the captured_emails fixture records it instead.
os.environ["GROD_SMTP_HOST"] = ""
# A throwaway signing key, so tests never touch the instance key.
os.environ["GROD_OIDC_PRIVATE_KEY_PATH"] = str(
    Path(tempfile.gettempdir()) / "grod-test-oidc-key.pem"
)


async def _recreate_test_database() -> None:
    engine = create_async_engine(MAINTENANCE_DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    """Build the schema from the models in a database used only by tests."""
    from grod.accounts import models  # noqa: F401  (registers the tables)
    from grod.accounts.oauth import models as oauth_models  # noqa: F401
    from grod.accounts.passkeys import models as passkey_models  # noqa: F401
    from grod.accounts.sessions import close_client
    from grod.apidocs import models as apidocs_models  # noqa: F401
    from grod.apps import models as apps_models  # noqa: F401
    from grod.artifacts import models as artifacts_models  # noqa: F401
    from grod.artifacts.registry import models as registry_models  # noqa: F401
    from grod.ci import models as ci_models  # noqa: F401
    from grod.collaboration import models as collaboration_models  # noqa: F401
    from grod.community import models as community_models  # noqa: F401
    from grod.databases import models as databases_models  # noqa: F401
    from grod.db import Base, dispose_engine, get_engine
    from grod.errors import models as errors_models  # noqa: F401
    from grod.functions import models as functions_models  # noqa: F401
    from grod.iam import models as iam_models  # noqa: F401
    from grod.monitoring import models as monitoring_models  # noqa: F401
    from grod.pages import models as pages_models  # noqa: F401
    from grod.queues import models as queues_models  # noqa: F401
    from grod.quotas import models as quotas_models  # noqa: F401
    from grod.repositories import models as repository_models  # noqa: F401
    from grod.routing import models as routing_models  # noqa: F401
    from grod.scanning import models as scanning_models  # noqa: F401
    from grod.storage import models as storage_models  # noqa: F401
    from grod.templates import models as templates_models  # noqa: F401
    from grod.workspaces import models as workspaces_models  # noqa: F401

    await _recreate_test_database()
    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()
    await close_client()


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Start every test with empty tables and an empty Valkey database."""
    from grod.accounts.sessions import get_client
    from grod.db import get_engine

    await get_client().flushdb()
    async with get_engine().begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)}"))


ACCOUNT_EMAIL = "anna.k@grod.dev"
ACCOUNT_PASSWORD = "correct-horse-battery"
ACCOUNT_DISPLAY_NAME = "Anna Kowalska"


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session for the tests that go straight to the services."""
    from grod.db import get_session_factory

    async with get_session_factory()() as session:
        yield session


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client wired straight to the application, keeping cookies."""
    from grod.main import create_app

    transport = httpx.ASGITransport(create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as http_client:
        yield http_client


@pytest.fixture
def captured_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Collect the messages that would have been sent."""
    from grod.accounts import password_reset

    sent: list[dict[str, str]] = []

    async def capture(*, to: str, subject: str, body: str) -> None:
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(password_reset, "send_email", capture)
    return sent


@pytest.fixture
async def account(client: httpx.AsyncClient) -> dict[str, object]:
    """A registered account; the client keeps its session cookie."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": ACCOUNT_EMAIL,
            "displayName": ACCOUNT_DISPLAY_NAME,
            "password": ACCOUNT_PASSWORD,
        },
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    created: dict[str, object] = response.json()["account"]
    return created
