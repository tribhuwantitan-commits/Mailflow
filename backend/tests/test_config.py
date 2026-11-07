"""Tests for environment-based settings and safe representation."""

from pydantic import SecretStr

from app.config import Settings


def test_settings_load_environment_and_mask_database_url(monkeypatch) -> None:
    database_url = "postgresql+psycopg://mailflow:local-only-secret@127.0.0.1:5432/mailflow"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("AUTH_TOKEN_EXPIRE_MINUTES", "45")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.database_connect_timeout_seconds == 9
    assert settings.auth_token_expire_minutes == 45
    assert settings.database_url == SecretStr(database_url)
    assert "local-only-secret" not in repr(settings)


def test_settings_have_local_postgres_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert "127.0.0.1" in settings.database_url.get_secret_value()
