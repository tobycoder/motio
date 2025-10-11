import os
import sys
import logging
from pathlib import Path
from logging.config import fileConfig

from alembic import context


# Alembic Config
config = context.config

# Robust logging load (don’t crash if config not found or malformed)
if config.config_file_name:
    cfg_file = config.config_file_name
    if not os.path.isabs(cfg_file):
        alt = Path(__file__).resolve().parent.parent / cfg_file
        if alt.exists():
            cfg_file = str(alt)
    try:
        fileConfig(cfg_file, disable_existing_loggers=False)
    except Exception:
        pass

logger = logging.getLogger("alembic.env")


# Ensure repository root is on sys.path so 'app' can be imported in CI
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import Flask app and DB, push app context
from app import create_app, db  # noqa: E402

app = create_app()


def _configure_sqlalchemy_url():
    with app.app_context():
        db_url = (
            os.getenv("DATABASE_URL")
            or app.config.get("SQLALCHEMY_DATABASE_URI")
            or config.get_main_option("sqlalchemy.url")
        )
        if db_url:
            config.set_main_option("sqlalchemy.url", db_url.replace('%', '%%'))


def _get_metadata():
    with app.app_context():
        return db.metadata


_configure_sqlalchemy_url()
target_metadata = _get_metadata()


def run_migrations_offline():
    """Run migrations zonder DB-verbinding (URL)."""
    with app.app_context():
        url = config.get_main_option("sqlalchemy.url") or db.engine.url.render_as_string(hide_password=False)
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_online():
    """Run migrations met echte verbinding (engine)."""
    with app.app_context():
        connectable = db.engine
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
