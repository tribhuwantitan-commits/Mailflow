"""FastAPI application factory, health endpoints, and versioned API routers."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.emails import router as emails_router
from app.api.errors import APIError
from app.api.keys import router as keys_router
from app.api.organizations import router as organizations_router
from app.config import Settings
from app.database import check_database, create_database_engine, create_session_factory

logger = logging.getLogger("mailflow.health")


def create_app(
    settings: Settings | None = None,
    *,
    database_engine: Engine | None = None,
) -> FastAPI:
    """Build the app; injectable settings/engine keep tests isolated."""
    app_settings = settings or Settings()
    engine = database_engine or create_database_engine(
        app_settings.database_url,
        app_settings.database_connect_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.database_engine = engine
    app.state.session_factory = create_session_factory(engine)

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache", **(exc.headers or {})}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        # Do not echo submitted password/token fields through Pydantic error details.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                }
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    app.include_router(auth_router, prefix="/v1/auth", tags=["authentication"])
    app.include_router(organizations_router, prefix="/v1/organizations", tags=["organizations"])
    app.include_router(
        keys_router, prefix="/v1/organizations/{organization_id}/api-keys", tags=["api-keys"]
    )
    app.include_router(emails_router, prefix="/v1/emails", tags=["emails"])

    @app.get("/health/live", tags=["health"])
    def health_live() -> dict[str, str]:
        """Report that the HTTP process is alive; do not depend on external services."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def health_ready(request: Request) -> JSONResponse:
        """Check the PostgreSQL connection without returning connection details."""
        try:
            check_database(request.app.state.database_engine)
        except SQLAlchemyError as exc:
            logger.warning("Database readiness probe failed (%s)", type(exc).__name__)
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready"},
            )
        return JSONResponse(content={"status": "ready", "checks": {"database": "ok"}})

    return app


app = create_app()
