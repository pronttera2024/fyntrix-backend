"""
Database Configuration Module
Handles database connection, session management, and initialization
"""
import os
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import Pool
import logging

# Load .env file before reading environment variables
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=_env_path, override=True)

logger = logging.getLogger(__name__)

# Base class for all models
Base = declarative_base()


class DatabaseConfig:
    """Database configuration and connection management"""
    
    def __init__(self):
        self.database_url = self._get_database_url()
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
    def _get_database_url(self) -> str:
        """
        Get database URL from environment variables
        Priority: DATABASE_URL > ARISE_DATABASE_URL > SQLite fallback
        """
        database_url = (
            os.getenv("DATABASE_URL") or
            os.getenv("ARISE_DATABASE_URL") or
            "sqlite:///./fyntrix_local.db"
        )
        
        # Log database type (without exposing credentials)
        if database_url.startswith("postgresql"):
            logger.info("Using PostgreSQL database")
        elif database_url.startswith("sqlite"):
            logger.info("Using SQLite database (local development)")
        else:
            logger.info("Using database: %s", database_url.split("://")[0])
            
        return database_url
    
    def _create_engine(self):
        """Create SQLAlchemy engine with appropriate settings"""
        connect_args = {}
        
        # SQLite-specific settings
        if self.database_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            engine = create_engine(
                self.database_url,
                connect_args=connect_args,
                echo=os.getenv("SQL_ECHO", "false").lower() == "true"
            )
        else:
            # PostgreSQL/RDS settings
            engine = create_engine(
                self.database_url,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=10,  # Connection pool size
                max_overflow=20,  # Max connections beyond pool_size
                pool_recycle=3600,  # Recycle connections after 1 hour
                echo=os.getenv("SQL_ECHO", "false").lower() == "true"
            )
            
            # Add connection pool event listeners for debugging
            @event.listens_for(Pool, "connect")
            def receive_connect(dbapi_conn, connection_record):
                logger.debug("Database connection established")
            
            @event.listens_for(Pool, "checkout")
            def receive_checkout(dbapi_conn, connection_record, connection_proxy):
                logger.debug("Connection checked out from pool")
        
        return engine
    
    def create_tables(self):
        """Create all tables defined in models"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get database session (dependency injection)
        Usage: db: Session = Depends(get_db)
        """
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False


# Singleton instance
_db_config: DatabaseConfig = None


def get_database_config() -> DatabaseConfig:
    """Get or create database configuration singleton"""
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
    return _db_config


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions
    
    Usage in routes:
    @router.get("/users")
    def get_users(db: Session = Depends(get_db)):
        return db.query(User).all()
    """
    db_config = get_database_config()
    yield from db_config.get_session()


def init_database():
    """Initialize database - create tables if they don't exist"""
    db_config = get_database_config()
    db_config.create_tables()
    logger.info("Database initialized")


# Export commonly used items
__all__ = [
    "Base",
    "DatabaseConfig",
    "get_database_config",
    "get_db",
    "init_database"
]
