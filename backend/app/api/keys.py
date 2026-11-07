"""Owner-controlled organization API key lifecycle."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db_session
from app.api.errors import APIError
from app.models import User
from app.models.delivery import APIKey
from app.models.organization import OrganizationMembership
from app.security.tokens import create_access_token

router = APIRouter()


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def owner(db: Session, organization_id: UUID, user: User) -> None:
    membership = db.get(OrganizationMembership, (organization_id, user.id))
    if membership is None or membership.role != "owner":
        raise APIError(
            status_code=404, code="organization_not_found", message="Organization not found."
        )


def public(key: APIKey) -> dict:
    return {
        "id": key.id,
        "organization_id": key.organization_id,
        "name": key.name,
        "is_active": key.is_active,
        "revoked_at": key.revoked_at,
        "created_at": key.created_at,
    }


def unavailable() -> APIError:
    return APIError(
        status_code=503,
        code="key_service_unavailable",
        message="Key service is temporarily unavailable.",
    )


@router.post("", status_code=201)
def create_key(
    organization_id: UUID,
    payload: KeyCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        owner(db, organization_id, user)
        raw, digest = create_access_token()
        key = APIKey(organization_id=organization_id, name=payload.name, key_hash=digest)
        db.add(key)
        db.commit()
        db.refresh(key)
        response.headers["Cache-Control"] = "no-store"
        return {**public(key), "key": f"mfk_{raw}"}
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None


@router.get("")
def list_keys(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[dict]:
    try:
        owner(db, organization_id, user)
        return [
            public(key)
            for key in db.scalars(
                select(APIKey)
                .where(APIKey.organization_id == organization_id)
                .order_by(APIKey.created_at, APIKey.id)
            )
        ]
    except SQLAlchemyError:
        raise unavailable() from None


def selected(db: Session, organization_id: UUID, key_id: UUID, user: User) -> APIKey:
    owner(db, organization_id, user)
    key = db.get(APIKey, key_id)
    if key is None or key.organization_id != organization_id:
        raise APIError(status_code=404, code="key_not_found", message="Key not found.")
    return key


@router.post("/{key_id}/revoke")
def revoke_key(
    organization_id: UUID,
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        key = selected(db, organization_id, key_id, user)
        key.is_active = False
        if key.revoked_at is None:
            key.revoked_at = datetime.now(timezone.utc)
            db.commit()
            return public(key)
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None


@router.delete("/{key_id}", status_code=204)
def delete_key(
    organization_id: UUID,
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    try:
        key = selected(db, organization_id, key_id, user)
        db.delete(key)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None
