"""Environment-based application settings."""

from typing import Final, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AUTH_COOKIE_NAME: Final = "mailflow_access"


class Settings(BaseSettings):
    """Application configuration; credentials are masked in representations."""

    app_name: str = "MailFlow"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://mailflow:change-me@127.0.0.1:5432/mailflow"),
        repr=False,
    )
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=30, ge=1, le=300)
    database_pool_recycle: int = Field(default=1800, ge=60, le=86400)
    auth_token_expire_minutes: int = Field(default=30, ge=5, le=1440)

    # Email provider selection: "fake" or "ses"
    mail_provider: Literal["fake", "ses"] = Field(default="fake")

    # Amazon SES configuration (only used when mail_provider="ses")
    # Identities and quotas are per Region; keep this aligned with the console.
    aws_region: str = Field(default="ap-south-1")
    aws_access_key_id: str | None = Field(default=None)
    aws_secret_access_key: SecretStr | None = Field(default=None, repr=False)
    ses_from_email: str = Field(default="noreply@example.com")
    ses_configuration_set: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
