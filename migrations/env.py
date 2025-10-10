import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object
config = context.config

# Logging uit alembic.ini (optioneel)
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# >>> IMPORTS UIT JOUW APP
from app import create_app, db  # <-- pas aan naar jouw pad

# Maak een Flask app en push context
app = create_app()
app.app_context().push()

# Bepaal DB-URL: voorkeursvolgorde = env var DATABASE_URL -> alembic.ini
db_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Metadata voor autogenerate
target_metadata = db.metadata

def run_migrations_offline():
    """Run migrations zonder DB-verbinding (URL)"""
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
    """Run migrations met echte verbinding (engine)"""
    connectable = db.engine  # werkt nu, want app context is gepusht
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
