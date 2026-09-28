"""Background job processing system supporting queued, processing, completed, failed, cancelled states."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BackgroundJob:
    """Represents a background task."""

    def __init__(
        self,
        job_id: str,
        name: str,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.id = job_id
        self.name = name
        self.user_id = user_id
        self.status = JobStatus.QUEUED
        self.progress = 0
        self.result: Any = None
        self.error: Optional[str] = None
        self.retry_count = 0
        self.max_retries = 2
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.metadata = metadata or {}
        self._asyncio_task: Optional[asyncio.Task] = None
        self._cancelled = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "user_id": self.user_id,
            "status": self.status.value,
            "progress": self.progress,
            "error": self.error,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }


class JobManager:
    """In-memory and persistent job manager with retry rules."""

    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = threading.Lock()

    def create_job(
        self,
        name: str,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> BackgroundJob:
        job_id = uuid.uuid4().hex
        job = BackgroundJob(job_id=job_id, name=name, user_id=user_id, metadata=metadata)
        with self._lock:
            self._jobs[job_id] = job
        logger.info("Created background job: %s (%s)", job_id, name)
        return job

    def get_job(self, job_id: str) -> Optional[BackgroundJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, user_id: Optional[str] = None) -> list[BackgroundJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        if user_id:
            jobs = [j for j in jobs if j.user_id == user_id]
        return sorted(jobs, key=lambda x: x.created_at, reverse=True)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                return False
            job.status = JobStatus.CANCELLED
            job._cancelled = True
            job.completed_at = datetime.now(timezone.utc)
            if job._asyncio_task and not job._asyncio_task.done():
                job._asyncio_task.cancel()
        logger.info("Cancelled background job: %s", job_id)
        return True

    async def run_async_job(
        self,
        job: BackgroundJob,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a coroutine function as a tracked background job with retries."""
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

        while True:
            if job._cancelled:
                job.status = JobStatus.CANCELLED
                return None

            try:
                result = await fn(*args, **kwargs)
                job.result = result
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.completed_at = datetime.now(timezone.utc)
                logger.info("Job %s completed successfully", job.id)
                return result
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
                return None
            except (ValueError, TypeError) as exc:
                # Do not retry invalid user inputs
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                logger.warning("Job %s failed with user input error (no retry): %s", job.id, exc)
                return None
            except Exception as exc:
                job.retry_count += 1
                if job.retry_count <= job.max_retries:
                    logger.warning("Job %s failed (attempt %d/%d): %s; retrying...", job.id, job.retry_count, job.max_retries, exc)
                    await asyncio.sleep(1.0 * job.retry_count)
                    continue
                else:
                    job.status = JobStatus.FAILED
                    job.error = str(exc)
                    job.completed_at = datetime.now(timezone.utc)
                    logger.error("Job %s failed permanently: %s", job.id, exc)
                    return None


job_manager = JobManager()
