"""Demonstrate the Account Registration Service through real HTTP requests.

This program intentionally imports no service code. Start the Flask service in
another terminal before running it.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

import requests


DEFAULT_SERVICE_URL = "http://127.0.0.1:5002"


def printable_json(value: object) -> str:
    """Format console JSON without showing reusable credentials."""

    if isinstance(value, dict):
        safe = dict(value)
        if "password" in safe:
            safe["password"] = "<redacted>"
        if "session_token" in safe:
            safe["session_token"] = "<received and stored by test program>"
        return json.dumps(safe, indent=2, sort_keys=True)
    return json.dumps(value, indent=2)


def send(
    session: requests.Session,
    method: str,
    url: str,
    *,
    expected_status: int,
    json_body: dict[str, str] | None = None,
    token: str | None = None,
) -> requests.Response:
    """Send one REST request and show what the program receives.

    :raises RuntimeError: if the response status does not match the demo step
    :return: received HTTP response
    """

    print(f"\nREQUEST  {method} {url}")
    if json_body is not None:
        print(printable_json(json_body))
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if token:
        print("Authorization: Bearer <stored session token>")

    response = session.request(
        method,
        url,
        json=json_body,
        headers=headers,
        timeout=5,
    )
    print(f"RECEIVED {response.status_code}")
    if response.content:
        try:
            print(printable_json(response.json()))
        except requests.JSONDecodeError:
            print(response.text)
    else:
        print("<empty response body>")

    if response.status_code != expected_status:
        raise RuntimeError(
            f"Expected HTTP {expected_status}, received HTTP {response.status_code}."
        )
    return response


def run_demo(base_url: str) -> None:
    """Run the full account and session demo against one service URL."""

    unique = f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{uuid4().hex[:6]}"
    username = f"preptrack_{unique}"
    credentials = {
        "username": username,
        "email": f"{username}@example.test",
        "password": "Example-Passphrase-42!",
    }
    root = base_url.rstrip("/")

    with requests.Session() as session:
        send(session, "GET", f"{root}/health", expected_status=200)
        registration = send(
            session,
            "POST",
            f"{root}/accounts",
            expected_status=201,
            json_body=credentials,
        ).json()
        login = send(
            session,
            "POST",
            f"{root}/sessions",
            expected_status=200,
            json_body={
                "username": credentials["username"],
                "password": credentials["password"],
            },
        ).json()
        if login["account_id"] != registration["account_id"]:
            raise RuntimeError("Login returned an unexpected account ID.")

        token = login["session_token"]
        send(
            session,
            "GET",
            f"{root}/accounts/me",
            expected_status=200,
            token=token,
        )
        send(
            session,
            "POST",
            f"{root}/sessions/logout",
            expected_status=204,
            token=token,
        )
        send(
            session,
            "GET",
            f"{root}/accounts/me",
            expected_status=401,
            token=token,
        )

    print("\nPASS: the service responded over HTTP and the logged-out token was rejected.")


def main() -> int:
    """Read command-line settings and return a shell-friendly result code."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("ACCOUNT_SERVICE_URL", DEFAULT_SERVICE_URL),
        help="Account service URL (default: ACCOUNT_SERVICE_URL or %(default)s)",
    )
    arguments = parser.parse_args()

    try:
        run_demo(arguments.base_url)
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as error:
        print(f"\nFAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
