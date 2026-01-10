import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _get_database_url() -> str:
    return (
        os.getenv("ARISE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///./arise_local.sqlite3"
    )


engine = create_engine(_get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
