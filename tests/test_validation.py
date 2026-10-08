import uuid
from fastapi.testclient import TestClient
from app.services.validation_service import ValidationService
from app.models.recipient import RecipientStatus


def test_missing_recipients_field(client: TestClient):
    response = client.post("/api/v1/jobs", json={})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_recipients_not_a_list(client: TestClient):
    response = client.post("/api/v1/jobs", json={"recipients": "not-a-list"})
    assert response.status_code == 422


def test_empty_recipients_list(client: TestClient):
    response = client.post("/api/v1/jobs", json={"recipients": []})
    assert response.status_code == 422


def test_batch_size_exceeded(client: TestClient, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "MAX_BATCH_SIZE", 2)

    payload = {
        "recipients": [
            {"name": "User 1", "email": "u1@example.com", "event_name": "Course", "completion_date": "2026-10-07"},
            {"name": "User 2", "email": "u2@example.com", "event_name": "Course", "completion_date": "2026-10-07"},
            {"name": "User 3", "email": "u3@example.com", "event_name": "Course", "completion_date": "2026-10-07"},
        ]
    }
    response = client.post("/api/v1/jobs", json=payload)
    # Exceeds max length constraint in Pydantic schema or JobService
    assert response.status_code in (400, 422)


def test_validation_service_partitioning():
    job_id = uuid.uuid4()
    raw_recipients = [
        # Valid
        {
            "name": "Alice Smith",
            "email": "alice@example.com",
            "event_name": "Python Mastery",
            "completion_date": "2026-10-07",
        },
        # Invalid email
        {
            "name": "Bob Jones",
            "email": "not-an-email",
            "event_name": "Python Mastery",
            "completion_date": "2026-10-07",
        },
        # Empty name
        {
            "name": "   ",
            "email": "charlie@example.com",
            "event_name": "Python Mastery",
            "completion_date": "2026-10-07",
        },
        # Invalid date
        {
            "name": "Diana Prince",
            "email": "diana@example.com",
            "event_name": "Python Mastery",
            "completion_date": "invalid-date",
        },
    ]

    valid, invalid = ValidationService.partition_recipients(raw_recipients, job_id)

    assert len(valid) == 1
    assert valid[0].name == "Alice Smith"
    assert valid[0].status == RecipientStatus.PENDING

    assert len(invalid) == 3
    for inv in invalid:
        assert inv.status == RecipientStatus.INVALID
        assert inv.error_message is not None


def test_mixed_recipients_api_response(client: TestClient):
    payload = {
        "recipients": [
            {
                "name": "Valid Recipient",
                "email": "valid@example.com",
                "event_name": "Backend Bootcamp",
                "completion_date": "2026-10-07",
            },
            {
                "name": "Invalid Email",
                "email": "bad-email-format",
                "event_name": "Backend Bootcamp",
                "completion_date": "2026-10-07",
            },
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["total"] == 2
    assert data["valid"] == 1
    assert data["invalid"] == 1
