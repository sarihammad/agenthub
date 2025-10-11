"""Server entry point."""

import uvicorn

from agenthub.app import create_app
from agenthub.config import settings


def main() -> None:
    """Run the server."""
    app = create_app()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_config=None,  # Use our custom logging
    )


if __name__ == "__main__":
    main()

