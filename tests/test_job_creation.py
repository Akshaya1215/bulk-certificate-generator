import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.job import GenerationJob
from app.models.recipient import Recipient, RecipientStatus


def test_create_job_successful(client: TestClient, db_session: Session):
    payload = {
        "recipients": [
            {
                "name": "Akshaya K",
                "email": "akshaya@example.com",
                "event_name": "Python Backend Development",
                "completion_date": "2026-10-07",
            },
            {
                "name": "Vivek K K",
                "email": "vivek@example.com",
                "event_name": "Python Backend Development",
                "completion_date": "2026-10-07",
            },
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert "job_id" in data
    job_uuid = uuid.UUID(data["job_id"])
    assert data["total"] == 2
    assert data["valid"] == 2
    assert data["invalid"] == 0

    # Verify records persisted in DB
    job = db_session.get(GenerationJob, job_uuid)
    assert job is not None
    assert job.total_count == 2

    recipients = db_session.query(Recipient).filter(Recipient.job_id == job_uuid).all()
    assert len(recipients) == 2
    for r in recipients:
        assert r.job_id == job_uuid
        assert r.status in (RecipientStatus.PENDING, RecipientStatus.PROCESSING, RecipientStatus.SUCCESS)


def test_create_job_all_invalid(client: TestClient, db_session: Session):
    payload = {
        "recipients": [
            {
                "name": "Invalid One",
                "email": "invalid-email-1",
                "event_name": "Course",
                "completion_date": "2026-10-07",
            },
            {
                "name": "Invalid Two",
                "email": "invalid-email-2",
                "event_name": "Course",
                "completion_date": "2026-10-07",
            },
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert data["total"] == 2
    assert data["valid"] == 0
    assert data["invalid"] == 2
    assert data["status"] == "COMPLETED_WITH_ERRORS"
