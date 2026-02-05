"""Application configuration using pydantic-settings."""
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    app_name: str = "procurewatch-api"
    database_url: str = Field(
        ...,
        validation_alias=AliasChoices("DATABASE_URL", "database_url")
    )
    allowed_origins: str = "*"
    log_level: str = "INFO"

    # Belgian e-Procurement connector
    eproc_mode: str = Field("auto", validation_alias="EPROC_MODE")  # official | playwright | auto
    eproc_oauth_token_url: str = "https://public.int.fedservices.be/api/oauth2/token"
    eproc_client_id: Optional[str] = Field(None, validation_alias="EPROC_CLIENT_ID")
    eproc_client_secret: Optional[str] = Field(None, validation_alias="EPROC_CLIENT_SECRET")
    eproc_search_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementSea/v1",
        validation_alias="EPROC_SEARCH_BASE_URL",
    )
    eproc_loc_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementLoc/v1",
        validation_alias="EPROC_LOC_BASE_URL",
    )
    eproc_timeout_seconds: int = Field(30, validation_alias="EPROC_TIMEOUT_SECONDS")

    # TED (EU Tenders Electronic Daily)
    ted_mode: str = Field("official", validation_alias="TED_MODE")  # official | off
    ted_search_base_url: str = Field(
        "https://api.ted.europa.eu",
        validation_alias="TED_SEARCH_BASE_URL",
    )
    ted_timeout_seconds: int = Field(30, validation_alias="TED_TIMEOUT_SECONDS")

    # Email (notifications)
    email_mode: str = Field("file", validation_alias="EMAIL_MODE")  # "file" | "smtp"
    email_from: Optional[str] = Field(None, validation_alias="EMAIL_FROM")
    email_smtp_host: Optional[str] = Field(None, validation_alias="EMAIL_SMTP_HOST")
    email_smtp_port: Optional[int] = Field(None, validation_alias="EMAIL_SMTP_PORT")
    email_smtp_username: Optional[str] = Field(None, validation_alias="EMAIL_SMTP_USERNAME")
    email_smtp_password: Optional[str] = Field(None, validation_alias="EMAIL_SMTP_PASSWORD")
    email_smtp_use_tls: bool = Field(True, validation_alias="EMAIL_SMTP_USE_TLS")
    email_outbox_dir: str = Field("data/outbox", validation_alias="EMAIL_OUTBOX_DIR")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Normalize DATABASE_URL and ensure SSL is required for PostgreSQL."""
        # Skip normalization for sqlite URLs
        if v.startswith("sqlite"):
            return v

        # Convert postgres:// to postgresql+psycopg://
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg://", 1)

        # Convert postgresql:// to postgresql+psycopg:// (if not already using psycopg)
        if v.startswith("postgresql://") and not v.startswith("postgresql+psycopg://"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)

        # Ensure postgresql+psycopg://
        if not v.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must start with postgresql://, postgresql+psycopg://, or sqlite")

        # Ensure sslmode=require is present for PostgreSQL connections
        if "sslmode=" not in v:
            # Add sslmode parameter
            separator = "&" if "?" in v else "?"
            v = f"{v}{separator}sslmode=require"
        elif "sslmode=require" not in v:
            # Replace existing sslmode with require
            import re
            v = re.sub(r"sslmode=[^&]+", "sslmode=require", v)

        return v

    @property
    def allowed_origins_list(self) -> list[str]:
        """Get allowed origins as a list."""
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = Settings()
