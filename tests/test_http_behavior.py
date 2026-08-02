"""HTTP envelope, CORS, and configuration tests."""

import pytest

from account_service import create_app


def test_allowed_browser_origin_receives_cors_headers(client):
    response = client.options(
        "/accounts",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert "Origin" in response.headers["Vary"]


def test_unconfigured_browser_origin_receives_no_cors_permission(client):
    response = client.get(
        "/health",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.parametrize(
    ("method", "path", "expected_status", "expected_code"),
    [
        ("get", "/does-not-exist", 404, "NOT_FOUND"),
        ("get", "/accounts", 405, "METHOD_NOT_ALLOWED"),
    ],
)
def test_routing_errors_use_the_json_error_envelope(
    client,
    method,
    path,
    expected_status,
    expected_code,
):
    response = getattr(client, method)(path)

    assert response.status_code == expected_status
    assert response.is_json
    assert response.get_json()["error"]["code"] == expected_code
    assert isinstance(response.get_json()["error"]["message"], str)


def test_oversized_body_is_a_structured_400(client):
    response = client.post(
        "/accounts",
        data="x" * (16 * 1024 + 1),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "REQUEST_TOO_LARGE"


@pytest.mark.parametrize("ttl", [0, -1, "not-a-number"])
def test_session_ttl_must_be_a_positive_integer(tmp_path, ttl):
    with pytest.raises(ValueError, match="ACCOUNT_SESSION_TTL_SECONDS"):
        create_app(
            {
                "TESTING": True,
                "DATABASE_PATH": str(tmp_path / "invalid-config.sqlite3"),
                "SESSION_TTL_SECONDS": ttl,
            }
        )


def test_origins_accept_comma_separated_configuration(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "origins.sqlite3"),
            "ALLOWED_ORIGINS": "https://one.example/, https://two.example",
        }
    )

    assert app.config["ALLOWED_ORIGINS"] == frozenset(
        {"https://one.example", "https://two.example"}
    )
