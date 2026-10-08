import uuid
from datetime import date
from typing import Any
from pydantic import ValidationError

from app.models.recipient import Recipient, RecipientStatus
from app.schemas.recipient import RecipientInput


class ValidationService:
    """Validates raw recipient input objects and partitions them into valid and invalid records."""

    @staticmethod
    def partition_recipients(
        raw_recipients: list[dict[str, Any]],
        job_id: uuid.UUID,
    ) -> tuple[list[Recipient], list[Recipient]]:
        """
        Validates individual recipient payloads.
        Returns:
            (valid_recipients, invalid_recipients)
        """
        valid_recipients: list[Recipient] = []
        invalid_recipients: list[Recipient] = []

        for item in raw_recipients:
            recipient_id = uuid.uuid4()
            try:
                # Validate using Pydantic RecipientInput
                validated = RecipientInput.model_validate(item)
                valid_recipient = Recipient(
                    id=recipient_id,
                    job_id=job_id,
                    name=validated.name.strip(),
                    email=validated.email.strip(),
                    event_name=validated.event_name.strip(),
                    completion_date=validated.completion_date,
                    status=RecipientStatus.PENDING,
                    error_message=None,
                )
                valid_recipients.append(valid_recipient)
            except ValidationError as e:
                # Format specific validation error message
                error_msgs = []
                for err in e.errors():
                    field = ".".join(str(loc) for loc in err.get("loc", []))
                    msg = err.get("msg", "Invalid value")
                    error_msgs.append(f"{field}: {msg}" if field else msg)
                error_summary = "; ".join(error_msgs)

                # Extract partial data safely with explicit None fallbacks
                name_val = item.get("name") if isinstance(item, dict) else None
                name = str(name_val or "Unknown").strip()[:255] or "Unknown"

                email_val = item.get("email") if isinstance(item, dict) else None
                email = str(email_val or "invalid@format").strip()[:255] or "invalid@format"

                event_val = item.get("event_name") if isinstance(item, dict) else None
                event_name = str(event_val or "Unknown").strip()[:255] or "Unknown"

                raw_date = item.get("completion_date") if isinstance(item, dict) else None
                try:
                    comp_date = date.fromisoformat(str(raw_date)) if raw_date else date.today()
                except Exception:
                    comp_date = date.today()

                invalid_recipient = Recipient(
                    id=recipient_id,
                    job_id=job_id,
                    name=name,
                    email=email,
                    event_name=event_name,
                    completion_date=comp_date,
                    status=RecipientStatus.INVALID,
                    error_message=error_summary,
                )
                invalid_recipients.append(invalid_recipient)
            except Exception as e:
                # Any other unexpected structure error
                name_val = item.get("name") if isinstance(item, dict) else None
                name = str(name_val or "Unknown").strip()[:255] or "Unknown"

                email_val = item.get("email") if isinstance(item, dict) else None
                email = str(email_val or "invalid@format").strip()[:255] or "invalid@format"

                event_val = item.get("event_name") if isinstance(item, dict) else None
                event_name = str(event_val or "Unknown").strip()[:255] or "Unknown"

                invalid_recipient = Recipient(
                    id=recipient_id,
                    job_id=job_id,
                    name=name,
                    email=email,
                    event_name=event_name,
                    completion_date=date.today(),
                    status=RecipientStatus.INVALID,
                    error_message=f"Invalid recipient data structure: {e}",
                )
                invalid_recipients.append(invalid_recipient)

        return valid_recipients, invalid_recipients
