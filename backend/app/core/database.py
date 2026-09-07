"""
Database Configuration
SQLAlchemy setup — supports SQLite (local dev, default) and PostgreSQL
(production, e.g. Supabase) via DATABASE_URL.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Supabase (and Heroku-style hosts) hand out connection strings starting
# with "postgres://", but SQLAlchemy 2.x + psycopg2 require "postgresql://" —
# rewrite it here so pasting a Supabase URL straight into DATABASE_URL just
# works instead of failing with "could not translate host name" style errors.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

_is_sqlite = _db_url.startswith("sqlite")

# check_same_thread=False is SQLite-only (it allows the connection to be used
# across the worker threads FastAPI's threadpool creates); passing it to a
# Postgres/psycopg2 engine raises a TypeError, so it must be conditional.
engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Supabase's pooled connection can silently drop idle connections;
    # pre-ping avoids "server closed the connection unexpectedly" errors on
    # the first request after a period of inactivity. No-op for SQLite.
    pool_pre_ping=not _is_sqlite,
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency to get database session
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
