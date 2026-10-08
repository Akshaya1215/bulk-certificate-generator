import os
import pytest
from collections.abc import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test settings before importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.storage.file_storage import FileStorage, file_storage
from app.workers.celery_app import celery_app

# Use in-memory SQLite with StaticPool for fast, isolated, safe tests
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def configure_celery():
    """Forces Celery into eager execution mode during all tests."""
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    settings.CELERY_TASK_ALWAYS_EAGER = True


@pytest.fixture(scope="function")
def test_storage(tmp_path):
    """Provides a fresh isolated filesystem storage directory for each test."""
    custom_storage = FileStorage(base_dir=tmp_path / "test_generated")
    # Patch the global file_storage singleton base dir
    original_base = file_storage.base_dir
    file_storage.base_dir = custom_storage.base_dir
    yield custom_storage
    file_storage.base_dir = original_base


@pytest.fixture(scope="function", autouse=True)
def bind_test_db_to_session():
    """Binds TestingSessionLocal to app.core.database.SessionLocal so worker tasks share the test DB."""
    import app.core.database as app_db
    original_session = app_db.SessionLocal
    app_db.SessionLocal = TestingSessionLocal
    yield
    app_db.SessionLocal = original_session


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Creates a clean database schema and session for each individual test function."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session, test_storage: FileStorage) -> Generator[TestClient, None, None]:
    """Provides a FastAPI TestClient wired to the isolated test database and test storage."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
