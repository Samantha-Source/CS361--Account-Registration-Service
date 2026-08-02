"""Handle the account and session REST endpoints."""

import hashlib
import secrets
import sqlite3
import time
from uuid import uuid4

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_database
from .validation import ValidationIssue, normalized_key, validate_login, validate_registration


api = Blueprint("api", __name__)
PASSWORD_HASH_METHOD = "scrypt:32768:8:1"
# still do password-hash work when the username is unknown
DUMMY_PASSWORD_HASH = generate_password_hash(
    "Not-A-Real-Account-Password-42!",
    method=PASSWORD_HASH_METHOD,
)


def _now() -> int:
    """Read the current epoch second or the controlled test clock."""

    provider = current_app.config.get("NOW_FUNCTION", time.time)
    return int(provider())


def _error(status: int, code: str, message: str, field: str | None = None) -> tuple[Response, int]:
    """Keep every JSON error in the same client-facing shape."""

    error: dict[str, str] = {"code": code, "message": message}
    if field:
        error["field"] = field
    return jsonify(error=error), status


def _validation_error(issue: ValidationIssue) -> tuple[Response, int]:
    """Turn one validation problem into an HTTP 400 response."""

    return _error(400, issue.code, issue.message, issue.field)


def _json_body() -> object:
    """Read JSON without letting Flask replace our error shape with HTML."""

    return request.get_json(silent=True)


def _token_hash(token: str) -> str:
    """Hash a bearer token before SQLite stores or looks it up."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _bearer_token() -> str | None:
    """Read one bearer token from the Authorization header."""

    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].casefold() != "bearer" or not parts[1]:
        return None
    return parts[1]


def _unauthorized() -> tuple[Response, int]:
    """Use one response for missing, expired, revoked, and unknown tokens."""

    response, status = _error(
        401,
        "UNAUTHORIZED",
        "A valid bearer token is required.",
    )
    response.headers["WWW-Authenticate"] = "Bearer"
    return response, status


def _find_active_account(token: str):
    """Find public account fields only when the session is still active."""

    return get_database().execute(
        """
        SELECT accounts.account_id, accounts.username, accounts.email
        FROM sessions
        JOIN accounts ON accounts.account_id = sessions.account_id
        WHERE sessions.token_hash = ?
          AND sessions.revoked_at IS NULL
          AND sessions.expires_at > ?
        """,
        (_token_hash(token), _now()),
    ).fetchone()


@api.after_app_request
def add_cors_headers(response: Response) -> Response:
    """Add browser permission only for a configured origin."""

    origin = request.headers.get("Origin", "").rstrip("/")
    allowed_origins = current_app.config["ALLOWED_ORIGINS"]
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers.add("Vary", "Origin")
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
    return response


@api.get("/health")
def health() -> tuple[Response, int]:
    """Confirm that the HTTP process is ready."""

    return jsonify(status="ok"), 200


@api.post("/accounts")
def create_account() -> tuple[Response, int]:
    """Create one account after its registration fields pass validation."""

    values, issue = validate_registration(_json_body())
    if issue:
        return _validation_error(issue)
    assert values is not None

    database = get_database()
    username_key = normalized_key(values["username"])
    email_key = normalized_key(values["email"])

    duplicate = database.execute(
        "SELECT username_key, email_key FROM accounts WHERE username_key = ? OR email_key = ?",
        (username_key, email_key),
    ).fetchall()
    if any(row["username_key"] == username_key for row in duplicate):
        return _error(
            409,
            "DUPLICATE_USERNAME",
            "An account already uses that username.",
            "username",
        )
    if any(row["email_key"] == email_key for row in duplicate):
        return _error(
            409,
            "DUPLICATE_EMAIL",
            "An account already uses that email address.",
            "email",
        )

    account_id = f"acct_{uuid4().hex}"
    try:
        database.execute(
            """
            INSERT INTO accounts (
                account_id, username, username_key, email, email_key,
                password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                values["username"],
                username_key,
                values["email"],
                email_key,
                generate_password_hash(values["password"], method=PASSWORD_HASH_METHOD),
                _now(),
            ),
        )
        database.commit()
    except sqlite3.IntegrityError:
        # another request may have inserted the same normalized value first
        database.rollback()
        duplicate = database.execute(
            "SELECT username_key, email_key FROM accounts WHERE username_key = ? OR email_key = ?",
            (username_key, email_key),
        ).fetchall()
        if any(row["username_key"] == username_key for row in duplicate):
            return _error(
                409,
                "DUPLICATE_USERNAME",
                "An account already uses that username.",
                "username",
            )
        return _error(
            409,
            "DUPLICATE_EMAIL",
            "An account already uses that email address.",
            "email",
        )

    return (
        jsonify(
            account_id=account_id,
            username=values["username"],
            email=values["email"],
        ),
        201,
    )


