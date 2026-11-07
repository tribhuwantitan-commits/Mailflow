"""Tests for PostgreSQL engine configuration without making a network connection."""

from pydantic import SecretStr

from app.database import create_database_engine


def test_engine_uses_psycopg_postgresql_dialect() -> None:
    engine = create_database_engine(
        SecretStr("postgresql+psycopg://mailflow:local-only@127.0.0.1:5432/mailflow"),
        connect_timeout_seconds=7,
    )
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()
