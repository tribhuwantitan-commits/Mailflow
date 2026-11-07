"""Registration, login, token, and authentication regression tests."""

from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.config import AUTH_COOKIE_NAME, Settings
from app.main import create_app
from app.models import AuthSession, Organization, OrganizationMembership, User
from app.security.tokens import hash_access_token

TEST_PASSWORD = "Correct horse battery staple 2026!"


def register(client, email: str = "alice@example.com", name: str = "Alice"):
    return client.post(
        "/v1/auth/register",
        json={"name": name, "email": email, "password": TEST_PASSWORD},
    )


def login(client, email: str = "alice@example.com", password: str = TEST_PASSWORD) -> str:
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[AUTH_COOKIE_NAME].value


def test_openapi_documents_cookie_and_bearer_authentication(client) -> None:
    schema = client.get("/openapi.json").json()
    security_schemes = schema["components"]["securitySchemes"]

    assert security_schemes["BearerAuth"] == {"type": "http", "scheme": "bearer"}
    assert security_schemes["SessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": AUTH_COOKIE_NAME,
    }
    assert "auth_cookie_name" not in Settings.model_fields
    protected_security = schema["paths"]["/v1/auth/me"]["get"]["security"]
    assert {"BearerAuth": []} in protected_security
    assert {"SessionCookie": []} in protected_security


def test_registration_creates_hashed_user_default_organization_and_owner_membership(
    client,
    database_engine,
) -> None:
    response = register(client, email="ALICE@Example.com")

    assert response.status_code == 201
    body = response.json()
    user_data = body["user"]
    organization_data = body["organization"]
    assert user_data["email"] == "alice@example.com"
    assert "password" not in body
    assert "password_hash" not in body
    assert "set-cookie" not in response.headers
    assert TEST_PASSWORD not in response.text
    assert organization_data["name"] == "Alice's Organization"
    assert organization_data["role"] == "owner"
    assert organization_data["owner_user_id"] == user_data["id"]

    with Session(database_engine) as db:
        user = db.get(User, UUID(user_data["id"]))
        organization = db.get(Organization, UUID(organization_data["id"]))
        membership = db.get(
            OrganizationMembership,
            (UUID(organization_data["id"]), UUID(user_data["id"])),
        )
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != TEST_PASSWORD
        assert organization is not None
        assert membership is not None
        assert organization.owner_user_id == membership.user_id
        assert membership.role == "owner"
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Organization)) == 1


def test_duplicate_email_registration_is_case_insensitive_and_does_not_create_partial_org(
    client,
    database_engine,
) -> None:
    assert register(client).status_code == 201

    response = register(client, email="ALICE@EXAMPLE.COM")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "email_already_registered",
            "message": "A user with this email already exists.",
        }
    }
    with Session(database_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Organization)) == 1


def test_registration_validates_email_and_password_without_echoing_secrets(client) -> None:
    submitted_password = "tiny-pass"
    short_password = client.post(
        "/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": submitted_password},
    )
    invalid_email = client.post(
        "/v1/auth/register",
        json={
            "name": "Alice",
            "email": "not-an-email",
            "password": TEST_PASSWORD,
        },
    )

    assert short_password.status_code == invalid_email.status_code == 422
    assert (
        short_password.json()
        == invalid_email.json()
        == {"error": {"code": "validation_error", "message": "Request validation failed."}}
    )
    assert submitted_password not in short_password.text
    assert "not-an-email" not in invalid_email.text


