"""Start the local-only ASGI server with explicitly selected settings."""

import argparse
import logging
from pathlib import Path

import uvicorn

from sales_manager_api.app import create_app
from sales_manager_api.settings import ConfigurationError, load_settings


def port_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return number


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local sales manager HTTP API")
    parser.add_argument(
        "--env-file", type=Path, help="Explicit dotenv path; OS env wins"
    )
    parser.add_argument("--port", type=port_number, default=8000)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
    except ConfigurationError as exc:
        parser.error(str(exc))
    logging.basicConfig(
        level=settings.log_level, format="%(levelname)s %(name)s %(message)s"
    )
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=args.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
