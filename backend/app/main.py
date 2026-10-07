import logging

from fastapi import FastAPI

from app.api import auth, health, knowledge, candidates, jobs, jd
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

register_exception_handlers(app)
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(candidates.router, prefix=settings.api_prefix)
app.include_router(candidates.job_router, prefix=settings.api_prefix)
app.include_router(jd.router, prefix=settings.api_prefix)

logger.info("%s started (env=%s)", settings.app_name, settings.app_env)
