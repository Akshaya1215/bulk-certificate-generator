import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import logger
from app.models.job import JobStatus
from app.schemas.job import (
    BulkJobCreateRequest,
    JobCreateResponse,
    JobResultsResponse,
    JobStatusResponse,
)
from app.services.job_service import JobService
from app.workers.tasks import process_bulk_job

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create bulk certificate generation job",
    description=(
        "Accepts a bulk list of recipient payloads, validates entries, "
        "persists the job and recipients, and enqueues background processing. "
        "Invalid recipients do not prevent valid recipients from being processed."
    ),
)
def create_bulk_job(
    payload: BulkJobCreateRequest,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    job_service = JobService(db)
    job, valid_count, invalid_count = job_service.create_bulk_job(payload.recipients)

    if valid_count > 0:
        # Enqueue background Celery task
        process_bulk_job.delay(str(job.id))
        logger.info("Enqueued Celery background task for job %s", job.id)
    else:
        # If all recipients were invalid, mark completed with errors immediately
        job_service.job_repo.update_status(
            job_id=job.id,
            status=JobStatus.COMPLETED_WITH_ERRORS,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        job.status = JobStatus.COMPLETED_WITH_ERRORS

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total=job.total_count,
        valid=valid_count,
        invalid=invalid_count,
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job processing status",
    description="Returns the real-time progress, persisted counts, and status of a certificate generation job.",
)
def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    job_service = JobService(db)
    return job_service.get_job_status(job_id)


@router.get(
    "/{job_id}/results",
    response_model=JobResultsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job recipient results",
    description="Returns the detailed outcome and certificate download links for every recipient in the job.",
)
def get_job_results(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> JobResultsResponse:
    job_service = JobService(db)
    return job_service.get_job_results(job_id)
