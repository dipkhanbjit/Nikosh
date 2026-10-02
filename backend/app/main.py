from fastapi import FastAPI

from app.api import health
from app.core.config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.include_router(health.router, prefix=settings.api_prefix)
