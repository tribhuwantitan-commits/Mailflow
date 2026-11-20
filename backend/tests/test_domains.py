"""Phase 7a: per-tenant domain ownership and the send-time gate.

The two behaviours that matter:

1. A tenant cannot send as a domain it has not verified — this is what stops one
   customer from borrowing another customer's (or our) reputation.
2. A domain belongs to exactly one tenant, so a second claim is refused before
   SES is touched.

Everything else here is about the setup UI: the DNS records must be renderable,
verification must be refreshable, and failures must read like advice.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_auth import login, register

from app.models.domain import Domain
from app.services.domains import (
    DomainError,
    IdentityState,
    normalize,
    sender_domain_allowed,
    validate,
)

PAYLOAD = {
    "from": "noreply@acme.example",
    "to": ["receiver@example.com"],
    "subject": "Hello",
    "text_body": "Hello there",
}


class StubVerifier:
    """In-memory SES identity stand-in, so these tests never call AWS."""

    def __init__(self, *, verified=False, tokens=("tok1", "tok2", "tok3")):
        self.verified = verified
        self.tokens = tokens
        self.registered: list[str] = []
        self.removed: list[str] = []

    def register(self, domain):
        self.registered.append(domain)
        return IdentityState(exists=True, verified=self.verified, dkim_tokens=self.tokens)

    def check(self, domain):
        return IdentityState(exists=True, verified=self.verified, dkim_tokens=self.tokens)

    def remove(self, domain):
        self.removed.append(domain)


@pytest.fixture
def verifier(client):
    stub = StubVerifier()
    client.app.state.domain_verifier = stub
    return stub


def setup(client, email="owner@example.com", name="Owner"):
    org = register(client, email=email, name=name).json()["organization"]["id"]
    login(client, email=email)
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "Test"}).json()["key"]
    return org, {"X-API-Key": key}


# ------------------------------------------------------------------ validation


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ACME.example", "acme.example"),
        ("https://acme.example/", "acme.example"),
        ("  www.acme.example.  ", "acme.example"),
        ("mail.acme.example", "mail.acme.example"),
    ],
)
def test_normalize_accepts_what_people_paste(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["gmail.com", "yahoo.co.in", "outlook.com", "proton.me", "rediffmail.com"],
)
def test_public_mail_providers_are_refused_with_advice(raw):
    with pytest.raises(DomainError) as exc:
        validate(raw)
    assert exc.value.code == "domain_not_verifiable"
    assert "verify a domain you own" in exc.value.message.lower()


def test_email_address_is_rejected_with_a_specific_message():
    with pytest.raises(DomainError) as exc:
        validate("you@acme.example")
    assert exc.value.code == "domain_invalid"
    assert "without the part before the @" in exc.value.message


@pytest.mark.parametrize("raw", ["", "   ", "localhost", "acme", "acme..example", "-acme.example"])
def test_malformed_domains_are_rejected(raw):
    with pytest.raises(DomainError):
        validate(raw)


# ------------------------------------------------------------------- lifecycle


def test_register_returns_dkim_records_to_publish(client, verifier):
    org, _ = setup(client)
    created = client.post(f"/v1/organizations/{org}/domains", json={"domain": "acme.example"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["domain"] == "acme.example"
    assert body["status"] == "pending"
    assert verifier.registered == ["acme.example"]

    records = body["dns_records"]
    assert len(records) == 3
    assert records[0] == {
        "type": "CNAME",
        "name": "tok1._domainkey.acme.example",
        "value": "tok1.dkim.amazonses.com",
    }


def test_already_verified_domain_skips_pending(client, verifier):
    verifier.verified = True
    org, _ = setup(client)
    body = client.post(f"/v1/organizations/{org}/domains", json={"domain": "fast.example"}).json()
    assert body["status"] == "verified"
    assert body["verified_at"] is not None


def test_same_domain_cannot_be_claimed_by_two_tenants(client, verifier):
    first_org, _ = setup(client, "a@example.com", "A")
    assert (
        client.post(
            f"/v1/organizations/{first_org}/domains", json={"domain": "brand.example"}
        ).status_code
        == 201
    )

    second_org, _ = setup(client, "b@example.com", "B")
    clash = client.post(f"/v1/organizations/{second_org}/domains", json={"domain": "brand.example"})
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "domain_taken"
    # SES must not be touched for a claim we already know is invalid.
    assert verifier.registered == ["brand.example"]


def test_duplicate_within_one_tenant_is_a_conflict(client, verifier):
    org, _ = setup(client)
    assert (
        client.post(f"/v1/organizations/{org}/domains", json={"domain": "acme.example"}).status_code
        == 201
    )
    again = client.post(f"/v1/organizations/{org}/domains", json={"domain": "ACME.example"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "domain_exists"


def test_check_promotes_pending_to_verified(client, verifier):
    org, _ = setup(client)
    created = client.post(
        f"/v1/organizations/{org}/domains", json={"domain": "acme.example"}
    ).json()
    assert created["status"] == "pending"

    verifier.verified = True
    checked = client.post(f"/v1/organizations/{org}/domains/{created['id']}/check")
    assert checked.status_code == 200
    assert checked.json()["status"] == "verified"
    assert checked.json()["verified_at"] is not None


def test_check_reports_failure_when_identity_disappeared(client, verifier):
    org, _ = setup(client)
    created = client.post(
        f"/v1/organizations/{org}/domains", json={"domain": "acme.example"}
    ).json()

    class Vanished(StubVerifier):
        def check(self, domain):
            return IdentityState(exists=False, verified=False, error="identity not found")

    client.app.state.domain_verifier = Vanished()
    checked = client.post(f"/v1/organizations/{org}/domains/{created['id']}/check").json()
    assert checked["status"] == "failed"
    assert checked["last_error"] == "identity not found"


def test_delete_removes_row_and_identity(client, verifier):
    org, _ = setup(client)
    created = client.post(
        f"/v1/organizations/{org}/domains", json={"domain": "acme.example"}
    ).json()
    assert client.delete(f"/v1/organizations/{org}/domains/{created['id']}").status_code == 204
    assert verifier.removed == ["acme.example"]
    assert client.get(f"/v1/organizations/{org}/domains").json() == []


def test_member_can_read_but_not_write_domains(client, verifier):
    org, _ = setup(client)
    # A second user joining the organization as a plain member.
    register(client, "member@example.com", "Member").json()
    login(client, "member@example.com")
    from uuid import UUID

    from app.models import OrganizationMembership

    with Session(client.app.state.database_engine) as db:
        db.add(
            OrganizationMembership(
                organization_id=UUID(org),
                user_id=db.scalar(
                    select(__import__("app.models", fromlist=["User"]).User.id).where(
                        __import__("app.models", fromlist=["User"]).User.email
                        == "member@example.com"
                    )
                ),
                role="member",
            )
        )
        db.commit()

    assert client.get(f"/v1/organizations/{org}/domains").status_code == 200
    refused = client.post(f"/v1/organizations/{org}/domains", json={"domain": "acme.example"})
    assert refused.status_code == 404


def test_domains_are_invisible_across_tenants(client, verifier):
    first_org, _ = setup(client, "a@example.com", "A")
    created = client.post(
        f"/v1/organizations/{first_org}/domains", json={"domain": "acme.example"}
    ).json()

    second_org, _ = setup(client, "b@example.com", "B")
    assert client.get(f"/v1/organizations/{second_org}/domains").json() == []
    assert (
        client.post(f"/v1/organizations/{second_org}/domains/{created['id']}/check").status_code
        == 404
    )


# ------------------------------------------------------------- send-time gate


def test_send_is_refused_before_a_domain_is_verified(client, verifier):
    org, headers = setup(client)
    refused = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    assert refused.status_code == 403
    body = refused.json()["error"]
    assert body["code"] == "sender_domain_not_verified"
    assert "acme.example" in body["message"]


def test_send_is_refused_while_domain_is_only_pending(client, verifier):
    org, headers = setup(client)
    client.post(f"/v1/organizations/{org}/domains", json={"domain": "acme.example"})
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 403


def test_send_is_allowed_after_verification(client, verifier):
    org, headers = setup(client)
    created = client.post(
        f"/v1/organizations/{org}/domains", json={"domain": "acme.example"}
    ).json()
    verifier.verified = True
    client.post(f"/v1/organizations/{org}/domains/{created['id']}/check")
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202


def test_verifying_a_domain_does_not_authorise_another_tenant(client, verifier):
    first_org, _ = setup(client, "a@example.com", "A")
    created = client.post(
        f"/v1/organizations/{first_org}/domains", json={"domain": "acme.example"}
    ).json()
    verifier.verified = True
    client.post(f"/v1/organizations/{first_org}/domains/{created['id']}/check")

    _, other_headers = setup(client, "b@example.com", "B")
    assert client.post("/v1/emails", json=PAYLOAD, headers=other_headers).status_code == 403


def test_refused_send_does_not_consume_quota(client, verifier):
    org, headers = setup(client)
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 403
    usage = client.get("/v1/emails/usage", headers=headers).json()
    assert usage["used"]["emails"] == 0
    assert usage["used"]["recipients"] == 0
    assert usage["used"]["monthly_emails"] == 0


def test_subdomain_of_verified_apex_is_not_implicitly_verified(client, verifier):
    """Verifying acme.example must not authorise mail.acme.example."""
    org, headers = setup(client)
    created = client.post(
        f"/v1/organizations/{org}/domains", json={"domain": "acme.example"}
    ).json()
    verifier.verified = True
    client.post(f"/v1/organizations/{org}/domains/{created['id']}/check")

    sub = {**PAYLOAD, "from": "noreply@mail.acme.example"}
    assert client.post("/v1/emails", json=sub, headers=headers).status_code == 403


# ------------------------------------------------------------------------ unit


def test_sender_domain_allowed_reads_the_database(database_engine):
    from app.models.identity import User
    from app.security.passwords import hash_password
    from app.services.organizations import add_organization_with_owner

    with Session(database_engine) as db:
        user = User(
            name="Owner", email=f"{uuid4().hex[:8]}@example.com", password_hash=hash_password("x")
        )
        db.add(user)
        db.flush()
        org = add_organization_with_owner(db, name="Check", owner_user_id=user.id)
        db.flush()
        db.add_all(
            [
                Domain(organization_id=org.id, domain="ok.example", status="verified"),
                Domain(organization_id=org.id, domain="pending.example", status="pending"),
            ]
        )
        db.commit()

        assert sender_domain_allowed(db, org.id, "noreply@ok.example") is True
        assert sender_domain_allowed(db, org.id, "noreply@OK.example") is True
        assert sender_domain_allowed(db, org.id, "noreply@pending.example") is False
        assert sender_domain_allowed(db, org.id, "noreply@unknown.example") is False
        assert sender_domain_allowed(db, org.id, "not-an-address") is False
