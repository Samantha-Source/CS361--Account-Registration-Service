"""Keep SQLite setup and request connections in one place."""

import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    username_key TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    email_key TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER
);

CREATE INDEX IF NOT EXISTS sessions_account_id_idx
    ON sessions (account_id);
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
    ON sessions (expires_at);
"""


def _connect(database_path: str | Path) -> sqlite3.Connection:
    """Open SQLite with named rows, foreign keys, and a short lock wait."""

    connection = sqlite3.connect(str(database_path), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database_path: str | Path) -> None:
    """Create missing tables without clearing existing local account data."""

    with _connect(database_path) as connection:
        connection.executescript(SCHEMA)


def get_database() -> sqlite3.Connection:
    """Reuse one SQLite connection for the current request."""

    if "database" not in g:
        g.database = _connect(current_app.config["DATABASE_PATH"])
    return g.database


def close_database(_error: BaseException | None = None) -> None:
    """Close the request connection when Flask tears down its context."""

    connection = g.pop("database", None)
    if connection is not None:
        connection.close()
