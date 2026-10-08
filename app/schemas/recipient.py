import uuid
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.recipient import RecipientStatus


class RecipientInput(BaseModel):
    """Schema for validating an individual recipient's data."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255, description="Full name of recipient")
    email: EmailStr = Field(..., description="Valid recipient email address")
    event_name: str = Field(..., min_length=1, max_length=255, description="Event or course name")
    completion_date: date = Field(..., description="Date of completion or issuance")


class RecipientResultItem(BaseModel):
    """Schema for recipient results in job results response."""
    model_config = ConfigDict(from_attributes=True)

    recipient_id: uuid.UUID
    name: str
    status: RecipientStatus
    certificate_id: uuid.UUID | None = None
    download_url: str | None = None
    error: str | None = None


class RecipientResponse(BaseModel):
    """Schema for returning recipient details."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    name: str
    email: str
    event_name: str
    completion_date: date
    status: RecipientStatus
    error_message: str | None = None
    created_at: datetime
