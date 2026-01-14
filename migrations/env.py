import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR_STR = str(BASE_DIR)
if BASE_DIR_STR in sys.path:
    sys.path.remove(BASE_DIR_STR)
sys.path.insert(0, BASE_DIR_STR)

# Load .env file before importing app modules
from dotenv import load_dotenv
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path, override=True)

from app.config.database import Base  # type: ignore
import app.db_models.trading  # noqa: F401
from app.models import User  # noqa: F401

config = context.config

# Load DATABASE_URL from environment (now loaded from .env via dotenv)
# Priority: DATABASE_URL > ARISE_DATABASE_URL > alembic.ini default
_env_db_url = os.getenv("DATABASE_URL") or os.getenv("ARISE_DATABASE_URL")
if _env_db_url:
    config.set_main_option("sqlalchemy.url", _env_db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
