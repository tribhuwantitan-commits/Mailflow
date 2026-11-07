"""Organization listing, creation, and membership-scoped detail routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db_session
from app.api.errors import APIError
from app.models import Organization, OrganizationMembership, User
from app.schemas.organizations import OrganizationCreate, OrganizationRead
from app.services.organizations import add_organization_with_owner

router = APIRouter()


def _organization_read(organization: Organization, role: str) -> OrganizationRead:
    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        owner_user_id=organization.owner_user_id,
        role=role,
        created_at=organization.created_at,
    )


def _not_found() -> APIError:
    return APIError(
        status_code=404,
        code="organization_not_found",
        message="Organization not found.",
    )


def _database_unavailable() -> APIError:
    return APIError(
        status_code=503,
        code="organization_service_unavailable",
        message="Organization service is temporarily unavailable.",
    )


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[OrganizationRead]:
    """List only organizations for which the current user has a membership row."""
    try:
        rows = db.execute(
            select(Organization, OrganizationMembership.role)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .where(OrganizationMembership.user_id == current_user.id)
            .order_by(Organization.created_at, Organization.id)
        ).all()
    except SQLAlchemyError:
        raise _database_unavailable() from None
    response.headers["Cache-Control"] = "no-store"
    return [_organization_read(organization, role) for organization, role in rows]


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> OrganizationRead:
    """Create an organization and its owner membership in one transaction."""
    try:
        organization = add_organization_with_owner(
            db,
            name=payload.name,
            owner_user_id=current_user.id,
        )
        db.commit()
        db.refresh(organization)
    except SQLAlchemyError:
        db.rollback()
        raise _database_unavailable() from None

    response.headers["Cache-Control"] = "no-store"
    return _organization_read(organization, "owner")


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> OrganizationRead:
    """Read an organization only when the current user is a member; hide foreign IDs."""
    try:
        row = db.execute(
            select(Organization, OrganizationMembership.role)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .where(
                Organization.id == organization_id,
                OrganizationMembership.user_id == current_user.id,
            )
        ).one_or_none()
    except SQLAlchemyError:
        raise _database_unavailable() from None
    if row is None:
        raise _not_found()

    organization, role = row
    response.headers["Cache-Control"] = "no-store"
    return _organization_read(organization, role)
