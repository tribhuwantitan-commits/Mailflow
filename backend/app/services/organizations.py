"""Organization creation transaction helpers."""

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models import Organization, OrganizationMembership


def add_organization_with_owner(
    db: Session,
    *,
    name: str,
    owner_user_id: UUID,
) -> Organization:
    """Stage an organization and its matching owner row in the caller's transaction.

    The caller commits or rolls back the transaction. The ORM flush guard rejects
    organization inserts unless this helper's paired owner membership is present.
    """
    organization_id = uuid4()
    organization = Organization(
        id=organization_id,
        name=name,
        owner_user_id=owner_user_id,
    )
    owner_membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=owner_user_id,
        role="owner",
    )
    db.add_all([organization, owner_membership])
    return organization
