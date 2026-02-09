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
        default="sqlite:///./dev.db",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    # Railway provides PORT; default for local
    port: int = Field(default=8000, validation_alias=AliasChoices("PORT", "port"))
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
    eproc_dos_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementDos/v1",
        validation_alias="EPROC_DOS_BASE_URL",
    )
    eproc_cpv_probe: bool = Field(False, validation_alias="EPROC_CPV_PROBE")
    eproc_timeout_seconds: int = Field(30, validation_alias="EPROC_TIMEOUT_SECONDS")

    # BOSA e-Procurement OAuth2 (Client Credentials) - separate INT/PR environments
    eprocurement_env: str = Field("INT", validation_alias="EPROCUREMENT_ENV")  # INT | PR
    eprocurement_int_token_url: str = Field(
        "https://public.int.fedservices.be/api/oauth2/token",
        validation_alias="EPROCUREMENT_INT_TOKEN_URL",
    )
    eprocurement_int_client_id: Optional[str] = Field(None, validation_alias="EPROCUREMENT_INT_CLIENT_ID")
    eprocurement_int_client_secret: Optional[str] = Field(None, validation_alias="EPROCUREMENT_INT_CLIENT_SECRET")
    eprocurement_pr_token_url: str = Field(
        "https://public.pr.fedservices.be/api/oauth2/token",
        validation_alias="EPROCUREMENT_PR_TOKEN_URL",
    )
    eprocurement_pr_client_id: Optional[str] = Field(None, validation_alias="EPROCUREMENT_PR_CLIENT_ID")
    eprocurement_pr_client_secret: Optional[str] = Field(None, validation_alias="EPROCUREMENT_PR_CLIENT_SECRET")

    # BOSA e-Procurement API base URLs (INT/PR)
    eprocurement_int_sea_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementSea/v1",
        validation_alias="EPROCUREMENT_INT_SEA_BASE_URL",
    )
    eprocurement_pr_sea_base_url: str = Field(
        "https://public.pr.fedservices.be/api/eProcurementSea/v1",
        validation_alias="EPROCUREMENT_PR_SEA_BASE_URL",
    )
    eprocurement_int_loc_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementLoc/v1",
        validation_alias="EPROCUREMENT_INT_LOC_BASE_URL",
    )
    eprocurement_pr_loc_base_url: str = Field(
        "https://public.pr.fedservices.be/api/eProcurementLoc/v1",
        validation_alias="EPROCUREMENT_PR_LOC_BASE_URL",
    )
    eprocurement_int_dos_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementDos/v1",
        validation_alias="EPROCUREMENT_INT_DOS_BASE_URL",
    )
    eprocurement_pr_dos_base_url: str = Field(
        "https://public.pr.fedservices.be/api/eProcurementDos/v1",
        validation_alias="EPROCUREMENT_PR_DOS_BASE_URL",
    )
    eprocurement_int_tus_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementTus/v1",
        validation_alias="EPROCUREMENT_INT_TUS_BASE_URL",
    )
    eprocurement_pr_tus_base_url: str = Field(
        "https://public.pr.fedservices.be/api/eProcurementTus/v1",
        validation_alias="EPROCUREMENT_PR_TUS_BASE_URL",
    )
    eprocurement_int_cfg_base_url: str = Field(
        "https://public.int.fedservices.be/api/eProcurementCfg/v1",
        validation_alias="EPROCUREMENT_INT_CFG_BASE_URL",
    )
    eprocurement_pr_cfg_base_url: str = Field(
        "https://public.pr.fedservices.be/api/eProcurementCfg/v1",
        validation_alias="EPROCUREMENT_PR_CFG_BASE_URL",
    )
    eprocurement_endpoint_confirmed: bool = Field(False, validation_alias="EPROCUREMENT_ENDPOINT_CONFIRMED")

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

    # Scheduler
    scheduler_enabled: bool = Field(False, validation_alias="SCHEDULER_ENABLED")
    import_interval_minutes: int = Field(360, validation_alias="IMPORT_INTERVAL_MINUTES")  # 6h default
    import_sources: str = Field("BOSA,TED", validation_alias="IMPORT_SOURCES")
    import_term: str = Field("*", validation_alias="IMPORT_TERM")
    import_page_size: int = Field(50, validation_alias="IMPORT_PAGE_SIZE")
    import_max_pages: int = Field(3, validation_alias="IMPORT_MAX_PAGES")
    backfill_after_import: bool = Field(True, validation_alias="BACKFILL_AFTER_IMPORT")

    # JWT (mock auth for Lovable; real user management later)
    jwt_secret_key: str = Field("change-me-in-production", validation_alias="JWT_SECRET_KEY")
    jwt_expiry_days: int = Field(7, validation_alias="JWT_EXPIRY_DAYS")
    jwt_algorithm: str = Field("HS256", validation_alias="JWT_ALGORITHM")

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

        # Convert postgresql:// to postgresql+psycopg:// (Railway compatibility)
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)
        elif not v.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must start with postgresql:// or sqlite://")

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
    def database_url_sync(self) -> str:
        """Get synchronous database URL for SQLAlchemy (e.g. Railway Postgres)."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return self.database_url

    @property
    def allowed_origins_list(self) -> list[str]:
        """Get allowed origins as a list."""
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def bosa_token_url(self) -> str:
        """Get BOSA OAuth2 token URL for current environment (INT or PR)."""
        if self.eprocurement_env.upper() == "PR":
            return self.eprocurement_pr_token_url
        return self.eprocurement_int_token_url

    @property
    def bosa_client_id(self) -> Optional[str]:
        """Get BOSA OAuth2 client ID for current environment (INT or PR)."""
        if self.eprocurement_env.upper() == "PR":
            return self.eprocurement_pr_client_id
        return self.eprocurement_int_client_id

    @property
    def bosa_client_secret(self) -> Optional[str]:
        """Get BOSA OAuth2 client secret for current environment (INT or PR)."""
        if self.eprocurement_env.upper() == "PR":
            return self.eprocurement_pr_client_secret
        return self.eprocurement_int_client_secret

    @property
    def bosa_sea_base_url(self) -> str:
        """Get BOSA Search API (Sea) base URL for current environment (INT or PR)."""
        if self.eprocurement_env.upper() == "PR":
            return self.eprocurement_pr_sea_base_url
        return self.eprocurement_int_sea_base_url

    @property
    def bosa_loc_base_url(self) -> str:
        """Get BOSA Location API base URL for current environment (INT or PR)."""
        if self.eprocurement_env.upper() == "PR":
            return self.eprocurement_pr_loc_base_url
        return self.eprocurement_int_loc_base_url

    def _resolve_eproc_env_name(self) -> str:
        """Resolve eProcurement environment name (INT or PR)."""
        env_name = (self.eprocurement_env or "INT").strip().upper()
        if env_name not in ("INT", "PR"):
            env_name = "INT"  # Default to INT
        return env_name

    @staticmethod
    def is_placeholder(value: str | None) -> bool:
        """
        Check if a value is a placeholder (should be ignored in config resolution).
        
        Returns True for:
        - None / empty / whitespace-only strings
        - Common placeholder patterns: "__REPLACE_ME__", "REPLACE_ME", "CHANGEME"
        - Values starting with "__REPLACE_ME"
        """
        if not value:
            return True
        
        value_stripped = value.strip()
        if not value_stripped:
            return True
        
        # Common placeholder patterns (case-insensitive)
        placeholders = {
            "__REPLACE_ME__",
            "REPLACE_ME",
            "CHANGEME",
            "__CHANGEME__",
            "YOUR_VALUE_HERE",
            "SET_ME",
        }
        
        if value_stripped.upper() in {p.upper() for p in placeholders}:
            return True
        
        # Values starting with "__REPLACE_ME" (with optional trailing characters)
        if value_stripped.upper().startswith("__REPLACE_ME"):
            return True
        
        return False

    def resolve_eproc_official_config(self) -> dict[str, Optional[str]]:
        """
        Canonicalize eProcurement 'official' mode configuration.
        Returns dict with: token_url, client_id, client_secret, search_base_url, loc_base_url.
        
        Resolution order:
        1. Legacy EPROC_* vars override everything (backward compatibility)
        2. EPROCUREMENT_ENV determines which INT/PR vars to use
        3. Defaults derived from environment if not set
        
        Raises ValueError if in official mode and credentials are missing/invalid.
        """
        env_name = self._resolve_eproc_env_name()
        
        # Resolve token_url: EPROC_OAUTH_TOKEN_URL > EPROCUREMENT_{INT,PR}_TOKEN_URL
        # Legacy override only if present and not a placeholder
        token_url: Optional[str] = None
        if (
            self.eproc_oauth_token_url
            and not self.is_placeholder(self.eproc_oauth_token_url)
            and self.eproc_oauth_token_url != "https://public.int.fedservices.be/api/oauth2/token"
        ):
            token_url = self.eproc_oauth_token_url
        elif env_name == "PR":
            token_url = self.eprocurement_pr_token_url
        else:
            token_url = self.eprocurement_int_token_url
        
        # Resolve client_id: EPROC_CLIENT_ID > EPROCUREMENT_{INT,PR}_CLIENT_ID
        # Legacy override only if present and not a placeholder
        client_id: Optional[str] = None
        if self.eproc_client_id and not self.is_placeholder(self.eproc_client_id):
            client_id = self.eproc_client_id
        elif env_name == "PR":
            client_id = self.eprocurement_pr_client_id
        else:
            client_id = self.eprocurement_int_client_id
        
        # Resolve client_secret: EPROC_CLIENT_SECRET > EPROCUREMENT_{INT,PR}_CLIENT_SECRET
        # Legacy override only if present and not a placeholder
        client_secret: Optional[str] = None
        if self.eproc_client_secret and not self.is_placeholder(self.eproc_client_secret):
            client_secret = self.eproc_client_secret
        elif env_name == "PR":
            client_secret = self.eprocurement_pr_client_secret
        else:
            client_secret = self.eprocurement_int_client_secret
        
        # Resolve search_base_url: EPROC_SEARCH_BASE_URL > EPROCUREMENT_{INT,PR}_SEA_BASE_URL > default
        search_base_url: Optional[str] = None
        if self.eproc_search_base_url and self.eproc_search_base_url != "https://public.int.fedservices.be/api/eProcurementSea/v1":
            search_base_url = self.eproc_search_base_url
        elif env_name == "PR":
            search_base_url = self.eprocurement_pr_sea_base_url
        else:
            search_base_url = self.eprocurement_int_sea_base_url
        
        # Resolve loc_base_url: EPROC_LOC_BASE_URL > EPROCUREMENT_{INT,PR}_LOC_BASE_URL > default
        loc_base_url: Optional[str] = None
        if self.eproc_loc_base_url and self.eproc_loc_base_url != "https://public.int.fedservices.be/api/eProcurementLoc/v1":
            loc_base_url = self.eproc_loc_base_url
        elif env_name == "PR":
            loc_base_url = self.eprocurement_pr_loc_base_url
        else:
            loc_base_url = self.eprocurement_int_loc_base_url

        # Resolve dos_base_url: EPROC_DOS_BASE_URL > EPROCUREMENT_{INT,PR}_DOS_BASE_URL > default
        dos_base_url: Optional[str] = None
        if self.eproc_dos_base_url and self.eproc_dos_base_url != "https://public.int.fedservices.be/api/eProcurementDos/v1":
            dos_base_url = self.eproc_dos_base_url
        elif env_name == "PR":
            dos_base_url = self.eprocurement_pr_dos_base_url
        else:
            dos_base_url = self.eprocurement_int_dos_base_url

        return {
            "token_url": token_url,
            "client_id": client_id,
            "client_secret": client_secret,
            "search_base_url": search_base_url,
            "loc_base_url": loc_base_url,
            "dos_base_url": dos_base_url,
            "env_name": env_name,
        }

    def validate_eproc_official_config(self) -> None:
        """
        Validate eProcurement official mode configuration.
        Raises ValueError with clear message if credentials are missing or invalid.
        """
        if self.eproc_mode.lower() not in ("official", "auto"):
            return  # Only validate for official/auto mode
        
        config = self.resolve_eproc_official_config()
        client_id = config["client_id"]
        client_secret = config["client_secret"]
        env_name = config["env_name"]
        
        # Check if credentials are missing or placeholders
        if not client_id or not client_secret:
            raise ValueError(
                f"eProcurement official mode requires credentials. "
                f"Set EPROCUREMENT_{env_name}_CLIENT_ID/EPROCUREMENT_{env_name}_CLIENT_SECRET in .env. "
                f"Note: Legacy EPROC_CLIENT_ID/EPROC_CLIENT_SECRET placeholders are ignored."
            )
        
        if self.is_placeholder(client_id) or self.is_placeholder(client_secret):
            raise ValueError(
                f"eProcurement credentials contain placeholder values. "
                f"Set real values in .env for EPROCUREMENT_{env_name}_CLIENT_ID/EPROCUREMENT_{env_name}_CLIENT_SECRET. "
                f"Note: Legacy EPROC_CLIENT_ID/EPROC_CLIENT_SECRET placeholders are ignored."
            )


settings = Settings()

# Validate on import if in official mode (fail fast)
try:
    settings.validate_eproc_official_config()
except ValueError:
    # Don't crash on import - validation happens when client is created
    pass
