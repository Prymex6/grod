"""Alembic environment: runs migrations against the configured database."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from grod.accounts import models as brama_models  # noqa: F401  (registers the tables)
from grod.apidocs import models as skryptorium_models  # noqa: F401
from grod.apps import models as osada_models  # noqa: F401
from grod.artifacts import models as skarbiec_models  # noqa: F401
from grod.artifacts.registry import models as registry_models  # noqa: F401
from grod.ci import models as kuznia_models  # noqa: F401
from grod.collaboration import models as collaboration_models  # noqa: F401
from grod.community import models as community_models  # noqa: F401
from grod.config import get_settings
from grod.databases import models as ksiegi_models  # noqa: F401
from grod.db import Base
from grod.errors import models as czujka_models  # noqa: F401
from grod.functions import models as mlyn_models  # noqa: F401
from grod.iam import models as iam_models  # noqa: F401
from grod.monitoring import models as straznica_models  # noqa: F401
from grod.pages import models as witryna_models  # noqa: F401
from grod.queues import models as goniec_models  # noqa: F401
from grod.quotas import models as quotas_models  # noqa: F401
from grod.repositories import models as repository_models  # noqa: F401
from grod.routing import models as drogowskaz_models  # noqa: F401
from grod.scanning import models as zwiad_models  # noqa: F401
from grod.storage import models as spichlerz_models  # noqa: F401
from grod.templates import models as jarmark_models  # noqa: F401
from grod.workspaces import models as warsztat_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", str(get_settings().database_url))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of touching a database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations through an async connection."""
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
