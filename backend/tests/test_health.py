"""Tests for liveness and PostgreSQL readiness behavior."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app


def test_liveness_does_not_depend_on_database(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_database_query_success(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_readiness_hides_database_error_details(test_settings: Settings) -> None:
    class UnavailableEngine:
        def connect(self) -> None:
            raise SQLAlchemyError("connection failed; password=must-not-leak")

        def dispose(self) -> None:
            pass

    app = create_app(test_settings, database_engine=UnavailableEngine())  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
        assert "must-not-leak" not in response.text
