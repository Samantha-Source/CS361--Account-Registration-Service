"""Account registration and persistence contract tests."""

import sqlite3

import pytest
from werkzeug.security import check_password_hash

from account_service import create_app

from .conftest import login, register


PASSWORD_WITH_SPACE = "No-Space" + chr(32) + "Allowed-42!"


def database_rows(app, query: str):
    """Read SQLite directly when the HTTP response is not enough evidence."""

    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(query).fetchall()


def test_health_has_exact_contract(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_registration_returns_public_fields_and_stores_a_salted_hash(app, client, credentials):
    response = register(client, credentials)

    assert response.status_code == 201
    body = response.get_json()
    assert body == {
        "account_id": body["account_id"],
        "username": credentials["username"],
        "email": credentials["email"],
    }
    assert body["account_id"].startswith("acct_")
    assert "password" not in body
    assert "password_hash" not in body

    rows = database_rows(
        app,
        "SELECT account_id, username_key, email_key, password_hash FROM accounts",
    )
    assert len(rows) == 1
    assert rows[0]["account_id"] == body["account_id"]
    assert rows[0]["username_key"] == credentials["username"].casefold()
    assert rows[0]["email_key"] == credentials["email"].casefold()
    assert credentials["password"] not in rows[0]["password_hash"]
    assert rows[0]["password_hash"].startswith("scrypt:")
    assert check_password_hash(rows[0]["password_hash"], credentials["password"])


def test_usernames_are_unique_without_regard_to_case(app, client, credentials):
    assert register(client, credentials).status_code == 201
    duplicate = {
        **credentials,
        "username": credentials["username"].upper(),
        "email": "different@example.test",
    }

    response = register(client, duplicate)

    assert response.status_code == 409
    assert response.get_json() == {
        "error": {
            "code": "DUPLICATE_USERNAME",
            "message": "An account already uses that username.",
            "field": "username",
        }
    }
    assert len(database_rows(app, "SELECT account_id FROM accounts")) == 1


def test_emails_are_unique_without_regard_to_case(app, client, credentials):
    assert register(client, credentials).status_code == 201
    duplicate = {
        **credentials,
        "username": "different_user",
        "email": credentials["email"].upper(),
    }

    response = register(client, duplicate)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "DUPLICATE_EMAIL"
    assert response.get_json()["error"]["field"] == "email"
    assert len(database_rows(app, "SELECT account_id FROM accounts")) == 1


@pytest.mark.parametrize(
    ("body", "expected_code", "expected_field"),
    [
        ([], "INVALID_JSON", None),
        ({"email": "demo@example.test", "password": "Example-Passphrase-42!"}, "MISSING_FIELD", "username"),
        ({"username": 42, "email": "demo@example.test", "password": "Example-Passphrase-42!"}, "INVALID_FIELD_TYPE", "username"),
        ({"username": "a!", "email": "demo@example.test", "password": "Example-Passphrase-42!"}, "INVALID_USERNAME", "username"),
        ({"username": "demo_user", "email": "not-an-email", "password": "Example-Passphrase-42!"}, "INVALID_EMAIL", "email"),
        ({"username": "demo_user", "email": "demo@example.test", "password": "short"}, "WEAK_PASSWORD", "password"),
        ({"username": "demo_user", "email": "demo@example.test", "password": PASSWORD_WITH_SPACE}, "WEAK_PASSWORD", "password"),
    ],
)
def test_invalid_registrations_return_structured_400_errors(
    app,
    client,
    body,
    expected_code,
    expected_field,
):
    response = client.post("/accounts", json=body)

    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert error.get("field") == expected_field
    assert database_rows(app, "SELECT account_id FROM accounts") == []


def test_missing_or_malformed_json_returns_structured_400(client):
    missing = client.post("/accounts")
    malformed = client.post(
        "/accounts",
        data='{"username":',
        content_type="application/json",
    )

    for response in (missing, malformed):
        assert response.status_code == 400
        assert response.is_json
        assert response.get_json()["error"]["code"] == "INVALID_JSON"


def test_account_data_persists_across_app_instances(tmp_path, credentials):
    database_path = tmp_path / "persistent.sqlite3"
    first_app = create_app({"TESTING": True, "DATABASE_PATH": str(database_path)})
    first_client = first_app.test_client()
    account_id = register(first_client, credentials).get_json()["account_id"]

    second_app = create_app({"TESTING": True, "DATABASE_PATH": str(database_path)})
    second_client = second_app.test_client()
    response = login(second_client, credentials)

    assert response.status_code == 200
    assert response.get_json()["account_id"] == account_id
