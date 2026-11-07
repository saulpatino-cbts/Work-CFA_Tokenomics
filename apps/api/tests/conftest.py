"""Shared test helpers."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def reset_database(engine: Engine) -> None:
    """Wipe the public schema so each database test starts from nothing and migrates fresh.

    Test databases only. Robust to new tables, unlike listing them by name."""
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
