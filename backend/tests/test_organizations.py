"""Organization CRUD surface and tenant-isolation tests."""

from http.cookies import SimpleCookie
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import AUTH_COOKIE_NAME
from app.models import Organization, OrganizationMembership


def register_and_login(client, email: str, name: str) -> tuple[str, dict]:
    registration = client.post(
        "/v1/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "Correct horse battery staple 2026!",
        },
    )
    assert registration.status_code == 201
    login = client.post(
        "/v1/auth/login",
        json={"email": email, "password": "Correct horse battery staple 2026!"},
    )
    assert login.status_code == 200
    cookie = SimpleCookie()
    cookie.load(login.headers["set-cookie"])
    return cookie[AUTH_COOKIE_NAME].value, registration.json()


def test_organization_creation_and_listing_use_owner_membership(client, database_engine) -> None:
    token, registration = register_and_login(client, "alice@example.com", "Alice")
    auth = {"Authorization": f"Bearer {token}"}

    default_org_id = registration["organization"]["id"]
    listed = client.get("/v1/organizations", headers=auth)
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert [org["id"] for org in listed.json()] == [default_org_id]
    assert listed.json()[0]["role"] == "owner"

    created = client.post("/v1/organizations", json={"name": "Research"}, headers=auth)
    assert created.status_code == 201
    assert created.json()["name"] == "Research"
    assert created.json()["role"] == "owner"
    assert created.json()["owner_user_id"] == registration["user"]["id"]

    with Session(database_engine) as db:
        organization = db.get(Organization, UUID(created.json()["id"]))
        owner_membership = db.get(
            OrganizationMembership,
            (UUID(created.json()["id"]), UUID(registration["user"]["id"])),
        )
        assert organization is not None
        assert owner_membership is not None
        assert organization.owner_user_id == owner_membership.user_id
        assert owner_membership.role == "owner"

    detail = client.get(f"/v1/organizations/{created.json()['id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json() == created.json()
    assert len(client.get("/v1/organizations", headers=auth).json()) == 2


def test_organization_access_is_scoped_to_membership(client) -> None:
    alice_token, alice_registration = register_and_login(
        client,
        "alice@example.com",
        "Alice",
    )
    alice_org_id = alice_registration["organization"]["id"]

    bob_token, bob_registration = register_and_login(
        client,
        "bob@example.com",
        "Bob",
    )
    bob_org_id = bob_registration["organization"]["id"]

    alice_orgs = client.get(
        "/v1/organizations",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    bob_orgs = client.get(
        "/v1/organizations",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    alice_access_to_bob = client.get(
        f"/v1/organizations/{bob_org_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    bob_access_to_alice = client.get(
        f"/v1/organizations/{alice_org_id}",
        headers={"Authorization": f"Bearer {bob_token}"},
    )

    assert [org["id"] for org in alice_orgs.json()] == [alice_org_id]
    assert [org["id"] for org in bob_orgs.json()] == [bob_org_id]
    assert alice_access_to_bob.status_code == bob_access_to_alice.status_code == 404
    assert alice_access_to_bob.json() == bob_access_to_alice.json()
    assert alice_access_to_bob.json()["error"]["code"] == "organization_not_found"


def test_organization_creation_requires_authentication(client) -> None:
    response = client.post("/v1/organizations", json={"name": "Private"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
