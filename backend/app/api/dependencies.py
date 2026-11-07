"""Database and authentication dependencies shared by protected routes."""

from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.config import AUTH_COOKIE_NAME, Settings
from app.models import AuthSession, User
from app.security.tokens import hash_access_token

_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")
_session_cookie_scheme = APIKeyCookie(
    name=AUTH_COOKIE_NAME,
    auto_error=False,
    scheme_name="SessionCookie",
)


def get_db_session(request: Request) -> Iterator[Session]:
    """Yield one request-scoped SQLAlchemy session."""
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    """Return the app's immutable settings instance."""
    return request.app.state.settings


def extract_access_token(request: Request) -> str | None:
    """Prefer explicit Bearer credentials, then fall back to the HttpOnly cookie."""
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split(None, 1)
    if parts and parts[0].casefold() == "bearer":
        # An explicitly supplied Bearer scheme never falls back to the cookie.
        # Missing, whitespace-only, or malformed credentials fail authentication.
        if len(parts) != 2 or len(parts[1].split()) != 1:
            return None
        return parts[1].strip()
    return request.cookies.get(AUTH_COOKIE_NAME)


def _authentication_required() -> APIError:
    return APIError(
        status_code=401,
        code="authentication_required",
        message="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    _bearer: object = Security(_bearer_scheme),
    _session_cookie: str | None = Security(_session_cookie_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    """Resolve a non-expired, non-revoked opaque token to its active user."""
    token = extract_access_token(request)
    if not token or len(token) > 256:
        raise _authentication_required()

    try:
        auth_session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_access_token(token))
        )
    except SQLAlchemyError:
        raise APIError(
            status_code=503,
            code="authentication_unavailable",
            message="Authentication is temporarily unavailable.",
        ) from None

    now = datetime.now(timezone.utc)
    if auth_session is None or auth_session.revoked_at is not None:
        raise _authentication_required()
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise _authentication_required()

    try:
        user = db.get(User, auth_session.user_id)
    except SQLAlchemyError:
        raise APIError(
            status_code=503,
            code="authentication_unavailable",
            message="Authentication is temporarily unavailable.",
        ) from None

    if user is None or not user.is_active:
        raise _authentication_required()
    return user
