import uuid
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus


def test_job_not_found(client: TestClient):
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/jobs/{random_id}")
    assert response.status_code == 404
    assert f"Job with ID '{random_id}' not found." in response.json()["detail"]


def test_job_results_not_found(client: TestClient):
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/jobs/{random_id}/results")
    assert response.status_code == 404


def test_job_status_and_progress_calculation(client: TestClient, db_session: Session):
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.PROCESSING,
        total_count=4,
        successful_count=2,
        failed_count=1,
    )
    db_session.add(job)

    # 4 recipients: 2 SUCCESS, 1 FAILED, 1 PENDING
    recipients = [
        Recipient(
            id=uuid.uuid4(),
            job_id=job_id,
            name="User 1",
            email="u1@example.com",
            event_name="Event",
            completion_date=date(2026, 10, 7),
            status=RecipientStatus.SUCCESS,
        ),
        Recipient(
            id=uuid.uuid4(),
            job_id=job_id,
            name="User 2",
            email="u2@example.com",
            event_name="Event",
            completion_date=date(2026, 10, 7),
            status=RecipientStatus.SUCCESS,
        ),
        Recipient(
            id=uuid.uuid4(),
            job_id=job_id,
            name="User 3",
            email="u3@example.com",
            event_name="Event",
            completion_date=date(2026, 10, 7),
            status=RecipientStatus.FAILED,
            error_message="Font rendering failed",
        ),
        Recipient(
            id=uuid.uuid4(),
            job_id=job_id,
            name="User 4",
            email="u4@example.com",
            event_name="Event",
            completion_date=date(2026, 10, 7),
            status=RecipientStatus.PENDING,
        ),
    ]
    db_session.add_all(recipients)
    db_session.commit()

    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["job_id"] == str(job_id)
    assert data["total"] == 4
    assert data["successful"] == 2
    assert data["failed"] == 1
    assert data["pending"] == 1
    # Processed: (2 + 1) / 4 * 100 = 75.0%
    assert data["progress_percentage"] == 75.0


def test_job_results_endpoint(client: TestClient, db_session: Session):
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.COMPLETED_WITH_ERRORS,
        total_count=2,
    )
    db_session.add(job)

    r1 = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Valid Recipient",
        email="valid@example.com",
        event_name="Workshop",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.SUCCESS,
    )
    r2 = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Bad Email Recipient",
        email="bad@email",
        event_name="Workshop",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.INVALID,
        error_message="Invalid email address format",
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    response = client.get(f"/api/v1/jobs/{job_id}/results")
    assert response.status_code == 200
    data = response.json()

    assert data["job_id"] == str(job_id)
    results = data["results"]
    assert len(results) == 2

    res1 = next(r for r in results if r["recipient_id"] == str(r1.id))
    assert res1["status"] == "SUCCESS"
    assert res1["error"] is None

    res2 = next(r for r in results if r["recipient_id"] == str(r2.id))
    assert res2["status"] == "INVALID"
    assert res2["error"] == "Invalid email address format"
    assert res2["certificate_id"] is None