def test_login_sets_httponly_cookie_and_authenticates_me(client, database_engine) -> None:
    assert register(client).status_code == 201

    response = client.post(
        "/v1/auth/login",
        json={"email": "ALICE@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["user"]["email"] == "alice@example.com"
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert "access_token" not in response.json()
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header
    assert "Max-Age=1800" in cookie_header

    cookie = SimpleCookie()
    cookie.load(cookie_header)
    token = cookie[AUTH_COOKIE_NAME].value
    assert token not in response.text
    me_response = client.get("/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.headers["cache-control"] == "no-store"
    assert me_response.json()["email"] == "alice@example.com"

    with Session(database_engine) as db:
        auth_session = db.scalar(select(AuthSession))
        assert auth_session is not None
        assert auth_session.token_hash == hash_access_token(token)
        assert auth_session.token_hash != token
        assert len(auth_session.token_hash) == 64


def test_production_login_cookie_is_secure(database_engine) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
    )
    app = create_app(settings, database_engine=database_engine)

    with TestClient(app) as client:
        assert register(client).status_code == 201
        response = client.post(
            "/v1/auth/login",
            json={"email": "alice@example.com", "password": TEST_PASSWORD},
        )
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        token = cookie[AUTH_COOKIE_NAME].value
        logout_response = client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert "Secure" in logout_response.headers["set-cookie"]
        assert f'{AUTH_COOKIE_NAME}=""' in logout_response.headers["set-cookie"]


def test_invalid_credentials_have_same_safe_response(client) -> None:
    assert register(client).status_code == 201

    wrong_password = client.post(
        "/v1/auth/login",
        json={"email": "alice@example.com", "password": "Wrong password 123!"},
    )
    unknown_user = client.post(
        "/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Wrong password 123!"},
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"
    assert "Wrong password" not in wrong_password.text
    assert "set-cookie" not in wrong_password.headers


def test_inactive_user_cannot_login_or_use_an_existing_session(client, database_engine) -> None:
    assert register(client).status_code == 201
    token = login(client)

    with Session(database_engine) as db:
        user = db.scalar(select(User).where(User.email == "alice@example.com"))
        assert user is not None
        user.is_active = False
        db.commit()

        inactive_login = client.post(
            "/v1/auth/login",
            json={"email": "alice@example.com", "password": TEST_PASSWORD},
        )
        existing_session = client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert inactive_login.status_code == 401
        assert inactive_login.json()["error"]["code"] == "invalid_credentials"
        assert "set-cookie" not in inactive_login.headers
        assert existing_session.status_code == 401
        assert existing_session.json()["error"]["code"] == "authentication_required"
        with Session(database_engine) as db:
            assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_corrupted_stored_password_hash_fails_closed(client, database_engine) -> None:
    assert register(client).status_code == 201

    with Session(database_engine) as db:
        user = db.scalar(select(User).where(User.email == "alice@example.com"))
        assert user is not None
        user.password_hash = "not-a-valid-argon2-hash"
        db.commit()

        response = client.post(
            "/v1/auth/login",
            json={"email": "alice@example.com", "password": TEST_PASSWORD},
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
        assert "set-cookie" not in response.headers
        with Session(database_engine) as db:
            assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_bearer_token_takes_precedence_over_cookie(client) -> None:
    assert register(client, email="alice@example.com", name="Alice").status_code == 201
    alice_token = login(client, email="alice@example.com")
    assert register(client, email="bob@example.com", name="Bob").status_code == 201
    bob_token = login(client, email="bob@example.com")

    bearer_wins = client.get(
        "/v1/auth/me",
        headers={
            "Cookie": f"{AUTH_COOKIE_NAME}={alice_token}",
            "Authorization": f"Bearer {bob_token}",
        },
    )
    invalid_bearer_wins = client.get(
        "/v1/auth/me",
        headers={
            "Cookie": f"{AUTH_COOKIE_NAME}={alice_token}",
            "Authorization": "Bearer invalid-token",
        },
    )

    assert bearer_wins.status_code == 200
    assert bearer_wins.json()["email"] == "bob@example.com"
    assert invalid_bearer_wins.status_code == 401
    assert invalid_bearer_wins.json()["error"]["code"] == "authentication_required"


@pytest.mark.parametrize(
    ("authorization", "cookie_authenticates"),
    [
        ("Bearer", False),
        ("Bearer ", False),
        ("Bearer   ", False),
        ("bEaReR\t", False),
        ("Bearer first second", False),
        ("Bearer\tfirst\tsecond", False),
        ("Bearer invalid-token", False),
        ("Basic opaque", True),
    ],
)
def test_authorization_precedence_on_protected_endpoints_and_logout(
    client, database_engine, authorization, cookie_authenticates
) -> None:
    assert register(client).status_code == 201
    token = login(client)
    headers = {"Authorization": authorization, "Cookie": f"{AUTH_COOKIE_NAME}={token}"}

    for path in ("/v1/auth/me", "/v1/organizations"):
        response = client.get(path, headers=headers)
        assert response.status_code == (200 if cookie_authenticates else 401)
        if not cookie_authenticates:
            assert response.json()["error"]["code"] == "authentication_required"

            logout_response = client.post("/v1/auth/logout", headers=headers)
            assert logout_response.status_code == 204
            assert SimpleCookie(logout_response.headers["set-cookie"])[AUTH_COOKIE_NAME].value == ""
            with Session(database_engine) as db:
                session = db.scalar(
                    select(AuthSession).where(AuthSession.token_hash == hash_access_token(token))
                )
                assert session is not None
                assert (session.revoked_at is not None) == cookie_authenticates

                # Logout clears the browser cookie regardless, but must not revoke a valid
                # cookie's session when an explicit invalid Bearer credential was selected.
                after = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
                assert after.status_code == (401 if cookie_authenticates else 200)


def test_missing_and_invalid_tokens_are_rejected_consistently(client) -> None:
    missing = client.get("/v1/auth/me")
    invalid = client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer definitely-not-a-valid-token"},
    )
    protected_org_list = client.get("/v1/organizations")

    assert missing.status_code == invalid.status_code == protected_org_list.status_code == 401
    assert missing.json() == invalid.json() == protected_org_list.json()
    assert missing.json()["error"]["code"] == "authentication_required"
    assert missing.headers["www-authenticate"] == "Bearer"
    assert missing.headers["cache-control"] == "no-store"


def test_expired_and_logged_out_tokens_cannot_be_used(client, database_engine) -> None:
    assert register(client).status_code == 201
    token = login(client)

    with Session(database_engine) as db:
        auth_session = db.scalar(select(AuthSession))
        assert auth_session is not None
        auth_session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        expired = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert expired.status_code == 401

        # A fresh login creates a usable session that logout then revokes server-side.
        token = login(client)
        logout_response = client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        after_logout = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert logout_response.status_code == 204
        assert f'{AUTH_COOKIE_NAME}=""' in logout_response.headers["set-cookie"]
        cleared_cookie = SimpleCookie()
        cleared_cookie.load(logout_response.headers["set-cookie"])
        assert cleared_cookie[AUTH_COOKIE_NAME].value == ""
        assert cleared_cookie[AUTH_COOKIE_NAME]["max-age"] == "0"
        assert cleared_cookie[AUTH_COOKIE_NAME]["path"] == "/"
        assert cleared_cookie[AUTH_COOKIE_NAME]["httponly"]
        assert cleared_cookie[AUTH_COOKIE_NAME]["samesite"] == "strict"
        assert after_logout.status_code == 401
        with Session(database_engine) as db:
            revoked_session = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == hash_access_token(token))
            )
            assert revoked_session is not None
            assert revoked_session.revoked_at is not None


def test_logout_clears_cookie_when_session_store_is_unavailable(client) -> None:
    assert register(client).status_code == 201
    login(client)

    class FailingSession:
        def scalar(self, *_args, **_kwargs):
            raise SQLAlchemyError("database unavailable")

        def rollback(self) -> None:
            return None

    def failing_db_dependency():
        yield FailingSession()

    client.app.dependency_overrides[get_db_session] = failing_db_dependency
    response = client.post("/v1/auth/logout")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_unavailable"
    cleared_cookie = SimpleCookie()
    cleared_cookie.load(response.headers["set-cookie"])
    assert cleared_cookie[AUTH_COOKIE_NAME].value == ""
    assert cleared_cookie[AUTH_COOKIE_NAME]["max-age"] == "0"
    assert cleared_cookie[AUTH_COOKIE_NAME]["httponly"]
