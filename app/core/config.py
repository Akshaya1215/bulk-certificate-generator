import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application details
    APP_NAME: str = "Bulk Certificate Generator"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/certificates_db"

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # File Storage
    STORAGE_PATH: str = "generated"

    # Batch limits
    MAX_BATCH_SIZE: int = 1000

    @property
    def sqlalchemy_database_url(self) -> str:
        """Ensures standard postgresql:// URLs use the psycopg2 driver."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    @property
    def storage_absolute_path(self) -> Path:
        """Returns resolved absolute path to the certificate storage directory."""
        path = Path(self.STORAGE_PATH)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path


settings = Settings()
