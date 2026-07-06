"""FastAPI application for NSX-T/AVI API Gateway."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import v1_router
from app.config import settings
from app.core.allowlist import get_allowlist
from app.core.idempotency import get_idempotency_manager
from app.core.inventory import get_inventory
from app.core.job_tracker import get_job_tracker
from app.middleware.error_handler import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.request_id import RequestIDMiddleware
from app.models.responses import HealthResponse

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Background task for periodic cleanup
async def cleanup_loop():
    """Periodic cleanup of expired jobs and idempotency keys."""
    while True:
        try:
            await asyncio.sleep(settings.job_cleanup_interval_seconds)

            # Cleanup expired jobs
            job_tracker = get_job_tracker()
            removed_jobs = await job_tracker.cleanup_expired(
                settings.job_retention_minutes
            )

            # Cleanup expired idempotency keys
            idempotency_manager = get_idempotency_manager()
            removed_keys = await idempotency_manager.cleanup_expired()

            if removed_jobs > 0 or removed_keys > 0:
                logger.info(
                    f"Cleanup: removed {removed_jobs} jobs, {removed_keys} idempotency keys"
                )

        except Exception as e:
            logger.error(f"Cleanup loop error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting NSX-T/AVI API Gateway")

    # Validate production settings
    issues = settings.validate_production_settings()
    for issue in issues:
        if issue.startswith("CRITICAL"):
            logger.error(issue)
        else:
            logger.warning(issue)

    settings.require_auth_configuration()

    # Load site inventory
    try:
        inventory = get_inventory()
        inventory.load()
        logger.info(f"Loaded {inventory.get_site_count()} sites from inventory")
    except FileNotFoundError:
        logger.warning(
            f"Site inventory file not found: {settings.sites_config_path}. "
            "Create config/sites.yml from config/sites.yml.example"
        )
    except Exception as e:
        logger.error(f"Error loading site inventory: {e}")

    # Load operations allowlist
    try:
        allowlist = get_allowlist()
        allowlist.load()
        logger.info("Loaded operations allowlist configuration")
    except FileNotFoundError:
        logger.warning(
            f"Operations allowlist file not found: {settings.operations_allowlist_path}. "
            "Create config/operations_allowlist.yml from config/operations_allowlist.yml.example"
        )
    except Exception as e:
        logger.error(f"Error loading operations allowlist: {e}")

    # Start background cleanup task
    cleanup_task = asyncio.create_task(cleanup_loop())

    logger.info(
        f"NSX-T/AVI API Gateway started on {settings.host}:{settings.port}"
    )

    yield

    # Shutdown
    logger.info("Shutting down NSX-T/AVI API Gateway")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Multi-site NSX-T and AVI Load Balancer API Gateway with async job tracking, OAuth2 authentication, and operation allowlist enforcement",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware (if origins configured)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)

# Add exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Mount versioned API router
app.include_router(v1_router, prefix="/api")


# Health check endpoint (unauthenticated)
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
    )


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/api/docs",
        "health": "/health",
        "api_version": settings.api_version,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
    )
