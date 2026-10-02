import logging

from fastapi import FastAPI

from app.api import health
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

register_exception_handlers(app)
app.include_router(health.router, prefix=settings.api_prefix)

logger.info("%s started (env=%s)", settings.app_name, settings.app_env)
