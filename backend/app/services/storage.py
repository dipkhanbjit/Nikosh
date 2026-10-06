import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def delete_file(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete file: %s", path)