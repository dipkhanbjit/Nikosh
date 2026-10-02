from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
