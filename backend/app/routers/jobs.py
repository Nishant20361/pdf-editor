"""Job status and management router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user_or_default
from app.db.models import User
from app.services.job_service import job_manager

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("")
async def list_jobs(user: User = Depends(get_current_user_or_default)):
    """List jobs for current user."""
    jobs = job_manager.list_jobs(user_id=user.id)
    return {"jobs": [j.to_dict() for j in jobs]}


@router.get("/{job_id}")
async def get_job(job_id: str, user: User = Depends(get_current_user_or_default)):
    """Get status and details of a background job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "Job not found", "error_code": "NOT_FOUND"})
    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this job")
    return job.to_dict()


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, user: User = Depends(get_current_user_or_default)):
    """Cancel a pending or running background job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "Job not found", "error_code": "NOT_FOUND"})
    if job.user_id and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this job")

    cancelled = job_manager.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=400,
            detail={"error": "Job cannot be cancelled (already completed, failed, or cancelled)", "error_code": "CANNOT_CANCEL"},
        )
    return {"message": "Job cancelled successfully", "job_id": job_id}
