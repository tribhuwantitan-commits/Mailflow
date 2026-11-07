"""Verify the complete Alembic chain can be applied and rolled back on SQLite."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_auth_organization_migration_applies_and_downgrades_cleanly(tmp_path, monkeypatch) -> None:
    database_file = tmp_path / "mailflow-migrations.db"
    database_url = URL.create("sqlite+pysqlite", database=str(database_file))
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")

    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        expected_tables = {
            "alembic_version",
            "users",
            "auth_sessions",
            "organizations",
            "organization_memberships",
            "api_keys",
            "email_messages",
            "outbox_events",
        }
        assert expected_tables.issubset(set(inspector.get_table_names()))
        assert {item["name"] for item in inspector.get_unique_constraints("users")} == {
            "uq_users_email"
        }
        membership_indexes = {
            item["name"]: item for item in inspector.get_indexes("organization_memberships")
        }
        assert "ix_organization_memberships_user_id" in membership_indexes
        assert bool(membership_indexes["uq_organization_memberships_single_owner"]["unique"])
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert version == "0004_worker"
    finally:
        engine.dispose()

        command.downgrade(alembic_config, "0003_delivery")
        engine = create_engine(database_url)
        try:
            indexes = {i["name"] for i in inspect(engine).get_indexes("outbox_events")}
            assert "ix_outbox_state_next_attempt" not in indexes
        finally:
            engine.dispose()
            command.upgrade(alembic_config, "head")
            command.downgrade(alembic_config, "0002_auth_orgs")
            engine = create_engine(database_url)
            try:
                assert "outbox_events" not in inspect(engine).get_table_names()
                assert "users" in inspect(engine).get_table_names()
            finally:
                engine.dispose()
                command.upgrade(alembic_config, "head")
                command.downgrade(alembic_config, "0001_initial")
                command.upgrade(alembic_config, "head")

                engine = create_engine(database_url)
                try:
                    assert "users" in inspect(engine).get_table_names()
                    with engine.connect() as connection:
                        version = connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one()
                        assert version == "0004_worker"
                finally:
                    engine.dispose()
