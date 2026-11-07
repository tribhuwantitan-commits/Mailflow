# MailFlow backend (implemented through Phase 4)

The FastAPI backend now includes:

- Phase 1 liveness/readiness checks and the fake, network-free email provider;
- email/password registration and login using Argon2id password hashes;
- expiring, revocable opaque access tokens issued through the fixed-name `mailflow_access` HttpOnly cookie (or accepted as a Bearer token);
- user, authentication-session, organization, and organization-membership models;
- default organization creation during registration; and
- membership-scoped organization listing, creation, and detail access;
- Phase 3 owner-managed organization API keys and API-key-authenticated REST email endpoints with transactional outbox; and
- Phase 4 fenced worker leases, aggregate status and manual failed-job recovery.

The fake provider never sends real mail. Sender-domain management/verification, SES, SMTP, frontend, Redis/Celery, and deployment are planned only. **PostgreSQL integration validation is pending**; local SQLite tests do not establish PostgreSQL compatibility.

For the Arena → private GitHub → Windows Server RDP workflow, Docker Desktop compatibility note, security details, and test guidance, see [`../DEVELOPMENT.md`](../DEVELOPMENT.md).

## Run on Windows Server RDP

From this directory, with Python 3.11+ and PostgreSQL available:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Edit DATABASE_URL in .env to match the local PostgreSQL role/database.
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Migration chain: Phase 1 `0001_initial` baseline; Phase 2 `0002_auth_orgs`; Phase 3 `0003_delivery`; Phase 4 `0004_worker`. The PostgreSQL integration test has not run against a live PostgreSQL service. Do not commit `.env` or real credentials. For local API examples and environment-specific cookie behavior, see [`../DEVELOPMENT.md`](../DEVELOPMENT.md).

## Phase 2 endpoints

- `POST /v1/auth/register` — create the user and default owner organization atomically.
- `POST /v1/auth/login` — verify credentials and set an expiring HttpOnly access-token cookie; the JSON response contains only public user fields.
- `POST /v1/auth/logout` — revoke the presented session and clear the cookie.
- `GET /v1/auth/me` — return the authenticated user's public profile.
- `GET /v1/organizations` — list only organizations where the user has a membership.
- `POST /v1/organizations` — create an organization owned by the authenticated user.
- `GET /v1/organizations/{organization_id}` — return details only to a member; foreign IDs return the same not-found response.

The generated OpenAPI schema documents both the Bearer token and HttpOnly session-cookie security schemes on protected operations.

## Phase 3 — API keys and email submission

Use your Phase 2 session cookie (or user Bearer session) to manage keys. Only
organization **owners** can create, list, revoke, or delete keys; members cannot.
`POST /v1/organizations/{organization_id}/api-keys` with `{"name":"Production"}`
returns `201` with `{ "id": "...", "organization_id": "...", "name": "Production",
"is_active": true, "revoked_at": null, "created_at": "...", "key": "mfk_..." }`.
Save the `key` securely: subsequent `GET /v1/organizations/{organization_id}/api-keys`
returns metadata only, never the raw key or stored hash. Use
`POST /v1/organizations/{organization_id}/api-keys/{key_id}/revoke` to revoke
(idempotent) or `DELETE /v1/organizations/{organization_id}/api-keys/{key_id}`
to delete. Deletion preserves submitted emails; their key reference becomes null.

The email API requires `X-API-Key: mfk_...` (not session cookies or user Bearer
headers). Example:

```sh
curl -X POST https://your-host/v1/emails \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: mfk_YOUR_KEY' \
  -H 'Idempotency-Key: order-123' \
  -d '{"from":"sender@example.com","to":["recipient@example.com"],"subject":"Hello","text_body":"Hello!","reply_to":"support@example.com"}'
```

`202 Accepted` returns `{ "id": "...", "organization_id": "...", "from":
"sender@example.com", "to": ["recipient@example.com"], "subject": "Hello",
"text_body": "Hello!", "html_body": null, "reply_to": "support@example.com",
"status": "accepted", "provider": null, "provider_message_id": null,
"attempt_count": 0, "error_code": null, "created_at": "...", "updated_at": "..." }`.
`GET /v1/emails/{email_id}` returns the same shape; `GET /v1/emails` returns
up to 100 latest records for the key's organization. A foreign ID returns 404.
A repeated idempotency key with identical content returns the original message;
changed content returns 409. Provide a unique key per logical send.

Bodies may be text, HTML, or both (at least one required); maximum 50 recipients,
100,000 characters per body, and 200,000 serialized characters per request.
Attachments and other unknown input fields are rejected. Do not put secrets in
subjects/bodies; message content is stored in the database and returned by the API.

The API persists messages and outbox events together, but does **not** submit
inline. Run `python -m app.services.outbox` from `backend/` for one bounded worker
tick, periodically via an external scheduler. It uses only the fake provider; it
never sends real email. `sent` means fake-provider acceptance, not delivery.

## Phase 4 worker operations and validation status

Run `python -m app.services.outbox` from this directory for one bounded fake-provider
worker tick under an external scheduler. `--status` prints aggregate pending/due/
leased/failed counts; `--requeue EMAIL_UUID` explicitly resets a failed job's
attempt budget. Investigate failures before requeueing: it may cause another
provider submission. Claims use 120-second renewable leases and random fencing
tokens; a long pause or failed heartbeat can still allow duplicate external
provider calls. The fake provider never sends mail and its optional idempotent
test double deduplicates only in memory. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

Real PostgreSQL integration validation is **pending**. With a **dedicated test
database** and schema-create permission, set `MAILFLOW_TEST_POSTGRES_URL` and run
`python -m pytest -q tests/test_postgres_integration.py`. The test skips when
the URL is absent. Do not use a production database.

**Planned, not implemented:** Phase 5 domain management and sender verification;
Phase 6 Amazon SES integration and delivery events; Phase 7 SMTP submission;
Phase 8 production readiness.
