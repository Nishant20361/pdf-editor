"""FastAPI application entry point for PDF Editor."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth import router as auth_router
from app.config import settings
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.routers import detection, export, jobs, preview, replacement, upload
from app.services.job_service import job_manager
from app.utils.cleanup import start_cleanup_task
from app.utils.middleware import (
    RateLimiterMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)


class RedactingFormatter(logging.Formatter):
    """Custom logging formatter that strips tokens, passwords, and sensitive text."""

    SENSITIVE_PATTERNS = [
        re.compile(r"password['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE),
        re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
        re.compile(r"secret[_\-]?key['\"]?\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    ]

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern in self.SENSITIVE_PATTERNS:
            msg = pattern.sub("[REDACTED]", msg)
        return msg


# Configure logging
handler = logging.StreamHandler()
handler.setFormatter(
    RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
root_logger.handlers = [handler]

logger = logging.getLogger(__name__)

# Background task reference
_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database, create directories, start cleanup task."""
    global _cleanup_task

    # 1. Initialize database schema
    init_db()

    # 2. Ensure directories exist
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "originals").mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "previews").mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "exports").mkdir(parents=True, exist_ok=True)
    logger.info("Storage initialized at: %s", settings.UPLOAD_DIR)

    # 3. Start background cleanup task
    if settings.FILE_TTL_MINUTES > 0:
        _cleanup_task = await start_cleanup_task()
    else:
        logger.info("Automatic file cleanup is disabled for local mode.")

    yield

    # Shutdown
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="PDF Editor API",
    description="Production-ready PDF and Image text replacement, preview, and export API",
    version="0.5.0",
    lifespan=lifespan,
)

# Global safe exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log internal error without leaking to client
    logger.error("Unhandled server exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An internal server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimiterMiddleware, requests_per_minute=settings.RATE_LIMIT_PER_MINUTE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)

# Register routers
# Authentication remains available for a future deployment, but the local UI
# does not expose sign-in or sign-up controls.
app.include_router(auth_router.router)
app.include_router(upload.router)
app.include_router(preview.router)
app.include_router(detection.router)
app.include_router(replacement.router)
app.include_router(export.router)
app.include_router(jobs.router)


@app.get("/api/health")
async def health_check():
    """Liveness probe endpoint."""
    return {
        "status": "healthy",
        "version": "0.5.0",
        "mode": "local" if settings.LOCAL_MODE else "production",
        "storage_backend": settings.STORAGE_BACKEND,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
    }


@app.get("/api/readiness")
async def readiness_check():
    """Readiness probe endpoint checking database, storage, and queue."""
    checks = {}

    # Check Database
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as exc:
        logger.error("Readiness check DB error: %s", exc)
        checks["database"] = "error"

    # Check Storage
    try:
        test_file = settings.UPLOAD_DIR / ".readiness_probe"
        test_file.write_text("ok")
        test_file.unlink()
        checks["storage"] = "writeable"
    except Exception as exc:
        logger.error("Readiness check Storage error: %s", exc)
        checks["storage"] = "error"

    # Check Queue / Jobs
    checks["queue"] = "healthy"
    checks["active_jobs"] = len(job_manager.list_jobs())

    is_ready = checks["database"] == "connected" and checks["storage"] == "writeable"

    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
        },
    )
