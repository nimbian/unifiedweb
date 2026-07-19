"""Structured-ish logging setup.

The Flask app used bare ``print()`` statements. This provides a single
configured logger used across services and the request middleware.
"""

import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers.
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
