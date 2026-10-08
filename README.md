# Bulk Certificate Generator

A production-grade, asynchronous bulk certificate generation backend API built with **Python 3.12+**, **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.x**, **Alembic**, **Celery**, **Redis**, and **ReportLab**.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Key Features](#key-features)
3. [Architecture & System Flow](#architecture--system-flow)
4. [Technology Stack](#technology-stack)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Environment Variables](#environment-variables)
8. [Local Development Setup](#local-development-setup)
9. [Database & Alembic Migrations](#database--alembic-migrations)
10. [Running the Application Locally](#running-the-application-locally)
11. [Running with Docker & Docker Compose](#running-with-docker--docker-compose)
12. [Running Automated Tests](#running-automated-tests)
13. [API Documentation & Endpoints](#api-documentation--endpoints)
14. [Curl Examples & Usage Guide](#curl-examples--usage-guide)
15. [Deep Dive: Architectural & Design Decisions](#deep-dive-architectural--design-decisions)
    - [Why Background Processing?](#why-background-processing)
    - [Why Celery & Redis?](#why-celery--redis)
    - [Why PostgreSQL & SQLAlchemy 2.x?](#why-postgresql--sqlalchemy-2x)
    - [Failure Isolation Guarantee](#failure-isolation-guarantee)
    - [How Progress is Calculated](#how-progress-is-calculated)
    - [Storage Strategy & Path Traversal Security](#storage-strategy--path-traversal-security)
16. [Tradeoffs & Considerations](#tradeoffs--considerations)
17. [Limitations](#limitations)

---

## Project Overview

In education, certification programs, and corporate events, organizations often issue certificates to hundreds or thousands of participants at once. Generating PDFs synchronously within an HTTP request cycle blocks the web server, leads to gateway timeouts (HTTP 504), consumes unbounded memory, and risks total batch failure if a single recipient's data contains an error.

The **Bulk Certificate Generator** solves this with a clean, decoupled architecture:
1. Validates request formatting and individual recipient fields.
2. Persists the job and records valid recipients as `PENDING` and invalid recipients as `INVALID`.
3. Returns an immediate `HTTP 202 Accepted` response with the unique job ID.
4. Offloads PDF generation to asynchronous background workers (Celery) backed by Redis.
5. Employs independent database transaction boundaries per recipient so **a failure in one recipient never interrupts or fails the remaining batch**.
6. Exposes endpoints to track persisted real-time progress, inspect individual recipient outcomes, and securely download generated PDFs.

---

## Key Features

- **Non-blocking Bulk Submissions**: Accepts bulk batches up to 1,000 recipients and responds immediately with `HTTP 202 Accepted`.
- **Fault-Tolerant Recipient Processing**: One invalid email or rendering failure will **never** stop other recipients in the same job from succeeding.
- **Two-Tier Validation**:
  - *Request-Level*: Rejects empty batches, malformed payloads, or oversized batches with `4xx`.
  - *Recipient-Level*: Marks individual entries as `INVALID` with precise error messages while queuing valid recipients.
- **Persisted Progress Tracking**: Real-time progress is computed from persisted database rows, guaranteeing accuracy across worker restarts.
- **Professional PDF Generator**: Generates high-fidelity, landscape A4 certificates using ReportLab with custom typography, accents, and unique certificate identifiers.
- **Secure File Storage**: Organizes files into `generated/<job_id>/<certificate_id>.pdf` with path traversal protections.
- **Full Docker & Compose Support**: Multi-container orchestration encompassing FastAPI, PostgreSQL, Redis, and Celery Worker.
- **Extensive Test Suite**: 21+ automated tests covering edge cases, failure isolation, PDF validity, and full lifecycle integration.

---

## Architecture & System Flow

```
                      +-----------------------------+
                      |         HTTP Client         |
                      +-----------------------------+
                           |                   ^
             POST /api/v1/jobs                 | GET /api/v1/jobs/{id}
                           v                   | GET /api/v1/certificates/{id}
                      +-----------------------------+
                      |       FastAPI Service       |
                      +-----------------------------+
                        /                         \
           Enqueue Job /                           \ Persist Records & Query
                      v                             v
           +--------------------+         +--------------------+
           |    Redis Broker    |         |     PostgreSQL     |
           +--------------------+         +--------------------+
                      |                             ^
             Task Event                             | State Updates &
                      v                             | Cert Metadata
           +--------------------+                   |
           |   Celery Worker    |-------------------+
           +--------------------+
                      |
                      v
           +--------------------+
           |  ReportLab Engine  |
           +--------------------+
                      |
                      v
           +--------------------+
           | Local File Storage | -> generated/<job_id>/<cert_id>.pdf
           +--------------------+
```

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.12+ (3.13 verified) | Modern type hinting, high performance, robust ecosystem |
| **API Framework** | FastAPI + Uvicorn | Async ASGI framework with automatic OpenAPI docs and high throughput |
| **Database** | PostgreSQL 16+ | ACID guarantees, relational integrity, robust indexing, transactional safety |
| **ORM & Migrations**| SQLAlchemy 2.x + Alembic | Modern Mapped columns, type-safe queries, controlled versioned schema migrations |
| **Background Queue**| Celery 5.4+ | Industry standard distributed task worker with robust lifecycle management |
| **Message Broker** | Redis 7+ | In-memory pub/sub broker for low-latency task delivery |
| **PDF Generation** | ReportLab 4.2+ | Production-grade vector PDF rendering without external headless browser overhead |
| **Validation** | Pydantic v2 + Pydantic Settings | Declarative typed data parsing and strict environment variable configuration |
| **Containerization**| Docker & Docker Compose | Uniform runtime packaging for API, database, cache, and worker |
| **Testing** | Pytest, HTTPX, PyPDF | Rigorous automated unit, integration, and end-to-end PDF validation |

---

## Project Structure

```
Certificate_Generator/
├── alembic/                      # Database migration scripts
│   ├── env.py                    # Alembic runtime configuration
│   ├── script.py.mako            # Migration template
│   └── versions/
│       └── 001_initial_schema.py # Initial database schema migration
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI initialization & exception handlers
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py         # GET /health
│   │       ├── jobs.py           # POST /api/v1/jobs, GET /jobs/{id}, GET /jobs/{id}/results
│   │       └── certificates.py   # GET /api/v1/certificates/{id}
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic Settings configuration
│   │   ├── database.py           # Engine & SessionLocal management
│   │   └── logging.py            # Structured logging setup
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── custom_exceptions.py  # Domain-specific application exceptions
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py                # GenerationJob SQLAlchemy model & JobStatus enum
│   │   ├── recipient.py          # Recipient model & RecipientStatus enum
│   │   └── certificate.py        # Certificate model
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── job_repository.py     # GenerationJob queries & atomic increments
│   │   ├── recipient_repository.py# Recipient queries & bulk creation
│   │   └── certificate_repository.py# Certificate queries & storage
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── job.py                # BulkJobCreateRequest, JobStatusResponse, etc.
│   │   ├── recipient.py          # RecipientInput, RecipientResultItem
│   │   └── certificate.py        # CertificateResponse
│   ├── services/
│   │   ├── __init__.py
│   │   ├── job_service.py        # Job creation, status tracking, results mapping
│   │   ├── recipient_service.py
│   │   ├── certificate_service.py# PDF generation & download coordinator
│   │   └── validation_service.py # Recipient validation and error partitioning
│   ├── storage/
│   │   ├── __init__.py
│   │   └── file_storage.py       # Safe filesystem operations & path traversal defense
│   ├── templates/
│   │   ├── __init__.py
│   │   └── certificate_template.py# Predefined ReportLab PDF certificate template
│   └── workers/
│       ├── __init__.py
│       ├── celery_app.py         # Celery configuration
│       └── tasks.py              # Celery background job processing task
├── generated/                    # Storage directory for generated certificates
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Test fixtures (isolated SQLite DB, storage, eager Celery)
│   ├── test_health.py            # Health check test
│   ├── test_job_creation.py      # Job creation & persistence tests
│   ├── test_validation.py        # Input & recipient validation tests
│   ├── test_certificate_generation.py # ReportLab PDF rendering & format verification
│   ├── test_job_status.py        # Status endpoint & progress calculation tests
│   ├── test_failure_handling.py  # A->Success, B->Fail, C->Success isolation test
│   ├── test_certificate_retrieval.py # Download & missing file tests
│   └── test_end_to_end_flow.py   # Full API flow and DB relationship cascade tests
├── .dockerignore
├── .env.example                  # Template environment variables
├── .gitignore
├── alembic.ini                   # Alembic configuration
├── docker-compose.yml            # Multi-service container orchestration
├── Dockerfile                    # Container image definition
├── requirements.txt              # Production and test dependencies
└── README.md
```

---

## Prerequisites

- **Python**: 3.12 or higher (Python 3.13 supported)
- **PostgreSQL**: 15+ (or Docker Compose)
- **Redis**: 7+ (or Docker Compose)
- **Git**

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development`, `production`, `test`) | `development` |
| `DEBUG` | Enable SQLAlchemy query logging | `false` |
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql://postgres:postgres@localhost:5432/certificates_db` |
| `REDIS_URL` | Redis server URL | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend URL | `redis://localhost:6379/0` |
| `CELERY_TASK_ALWAYS_EAGER`| Execute Celery tasks synchronously (tests / single-node dev) | `false` |
| `STORAGE_PATH` | Relative or absolute path for generated PDFs | `generated` |
| `MAX_BATCH_SIZE` | Maximum allowed recipients per request | `1000` |

---

## Local Development Setup

### 1. Create and Activate Virtual Environment

```bash
# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
py -3.12 -m venv .venv
# or
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Database & Alembic Migrations

To apply migrations against your configured database:

```bash
# Run latest database migrations
alembic upgrade head

# Rollback one migration (if needed)
alembic downgrade -1
```

*Note: The application does NOT use `Base.metadata.create_all()` in production code. All schema versioning is managed explicitly through Alembic.*

---

## Running the Application Locally

### 1. Start Celery Worker

In a dedicated terminal:

```bash
# Linux / macOS:
celery -A app.workers.celery_app worker --loglevel=info

# Windows (Windows does not support Unix fork, use solo pool):
celery -A app.workers.celery_app worker --loglevel=info -P solo
```

### 2. Start FastAPI Server

In another terminal:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive Swagger UI will be available at: **http://localhost:8000/docs**

---

## Running with Docker & Docker Compose

To run the entire stack (FastAPI + PostgreSQL + Redis + Celery Worker) with one command:

```bash
docker compose up --build
```

To run in the background (detached):

```bash
docker compose up -d --build
```

To view logs:

```bash
docker compose logs -f
```

To shut down and preserve volumes:

```bash
docker compose down
```

To clean up all data volumes:

```bash
docker compose down -v
```

---

## Running Automated Tests

The test suite utilizes an isolated in-memory SQLite database and isolated temporary file storage. **Tests never touch or pollute your development or production database.**

Run pytest:

```bash
# Run all tests with verbose output
pytest -v

# Run with test coverage report
pytest -v --cov=app
```

---

## API Documentation & Endpoints

| Method | Endpoint | Status Code | Description |
|---|---|---|---|
| `GET` | `/health` | `200 OK` | Verifies API, database, and Redis health |
| `POST` | `/api/v1/jobs` | `202 Accepted` | Submits bulk certificate generation job |
| `GET` | `/api/v1/jobs/{job_id}` | `200 OK` | Retrieves real-time persisted progress and job status |
| `GET` | `/api/v1/jobs/{job_id}/results` | `200 OK` | Retrieves outcomes and download links for each recipient |
| `GET` | `/api/v1/certificates/{certificate_id}`| `200 OK` | Downloads generated certificate PDF |

---

## Curl Examples & Usage Guide

### 1. Health Check

```bash
curl -X GET http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "database": "healthy",
  "redis": "healthy"
}
```

---

### 2. Submit Bulk Certificate Generation Request

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": [
      {
        "name": "Akshaya K",
        "email": "akshaya@example.com",
        "event_name": "Python Backend Development",
        "completion_date": "2026-10-07"
      },
      {
        "name": "Vivek K K",
        "email": "vivek@example.com",
        "event_name": "Python Backend Development",
        "completion_date": "2026-10-07"
      },
      {
        "name": "Invalid Recipient",
        "email": "not-a-valid-email",
        "event_name": "Python Backend Development",
        "completion_date": "2026-10-07"
      }
    ]
  }'
```

**Response (`HTTP 202 Accepted`):**
```json
{
  "job_id": "93b6ddac-ab42-43c1-946e-5b7e721cce6f",
  "status": "QUEUED",
  "total": 3,
  "valid": 2,
  "invalid": 1
}
```

---

### 3. Track Job Status & Progress

```bash
curl -X GET http://localhost:8000/api/v1/jobs/93b6ddac-ab42-43c1-946e-5b7e721cce6f
```

**Response (`HTTP 200 OK`):**
```json
{
  "job_id": "93b6ddac-ab42-43c1-946e-5b7e721cce6f",
  "status": "COMPLETED_WITH_ERRORS",
  "total": 3,
  "successful": 2,
  "failed": 0,
  "invalid": 1,
  "pending": 0,
  "progress_percentage": 100.0,
  "created_at": "2026-10-07T02:50:01Z",
  "started_at": "2026-10-07T02:50:01.944Z",
  "completed_at": "2026-10-07T02:50:01.990Z"
}
```

---

### 4. Fetch Job Results

```bash
curl -X GET http://localhost:8000/api/v1/jobs/93b6ddac-ab42-43c1-946e-5b7e721cce6f/results
```

**Response (`HTTP 200 OK`):**
```json
{
  "job_id": "93b6ddac-ab42-43c1-946e-5b7e721cce6f",
  "results": [
    {
      "recipient_id": "cd1ce8b6-20b2-4bbf-b22c-07aa03476d3f",
      "name": "Akshaya K",
      "status": "SUCCESS",
      "certificate_id": "afeff39d-beda-4cf3-ab11-13911435048b",
      "download_url": "/api/v1/certificates/afeff39d-beda-4cf3-ab11-13911435048b",
      "error": null
    },
    {
      "recipient_id": "6bd83dfe-83fd-410c-a5e8-1070cf79de58",
      "name": "Vivek K K",
      "status": "SUCCESS",
      "certificate_id": "df76c1b7-6002-439e-9db5-7b6716da4ae9",
      "download_url": "/api/v1/certificates/df76c1b7-6002-439e-9db5-7b6716da4ae9",
      "error": null
    },
    {
      "recipient_id": "7f2cd0d9-bc58-42ac-bd74-b6259a619ed9",
      "name": "Invalid Recipient",
      "status": "INVALID",
      "certificate_id": null,
      "download_url": null,
      "error": "email: value is not a valid email address: An email address must have an @-sign."
    }
  ]
}
```

---

### 5. Download Certificate PDF

```bash
curl -O -J http://localhost:8000/api/v1/certificates/afeff39d-beda-4cf3-ab11-13911435048b
```

This saves `certificate_afeff39d-beda-4cf3-ab11-13911435048b.pdf` directly to your local working directory.

---

## Deep Dive: Architectural & Design Decisions

### Why Background Processing?
Rendering vector PDFs with embedded typography, borders, and geometry requires non-trivial CPU cycles (typically 15–50ms per PDF). For a bulk batch of 500 recipients:
- Generating synchronously would block the HTTP connection for 10–25 seconds.
- Most standard HTTP proxies (Nginx, AWS ALB, Cloudflare) enforce 15–30s read timeouts.
- Offloading processing to Celery allows the HTTP endpoint to return in sub-10ms, while background workers process items concurrently without starving web traffic.

### Why Celery & Redis?
- **Celery** is the industry standard distributed task queue for Python. It provides built-in worker process pools, task retries, acknowledgment guarantees (`acks_late`), and clear error handling.
- **Redis** serves as an ultra-fast in-memory broker with negligible overhead for job queuing and pub/sub signaling.
- Furthermore, Celery provides an eager execution mode (`CELERY_TASK_ALWAYS_EAGER=true`), making integration testing fast and deterministic without requiring an active Redis daemon.

### Why PostgreSQL & SQLAlchemy 2.x?
- PostgreSQL provides strict relational integrity (Foreign Keys, Unique constraints, Cascading deletes).
- SQLAlchemy 2.x utilizes modern `Mapped[...]` and `mapped_column` type annotations, giving full static analysis support with Mypy/Pyright.
- Alembic enables version-controlled, auditable database schema migrations.

### Failure Isolation Guarantee
A core design requirement is that **failure of one certificate must never stop others in the batch**.
1. **Pre-flight Partitioning**: During job creation, each recipient payload is parsed through Pydantic's `RecipientInput`. Valid items enter `PENDING` state; invalid items are persisted as `INVALID` with their specific validation errors.
2. **Per-Recipient Transaction Boundaries**: The Celery worker does **not** wrap the entire bulk batch in a single monolithic transaction. Instead, each recipient is processed in its own `try...except` block:
   - On success: PDF is saved, `Certificate` row created, recipient marked `SUCCESS`, and `db.commit()` is called.
   - On exception: `db.rollback()` cleans up any dirty session state, recipient is marked `FAILED` with the exact exception message, and committed independently.
3. **Loop Continuity**: The worker proceeds unconditionally to the next recipient.
4. **Final Status**: If any recipient failed or was invalid, the job transitions to `COMPLETED_WITH_ERRORS`.

### How Progress is Calculated
Progress is calculated directly from persisted database records:
$$\text{Progress} = \frac{\text{successful\_count} + \text{failed\_count} + \text{invalid\_count}}{\text{total\_count}} \times 100$$
Because this is derived from PostgreSQL rows and atomic SQL updates rather than volatile in-memory worker variables, progress tracking remains accurate even if Celery worker nodes restart mid-batch.

### Storage Strategy & Path Traversal Security
1. Certificates are persisted on the local filesystem under:
   ```
   generated/<job_id>/<certificate_id>.pdf
   ```
2. The database stores the relative or absolute filepath.
3. **Path Traversal Defense**: The `FileStorage` class resolves paths with `.resolve()` and enforces `path.is_relative_to(base_dir)`. Any attempt to request files outside `generated/` raises a `StorageError` and prevents unauthorized filesystem access.
4. Internal filesystem paths are **never** returned in API responses.

---

## Tradeoffs & Considerations

1. **Local Filesystem vs Object Storage (S3/GCS)**:
   - *Chosen*: Local filesystem organized by UUID folders.
   - *Reason*: Avoids external cloud vendor dependencies and complex AWS SDK setup for this assignment.
   - *Production Tradeoff*: For horizontally auto-scaled worker pools across multiple VM instances, mounting an S3/GCS bucket or shared NFS volume would be preferred. The `FileStorage` class is decoupled so migrating to S3 involves only updating that single module.

2. **Single-Worker Loop vs Individual Celery Tasks per Recipient**:
   - *Chosen*: One Celery task per batch iterating through recipients with isolated transactions.
   - *Reason*: Avoids queuing tens of thousands of individual Celery messages in Redis for large batches, keeping broker message overhead minimal and avoiding queue flooding.
   - *Production Tradeoff*: If ultra-high parallelism across 50 worker nodes is desired, a Celery `chord` or `group` could distribute individual recipient tasks.

---

## Limitations

- **Email Delivery**: The current scope focuses on generating and persisting the certificates; dispatching emails with PDF attachments is not enabled by default.
- **Certificate Templates**: The service uses ONE predefined ReportLab template. Custom user-uploaded templates are intentionally disallowed to prevent arbitrary code execution and maintain layout consistency.
- **Idempotency Keys**: Request deduplication can be enabled in production via a custom Redis idempotency middleware using `Idempotency-Key` headers.
