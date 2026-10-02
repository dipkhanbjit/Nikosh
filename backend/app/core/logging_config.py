import logging
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )
