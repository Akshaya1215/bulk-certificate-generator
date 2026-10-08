import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CertificateResponse(BaseModel):
    """Schema for certificate metadata."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_id: uuid.UUID
    download_url: str
    created_at: datetime
