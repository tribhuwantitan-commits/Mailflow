"""Application-level ORM guards for organization ownership invariants.

The relational schema enforces valid membership roles and at most one owner row,
but it cannot assert that every organization has an owner row matching
``organizations.owner_user_id`` without a database-specific trigger. These
checks protect all normal SQLAlchemy ORM flushes used by the application.
"""

from collections import defaultdict

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationMembership


class OrganizationOwnershipInvariantError(ValueError):
    """Raised when an ORM flush could leave organization ownership inconsistent."""


@event.listens_for(Session, "before_flush")
def _enforce_organization_owner_invariants(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    """Require paired owner creation and forbid partial ownership mutations."""
    deleted_organization_ids = {
        organization.id
        for organization in session.deleted
        if isinstance(organization, Organization)
    }
    new_organizations = {
        organization.id: organization
        for organization in session.new
        if isinstance(organization, Organization)
    }
    new_owner_memberships: dict[object, list[OrganizationMembership]] = defaultdict(list)

    for membership in session.new:
        if isinstance(membership, OrganizationMembership) and membership.role == "owner":
            organization_id = membership.organization_id
            if organization_id is None and membership.organization is not None:
                organization_id = membership.organization.id
            new_owner_memberships[organization_id].append(membership)

    for organization_id, organization in new_organizations.items():
        if organization_id is None:
            raise OrganizationOwnershipInvariantError(
                "Organization IDs must be assigned before creating the owner membership."
            )
        owner_memberships = new_owner_memberships.get(organization_id, [])
        if len(owner_memberships) != 1:
            raise OrganizationOwnershipInvariantError(
                "A new organization must be created with exactly one owner membership."
            )
        if owner_memberships[0].user_id != organization.owner_user_id:
            raise OrganizationOwnershipInvariantError(
                "The owner membership must match the organization's owner user."
            )

    for organization_id in new_owner_memberships:
        if organization_id not in new_organizations:
            raise OrganizationOwnershipInvariantError(
                "An owner membership can only be added with its new organization."
            )

    for organization in session.dirty:
        if not isinstance(organization, Organization):
            continue
        state = inspect(organization)
        if (
            state.attrs.owner_user_id.history.has_changes()
            or state.attrs.owner.history.has_changes()
        ):
            raise OrganizationOwnershipInvariantError(
                "Organization ownership is immutable in Phase 2."
            )

    for membership in session.dirty:
        if not isinstance(membership, OrganizationMembership):
            continue
        state = inspect(membership)
        changed_identity_or_role = any(
            state.attrs[field].history.has_changes()
            for field in ("organization_id", "user_id", "role")
        )
        if changed_identity_or_role:
            raise OrganizationOwnershipInvariantError(
                "Membership identity and role are immutable in Phase 2."
            )

    for membership in session.deleted:
        if (
            isinstance(membership, OrganizationMembership)
            and membership.role == "owner"
            and membership.organization_id not in deleted_organization_ids
        ):
            raise OrganizationOwnershipInvariantError(
                "An owner membership cannot be removed while its organization remains."
            )
