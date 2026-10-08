from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session
import redis

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Health check",
    description="Returns the health status of the API service, database, and Redis broker.",
    responses={
        200: {"description": "All required services are healthy."},
        503: {"description": "One or more required services are degraded."},
    },
)
def health_check(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    is_healthy = True
    health_status: dict[str, str] = {"status": "ok"}

    # Database health check
    try:
        db.execute(text("SELECT 1"))
        health_status["database"] = "healthy"
    except Exception:
        health_status["database"] = "unhealthy"
        is_healthy = False

    # Redis broker health check
    try:
        r = redis.from_url(settings.REDIS_URL, socket_timeout=1.0)
        if r.ping():
            health_status["redis"] = "healthy"
        else:
            health_status["redis"] = "unhealthy"
            if not settings.CELERY_TASK_ALWAYS_EAGER:
                is_healthy = False
    except Exception:
        if settings.CELERY_TASK_ALWAYS_EAGER:
            health_status["redis"] = "skipped (eager mode)"
        else:
            health_status["redis"] = "unhealthy"
            is_healthy = False

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        health_status["status"] = "degraded"

    return health_status
