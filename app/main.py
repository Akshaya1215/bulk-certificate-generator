from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes.certificates import router as certificates_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.exceptions.custom_exceptions import AppException
from app.storage.file_storage import file_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: configure logging and storage
    setup_logging()
    logger.info("Initializing %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    file_storage._ensure_base_dir()
    logger.info("Storage directory verified at: %s", settings.storage_absolute_path)
    yield
    # Shutdown
    logger.info("Shutting down %s...", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-grade bulk certificate generation service. "
        "Accepts bulk recipient payloads, isolates individual failures, "
        "processes PDF generation in the background via Celery/Redis, "
        "and provides real-time status tracking and certificate retrieval."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Include Routers
app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(certificates_router)


# Custom Exception Handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handles domain-specific application exceptions cleanly."""
    logger.warning("Application exception on %s %s: %s (status %d)", request.method, request.url.path, exc.message, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles request payload validation errors cleanly."""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        errors.append(f"{loc}: {msg}" if loc else msg)
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Request validation failed", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches unexpected exceptions, logs traceback, and hides sensitive internals from client."""
    logger.exception("Unhandled server error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact the administrator."},
    )
