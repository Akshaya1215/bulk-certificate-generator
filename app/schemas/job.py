import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.models.job import JobStatus
from app.schemas.recipient import RecipientResultItem


class BulkJobCreateRequest(BaseModel):
    """Payload for creating a bulk certificate generation job."""
    recipients: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=settings.MAX_BATCH_SIZE,
        description=f"List of recipient objects (1 to {settings.MAX_BATCH_SIZE} items)",
    )


class JobCreateResponse(BaseModel):
    """Response returned upon successfully creating and queuing a bulk job."""
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: JobStatus
    total: int
    valid: int
    invalid: int


class JobStatusResponse(BaseModel):
    """Response returned when querying the current status of a job."""
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: JobStatus
    total: int
    successful: int
    failed: int
    invalid: int
    pending: int
    progress_percentage: float
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobResultsResponse(BaseModel):
    """Response returned when querying the detailed results of a job."""
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    results: list[RecipientResultItem]
