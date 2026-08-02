"""Run the Account Registration Service for local development."""

import os

from account_service import create_app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("ACCOUNT_HOST", "127.0.0.1"),
        port=int(os.getenv("ACCOUNT_PORT", "5002")),
        debug=os.getenv("ACCOUNT_DEBUG", "").casefold() == "true",
    )
