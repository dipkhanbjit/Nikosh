import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DIR = Path("logs")
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
BACKUP_COUNT = 20


def setup_logging(filename: str = "nikosh.log", console: bool = True) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_DIR / filename, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    handlers = [file_handler]

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    logging.basicConfig(level=settings.log_level.upper(), handlers=handlers, force=True)

    # Uvicorn's own loggers don't propagate to root, so attach the file handler directly
    for name in ("uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addHandler(file_handler)