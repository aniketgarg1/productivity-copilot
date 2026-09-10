#!/usr/bin/env python
"""Bring the database schema up to date, then hand off to the app.

Handles three cases:

* fresh database                -> run every migration
* database created by an older
  build's `create_all()`        -> stamp the baseline, then migrate forward
* already under Alembic         -> migrate forward

Run from the backend directory (``python scripts/migrate.py``).
"""

import logging
import sys
import time

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

sys.path.insert(0, ".")

from app.core.config import settings  # noqa: E402
from app.db import models as db_models  # noqa: E402
from app.db.session import engine  # noqa: E402

# Importing the models module is what registers the tables on the metadata.
TARGET_METADATA = db_models.Base.metadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")

# The revision matching the schema the original `create_all()` produced.
BASELINE_REVISION = "32ec80315f74"
LEGACY_TABLE = "google_tokens"


def wait_for_db(attempts: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect():
                return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.info("Waiting for the database (%s/%s)…", attempt, attempts)
            time.sleep(delay)


def schema_matches_models() -> bool:
    """True when the live schema already matches the ORM models exactly."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return not compare_metadata(context, TARGET_METADATA)


def adopt_unstamped_schema(config: Config) -> None:
    """
    Record a version for a database that has tables but no Alembic history.

    Which revision to stamp depends on what the schema actually looks like —
    assuming the baseline breaks when the tables are already current, because
    the outstanding migrations then try to add columns that exist.
    """
    if schema_matches_models():
        logger.info("Existing schema already matches the models — stamping head")
        command.stamp(config, "head")
    else:
        logger.info("Existing pre-Alembic schema found — stamping baseline %s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)


def main() -> int:
    logger.info("Database: %s", settings.DATABASE_URL.split("@")[-1])
    wait_for_db()

    tables = set(inspect(engine).get_table_names())
    config = Config("alembic.ini")

    if "alembic_version" in tables:
        logger.info("Already under Alembic — upgrading to head")
    elif LEGACY_TABLE in tables:
        adopt_unstamped_schema(config)
    else:
        logger.info("Empty database — creating the schema from scratch")

    command.upgrade(config, "head")
    logger.info("Schema is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
