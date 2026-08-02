"""Authentication, bearer-token, and revocation contract tests."""

import hashlib
import sqlite3

import pytest

from .conftest import login, register


def session_rows(app):
    """Read SQLite directly so tests can inspect stored session data."""

    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT token_hash, account_id, created_at, expires_at, revoked_at FROM sessions"
        ).fetchall()


def authorization(token: str) -> dict[str, str]:
    """Build the bearer header shared by protected-route tests."""

    return {"Authorization": f"Bearer {token}"}


def test_login_is_case_insensitive_and_stores_only_the_token_hash(app, client, credentials):
    registration = register(client, credentials).get_json()
    response = client.post(
        "/sessions",
        json={
            "username": credentials["username"].upper(),
            "password": credentials["password"],
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["authenticated"] is True
    assert body["account_id"] == registration["account_id"]
    assert set(body) == {"authenticated", "account_id", "session_token"}
    assert isinstance(body["session_token"], str)
    assert len(body["session_token"]) >= 40

    rows = session_rows(app)
    assert len(rows) == 1
    expected_hash = hashlib.sha256(body["session_token"].encode("utf-8")).hexdigest()
    assert rows[0]["token_hash"] == expected_hash
    assert rows[0]["token_hash"] != body["session_token"]
    assert rows[0]["expires_at"] - rows[0]["created_at"] == 60


def test_login_accepts_email_without_changing_the_username_flow(client, credentials):
    registration = register(client, credentials).get_json()

    response = client.post(
        "/sessions",
        json={
            "email": credentials["email"].upper(),
            "password": credentials["password"],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["account_id"] == registration["account_id"]
    assert response.get_json()["authenticated"] is True


@pytest.mark.parametrize("username", ["demo_user", "unknown_user"])
def test_bad_credentials_return_generic_401_without_protected_fields(
    client,
    credentials,
    username,
):
    assert register(client, credentials).status_code == 201

    response = client.post(
        "/sessions",
        json={"username": username, "password": "Wrong-Passphrase-42!"},
    )

    assert response.status_code == 401
    body = response.get_json()
    assert body["authenticated"] is False
    assert body["error"]["code"] == "INVALID_CREDENTIALS"
    assert "account_id" not in body
    assert "session_token" not in body


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"username": "demo_user"},
        {"email": "not-an-email", "password": "Example-Passphrase-42!"},
        {
            "username": "demo_user",
            "email": "demo@example.test",
            "password": "Example-Passphrase-42!",
        },
        {"username": "demo_user", "password": 42},
        {"username": "", "password": "Example-Passphrase-42!"},
    ],
)
def test_invalid_login_input_returns_400(client, body):
    response = client.post("/sessions", json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] in {
        "INVALID_JSON",
        "MISSING_FIELD",
        "INVALID_FIELD_TYPE",
        "INVALID_LOGIN_IDENTIFIER",
        "INVALID_USERNAME",
        "INVALID_EMAIL",
    }


def test_active_token_reads_public_account_then_logout_revokes_it(app, client, credentials):
    account = register(client, credentials).get_json()
    token = login(client, credentials).get_json()["session_token"]

    before_logout = client.get("/accounts/me", headers=authorization(token))
    logout_response = client.post("/sessions/logout", headers=authorization(token))
    after_logout = client.get("/accounts/me", headers=authorization(token))
    repeated_logout = client.post("/sessions/logout", headers=authorization(token))

    assert before_logout.status_code == 200
    assert before_logout.get_json() == account
    assert "password" not in before_logout.get_json()
    assert logout_response.status_code == 204
    assert logout_response.data == b""
    assert after_logout.status_code == 401
    assert after_logout.get_json()["error"]["code"] == "UNAUTHORIZED"
    assert repeated_logout.status_code == 401
    assert session_rows(app)[0]["revoked_at"] is not None


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Basic abc123",
        "Bearer",
        "Bearer one two",
        "Bearer unknown-token",
    ],
)
def test_protected_endpoint_rejects_missing_or_invalid_authorization(client, header):
    headers = {} if header is None else {"Authorization": header}

    response = client.get("/accounts/me", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_is_rejected_without_returning_account_data(
    clock,
    client,
    credentials,
):
    assert register(client, credentials).status_code == 201
    token = login(client, credentials).get_json()["session_token"]
    clock[0] += 61

    me_response = client.get("/accounts/me", headers=authorization(token))
    logout_response = client.post("/sessions/logout", headers=authorization(token))

    assert me_response.status_code == 401
    assert "account_id" not in me_response.get_json()
    assert logout_response.status_code == 401


def test_logging_out_one_session_does_not_revoke_another(client, credentials):
    assert register(client, credentials).status_code == 201
    first_token = login(client, credentials).get_json()["session_token"]
    second_token = login(client, credentials).get_json()["session_token"]

    assert first_token != second_token
    assert client.post("/sessions/logout", headers=authorization(first_token)).status_code == 204
    assert client.get("/accounts/me", headers=authorization(first_token)).status_code == 401
    assert client.get("/accounts/me", headers=authorization(second_token)).status_code == 200
