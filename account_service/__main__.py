"""Run the package with ``python -m account_service``."""

import os

from . import create_app


application = create_app()


if __name__ == "__main__":
    application.run(
        host=os.getenv("ACCOUNT_HOST", "127.0.0.1"),
        port=int(os.getenv("ACCOUNT_PORT", "5002")),
        debug=os.getenv("ACCOUNT_DEBUG", "").casefold() == "true",
    )