@api.post("/sessions")
def create_session() -> tuple[Response, int]:
    """Check credentials and issue a new opaque bearer token."""

    values, issue = validate_login(_json_body())
    if issue:
        return _validation_error(issue)
    assert values is not None

    database = get_database()
    identifier_field = "username" if "username" in values else "email"
    lookup_query = (
        "SELECT account_id, password_hash FROM accounts WHERE username_key = ?"
        if identifier_field == "username"
        else "SELECT account_id, password_hash FROM accounts WHERE email_key = ?"
    )
    account = database.execute(
        lookup_query,
        (normalized_key(values[identifier_field]),),
    ).fetchone()
    stored_hash = account["password_hash"] if account else DUMMY_PASSWORD_HASH
    password_matches = check_password_hash(stored_hash, values["password"])
    if account is None or not password_matches:
        response, status = _error(
            401,
            "INVALID_CREDENTIALS",
            "Invalid username, email, or password.",
        )
        payload = response.get_json()
        payload["authenticated"] = False
        response.set_data(current_app.json.dumps(payload) + "\n")
        return response, status

    token = secrets.token_urlsafe(32)
    created_at = _now()
    database.execute(
        """
        INSERT INTO sessions (token_hash, account_id, created_at, expires_at, revoked_at)
        VALUES (?, ?, ?, ?, NULL)
        """,
        (
            _token_hash(token),
            account["account_id"],
            created_at,
            created_at + current_app.config["SESSION_TTL_SECONDS"],
        ),
    )
    database.commit()

    return (
        jsonify(
            authenticated=True,
            account_id=account["account_id"],
            session_token=token,
        ),
        200,
    )


@api.get("/accounts/me")
def current_account() -> tuple[Response, int]:
    """Return public account data for one active bearer token."""

    token = _bearer_token()
    if token is None:
        return _unauthorized()
    account = _find_active_account(token)
    if account is None:
        return _unauthorized()
    return (
        jsonify(
            account_id=account["account_id"],
            username=account["username"],
            email=account["email"],
        ),
        200,
    )


@api.post("/sessions/logout")
def logout() -> tuple[Response, int] | Response:
    """Revoke one active bearer token and leave the response body empty."""

    token = _bearer_token()
    if token is None:
        return _unauthorized()

    database = get_database()
    now = _now()
    result = database.execute(
        """
        UPDATE sessions
        SET revoked_at = ?
        WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
        """,
        (now, _token_hash(token), now),
    )
    database.commit()
    if result.rowcount != 1:
        return _unauthorized()
    return Response(status=204)


@api.app_errorhandler(404)
def not_found(_exception: HTTPException) -> tuple[Response, int]:
    """Keep unknown endpoints inside the JSON error contract."""

    return _error(404, "NOT_FOUND", "The requested endpoint does not exist.")


@api.app_errorhandler(405)
def method_not_allowed(_exception: HTTPException) -> tuple[Response, int]:
    """Keep unsupported methods inside the JSON error contract."""

    return _error(405, "METHOD_NOT_ALLOWED", "The HTTP method is not allowed for this endpoint.")


@api.app_errorhandler(413)
def request_too_large(_exception: HTTPException) -> tuple[Response, int]:
    """Reject oversized JSON with the shared error shape."""

    return _error(400, "REQUEST_TOO_LARGE", "The request body is too large.")


@api.app_errorhandler(500)
def internal_error(_exception: HTTPException) -> tuple[Response, int]:
    """Hide internal details while keeping the JSON contract."""

    return _error(500, "INTERNAL_ERROR", "The service could not complete the request.")
