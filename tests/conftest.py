"""Shared pytest fixtures for isolated service instances."""

import pytest

from account_service import create_app


@pytest.fixture
def clock() -> list[int]:
    return [1_800_000_000]


@pytest.fixture
def app(tmp_path, clock):
    return create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test-accounts.sqlite3"),
            "SESSION_TTL_SECONDS": 60,
            "ALLOWED_ORIGINS": ["http://localhost:5173"],
            "NOW_FUNCTION": lambda: clock[0],
        }
    )

@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def credentials() -> dict[str, str]:
    return {
        "username": "demo_user",
        "email": "demo@example.test",
        "password": "Example-Passphrase-42!",
    }


def register(client, credentials: dict[str, str]):
    return client.post("/accounts", json=credentials)


def login(client, credentials: dict[str, str]):
    return client.post(
        "/sessions",
        json={
            "username": credentials["username"],
            "password": credentials["password"],
        },
    )
