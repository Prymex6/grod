"""Entry point of the Grod platform API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from grod.accounts.oauth.router import discovery_router
from grod.accounts.oauth.router import router as oauth_router
from grod.accounts.passkeys.router import router as passkeys_router
from grod.accounts.router import router as accounts_router
from grod.accounts.sessions import close_client
from grod.apidocs.router import router as apidocs_router
from grod.apps.router import router as apps_router
from grod.artifacts.registry.router import router as registry_router
from grod.artifacts.router import router as artifacts_router
from grod.ci.router import router as ci_router
from grod.ci.router import runner_router
from grod.collaboration import queue_worker
from grod.collaboration.merge_router import router as merge_router
from grod.collaboration.router import router as collaboration_router
from grod.community.group_router import router as groups_router
from grod.community.router import router as community_router
from grod.config import Settings, get_settings
from grod.databases.router import router as databases_router
from grod.db import dispose_engine
from grod.errors.router import report_router
from grod.errors.router import router as errors_router
from grod.functions.router import router as functions_router
from grod.iam.router import router as iam_router
from grod.monitoring import watcher
from grod.monitoring.router import router as monitoring_router
from grod.pages.router import router as pages_router
from grod.pages.router import serving_router
from grod.queues.router import router as queues_router
from grod.quotas.router import router as quotas_router
from grod.repositories.git_router import router as git_router
from grod.repositories.router import router as repositories_router
from grod.routing.router import router as routing_router
from grod.routing.router import traffic_router
from grod.scanning.router import router as scanning_router
from grod.storage.router import router as storage_router
from grod.templates.router import router as templates_router
from grod.workspaces.router import router as workspaces_router

API_PREFIX = "/api/v1"
VERSION = "0.1.0"

SettingsDependency = Annotated[Settings, Depends(get_settings)]


class Health(BaseModel):
    """Answer of the health check used by monitoring and by the frontend."""

    status: Literal["ok"]
    instance: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the background loops while the server lives, and let go afterwards."""
    del app
    watching = watcher.start()
    queueing = queue_worker.start()
    yield
    await queue_worker.stop(queueing)
    await watcher.stop(watching)
    await dispose_engine()
    await close_client()


def create_app() -> FastAPI:
    """Build the API application."""
    settings = get_settings()
    app = FastAPI(
        title="Grod API",
        version=VERSION,
        debug=settings.debug,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    @app.get(f"{API_PREFIX}/health", tags=["platform"])
    async def health(settings: SettingsDependency) -> Health:
        return Health(status="ok", instance=settings.instance_name, version=VERSION)

    app.include_router(accounts_router, prefix=API_PREFIX)
    app.include_router(passkeys_router, prefix=API_PREFIX)
    app.include_router(oauth_router, prefix=API_PREFIX)
    app.include_router(repositories_router, prefix=API_PREFIX)
    app.include_router(collaboration_router, prefix=API_PREFIX)
    app.include_router(merge_router, prefix=API_PREFIX)
    app.include_router(community_router, prefix=API_PREFIX)
    app.include_router(groups_router, prefix=API_PREFIX)
    app.include_router(ci_router, prefix=API_PREFIX)
    app.include_router(runner_router, prefix=API_PREFIX)
    app.include_router(pages_router, prefix=API_PREFIX)
    app.include_router(artifacts_router, prefix=API_PREFIX)
    app.include_router(storage_router, prefix=API_PREFIX)
    app.include_router(apps_router, prefix=API_PREFIX)
    app.include_router(functions_router, prefix=API_PREFIX)
    app.include_router(databases_router, prefix=API_PREFIX)
    app.include_router(queues_router, prefix=API_PREFIX)
    app.include_router(routing_router, prefix=API_PREFIX)
    app.include_router(monitoring_router, prefix=API_PREFIX)
    app.include_router(errors_router, prefix=API_PREFIX)
    app.include_router(apidocs_router, prefix=API_PREFIX)
    app.include_router(iam_router, prefix=API_PREFIX)
    app.include_router(scanning_router, prefix=API_PREFIX)
    app.include_router(quotas_router, prefix=API_PREFIX)
    app.include_router(workspaces_router, prefix=API_PREFIX)
    app.include_router(templates_router, prefix=API_PREFIX)
    app.include_router(report_router, prefix=API_PREFIX)
    app.include_router(traffic_router)
    # Published sites live outside the API prefix, at their own address.
    app.include_router(serving_router)
    # Discovery documents and Git addresses sit at the root of the instance.
    app.include_router(discovery_router)
    # The registry answers under /v2, where the container tools look for it.
    app.include_router(registry_router)
    app.include_router(git_router)
    return app


app = create_app()
