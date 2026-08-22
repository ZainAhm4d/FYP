"""
MySQL and PostgreSQL connector — lists tables and fetches table data as DataFrames.

Requires:
  pymysql          — pip install pymysql           (MySQL driver)
  psycopg2-binary  — pip install psycopg2-binary   (Postgres driver)
Both are listed in requirements.txt for Phase 3.
"""
from typing import List
from urllib.parse import quote_plus

import pandas as pd


def _build_url(source_type: str, host: str, port: int,
               username: str, password: str, database: str) -> str:
    """Build a SQLAlchemy connection URL for MySQL or Postgres."""
    u = quote_plus(username)
    p = quote_plus(password)
    if source_type == "mysql":
        return f"mysql+pymysql://{u}:{p}@{host}:{port}/{database}"
    if source_type == "postgres":
        return f"postgresql+psycopg2://{u}:{p}@{host}:{port}/{database}"
    raise ValueError(f"Unsupported source_type: '{source_type}'. Use 'mysql' or 'postgres'.")


def list_tables(
    source_type: str,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
) -> List[str]:
    """
    Return a sorted list of table names for the given database connection.
    Raises ValueError with a user-friendly message on connection failure.
    """
    try:
        from sqlalchemy import create_engine, inspect
    except ImportError:
        raise RuntimeError("sqlalchemy is not installed. Run: pip install sqlalchemy")

    url = _build_url(source_type, host, port, username, password, database)
    connect_args = {"connect_timeout": 10}
    engine = create_engine(url, connect_args=connect_args)
    try:
        with engine.connect():
            tables = inspect(engine).get_table_names()
        return sorted(tables)
    except Exception as exc:
        raise ValueError(f"Could not connect to the database: {exc}")
    finally:
        engine.dispose()


def fetch_table(
    source_type: str,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    table_name: str,
    max_rows: int = 100_000,
) -> pd.DataFrame:
    """
    Fetch a full table from MySQL/Postgres as a DataFrame (capped at max_rows).
    Raises ValueError with a user-friendly message on failure.
    """
    try:
        from sqlalchemy import create_engine
    except ImportError:
        raise RuntimeError("sqlalchemy is not installed. Run: pip install sqlalchemy")

    url = _build_url(source_type, host, port, username, password, database)
    connect_args = {"connect_timeout": 10}
    engine = create_engine(url, connect_args=connect_args)
    try:
        with engine.connect() as conn:
            df = pd.read_sql_table(table_name, conn)
            if len(df) > max_rows:
                df = df.head(max_rows)
        return df
    except Exception as exc:
        raise ValueError(f"Could not fetch table '{table_name}': {exc}")
    finally:
        engine.dispose()
