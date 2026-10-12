import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, health, knowledge, candidates, jobs, jd, shortlist, interviews
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import setup_logging
from app.services.form_status import form_check_loop
from app.services.screening_runs import mark_interrupted_runs

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mark_interrupted_runs()
    task = asyncio.create_task(form_check_loop())
    logger.info("%s started (env=%s)", settings.app_name, settings.app_env)
    yield
    task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

register_exception_handlers(app)
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(candidates.router, prefix=settings.api_prefix)
app.include_router(candidates.job_router, prefix=settings.api_prefix)
app.include_router(jd.router, prefix=settings.api_prefix)
app.include_router(shortlist.router, prefix=settings.api_prefix)
app.include_router(interviews.router, prefix=settings.api_prefix)
app.include_router(interviews.job_router, prefix=settings.api_prefix)