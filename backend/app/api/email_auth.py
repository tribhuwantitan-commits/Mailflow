"""API-key-only authentication; user cookies and Bearer sessions never grant send access."""

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.api.errors import APIError
from app.models.delivery import APIKey
from app.security.tokens import hash_access_token

_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, scheme_name="EmailAPIKey")


def get_email_key(
    request: Request,
    _documented: str | None = Security(_scheme),
    db: Session = Depends(get_db_session),
) -> APIKey:
    raw = request.headers.get("X-API-Key", "")
    if not raw.startswith("mfk_") or len(raw) > 100 or len(raw) < 40:
        raise APIError(
            status_code=401, code="invalid_api_key", message="A valid API key is required."
        )
    try:
        key = db.scalar(select(APIKey).where(APIKey.key_hash == hash_access_token(raw[4:])))
    except SQLAlchemyError:
        raise APIError(
            status_code=503,
            code="key_service_unavailable",
            message="Key service is temporarily unavailable.",
        ) from None
    if key is None or not key.is_active or key.revoked_at is not None:
        raise APIError(
            status_code=401, code="invalid_api_key", message="A valid API key is required."
        )
    return key
