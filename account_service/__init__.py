"""Build and configure the Flask account service."""

import os
from pathlib import Path

from flask import Flask

from .db import close_database, initialize_database
from .routes import api


DEFAULT_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _positive_int(value: object, setting_name: str) -> int:
    """Read a positive integer setting or raise a clear configuration error."""

    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{setting_name} must be a positive integer") from error
    if number <= 0:
        raise ValueError(f"{setting_name} must be a positive integer")
    return number


def _origins(value: object) -> frozenset[str]:
    """Turn configured browser origins into one exact-match set."""

    if isinstance(value, str):
        candidates = value.split(",")
    else:
        try:
            candidates = list(value)  # type: ignore[arg-type]
        except TypeError as error:
            raise ValueError("ACCOUNT_ALLOWED_ORIGINS must be a string or iterable") from error

    return frozenset(str(origin).strip().rstrip("/") for origin in candidates if str(origin).strip())


def create_app(test_config: dict | None = None) -> Flask:
    """Build one service instance and make sure its SQLite file is ready.

    :param test_config: optional settings used by tests or embedded apps
    :return: configured Flask application
    """

    app = Flask(__name__, instance_relative_config=True)
    default_database = str(Path(app.instance_path) / "accounts.sqlite3")
    app.config.from_mapping(
        DATABASE_PATH=os.getenv("ACCOUNT_DATABASE_PATH", default_database),
        SESSION_TTL_SECONDS=os.getenv("ACCOUNT_SESSION_TTL_SECONDS", "3600"),
        ALLOWED_ORIGINS=os.getenv(
            "ACCOUNT_ALLOWED_ORIGINS",
            ",".join(DEFAULT_ORIGINS),
        ),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    app.config["SESSION_TTL_SECONDS"] = _positive_int(
        app.config["SESSION_TTL_SECONDS"],
        "ACCOUNT_SESSION_TTL_SECONDS",
    )
    app.config["ALLOWED_ORIGINS"] = _origins(app.config["ALLOWED_ORIGINS"])

    database_path = Path(app.config["DATABASE_PATH"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(database_path)

    app.teardown_appcontext(close_database)
    app.register_blueprint(api)

    return app
