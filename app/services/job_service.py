import uuid
from typing import Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.exceptions.custom_exceptions import (
    BatchSizeExceededError,
    InvalidBatchError,
    JobNotFoundError,
)
from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.repositories.job_repository import JobRepository
from app.repositories.recipient_repository import RecipientRepository
from app.schemas.job import JobResultsResponse, JobStatusResponse
from app.schemas.recipient import RecipientResultItem
from app.services.validation_service import ValidationService


class JobService:
    """Orchestrates job lifecycle: creation, validation, status tracking, and results retrieval."""

    def __init__(self, db: Session):
        self.db = db
        self.job_repo = JobRepository(db)
        self.recipient_repo = RecipientRepository(db)

    def create_bulk_job(
        self,
        raw_recipients: list[dict[str, Any]],
    ) -> tuple[GenerationJob, int, int]:
        """
        Creates a new GenerationJob, validates individual recipient payloads,
        persists valid and invalid recipients, and commits the transaction.

        Returns:
            (job, valid_count, invalid_count)
        """
        if not raw_recipients:
            raise InvalidBatchError("Recipients list cannot be empty.")

        if len(raw_recipients) > settings.MAX_BATCH_SIZE:
            raise BatchSizeExceededError(len(raw_recipients), settings.MAX_BATCH_SIZE)

        job_id = uuid.uuid4()
        total_count = len(raw_recipients)

        # 1. Create GenerationJob entity
        job = GenerationJob(
            id=job_id,
            status=JobStatus.QUEUED,
            total_count=total_count,
            successful_count=0,
            failed_count=0,
        )
        self.job_repo.create(job)

        # 2. Partition recipients into valid (PENDING) and invalid (INVALID)
        valid_recipients, invalid_recipients = ValidationService.partition_recipients(
            raw_recipients,
            job_id=job_id,
        )

        # 3. Persist all recipients in one atomic transaction
        all_recipients: list[Recipient] = valid_recipients + invalid_recipients
        self.recipient_repo.create_all(all_recipients)

        self.db.commit()
        self.db.refresh(job)

        logger.info(
            "Created job %s: total=%d, valid=%d, invalid=%d",
            job.id,
            total_count,
            len(valid_recipients),
            len(invalid_recipients),
        )

        return job, len(valid_recipients), len(invalid_recipients)

    def get_job_status(self, job_id: uuid.UUID) -> JobStatusResponse:
        """Retrieves real-time persisted progress and counts for a job."""
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(str(job_id))

        stats = self.job_repo.get_persisted_progress_stats(job_id)
        total = stats["total"]
        successful = stats["successful"]
        failed = stats["failed"]
        invalid = stats["invalid"]
        pending = stats["pending"] + stats["processing"]

        # Calculate progress strictly based on persisted records
        processed_count = successful + failed + invalid
        progress_percentage = round((processed_count / total * 100.0), 2) if total > 0 else 100.0

        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            total=total,
            successful=successful,
            failed=failed,
            invalid=invalid,
            pending=pending,
            progress_percentage=progress_percentage,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    def get_job_results(self, job_id: uuid.UUID) -> JobResultsResponse:
        """Retrieves the generation outcomes for every recipient in a job."""
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(str(job_id))

        recipients = self.recipient_repo.get_all_by_job_id(job_id)
        result_items: list[RecipientResultItem] = []

        for r in recipients:
            cert_id = r.certificate.id if r.certificate else None
            download_url = f"/api/v1/certificates/{cert_id}" if cert_id else None
            result_items.append(
                RecipientResultItem(
                    recipient_id=r.id,
                    name=r.name,
                    status=r.status,
                    certificate_id=cert_id,
                    download_url=download_url,
                    error=r.error_message,
                )
            )

        return JobResultsResponse(
            job_id=job.id,
            results=result_items,
        )
