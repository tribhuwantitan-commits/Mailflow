"""Application-level protections for organization owner/membership consistency."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.db.ownership import OrganizationOwnershipInvariantError
from app.models import Organization, OrganizationMembership, User


def test_orm_rejects_organization_without_owner_membership(database_engine) -> None:
    user_id = uuid4()
    organization = Organization(
        id=uuid4(),
        name="Orphaned ownership",
        owner_user_id=user_id,
    )
    user = User(
        id=user_id,
        name="Owner",
        email="owner@example.com",
        password_hash="test-only-hash",
    )

    with Session(database_engine) as db:
        db.add_all([user, organization])
        with pytest.raises(OrganizationOwnershipInvariantError, match="exactly one owner"):
            db.flush()
            db.rollback()


def test_orm_rejects_owner_membership_for_a_different_user(database_engine) -> None:
    owner_id = uuid4()
    other_user_id = uuid4()
    organization_id = uuid4()
    owner = User(
        id=owner_id,
        name="Owner",
        email="owner@example.com",
        password_hash="test-only-hash",
    )
    other_user = User(
        id=other_user_id,
        name="Other",
        email="other@example.com",
        password_hash="test-only-hash",
    )
    organization = Organization(
        id=organization_id,
        name="Mismatched ownership",
        owner_user_id=owner_id,
    )
    mismatched_membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=other_user_id,
        role="owner",
    )

    with Session(database_engine) as db:
        db.add_all([owner, other_user, organization, mismatched_membership])
        with pytest.raises(OrganizationOwnershipInvariantError, match="must match"):
            db.flush()
            db.rollback()


def test_persisted_owner_and_membership_role_cannot_be_changed_or_removed(
    client,
    database_engine,
) -> None:
    registration = client.post(
        "/v1/auth/register",
        json={
            "name": "Owner",
            "email": "owner@example.com",
            "password": "Correct horse battery staple 2026!",
        },
    )
    assert registration.status_code == 201
    organization_id = UUID(registration.json()["organization"]["id"])
    owner_id = UUID(registration.json()["user"]["id"])
    other_user_id = uuid4()

    with Session(database_engine) as db:
        organization = db.get(Organization, organization_id)
        assert organization is not None
        organization.owner_user_id = other_user_id
        with pytest.raises(OrganizationOwnershipInvariantError, match="immutable"):
            db.flush()
            db.rollback()

            with Session(database_engine) as db:
                owner_membership = db.get(OrganizationMembership, (organization_id, owner_id))
                assert owner_membership is not None
                owner_membership.role = "member"
                with pytest.raises(OrganizationOwnershipInvariantError, match="immutable"):
                    db.flush()
                    db.rollback()

                    with Session(database_engine) as db:
                        owner_membership = db.get(
                            OrganizationMembership, (organization_id, owner_id)
                        )
                        assert owner_membership is not None
                        db.delete(owner_membership)
                        with pytest.raises(
                            OrganizationOwnershipInvariantError, match="cannot be removed"
                        ):
                            db.flush()
                            db.rollback()
