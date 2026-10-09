"""Shared Neon PostgreSQL helpers used by every dataset worker."""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def get_engine():
    """Create a SQLAlchemy engine from DATABASE_URL in the project's .env file."""
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and paste the team connection string.")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


def read_sql(engine, query: str) -> pd.DataFrame:
    """Run a SELECT query on Neon and return the result as a DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def replace_rows(engine, table: str, df: pd.DataFrame) -> int:
    """Delete all rows of an existing table and insert df in one transaction (keeps table and grants)."""
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table}"))
        df.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=500)
    return len(df)
