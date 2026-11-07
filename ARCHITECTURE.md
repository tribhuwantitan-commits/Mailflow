# MailFlow architecture and roadmap

**Current implemented phase: Phase 4.** Phases 1–4 run with a network-free fake email provider. Real PostgreSQL integration validation is **pending**: the opt-in integration test was skipped because no PostgreSQL service/test URL was available. No real mail is sent; there is no SES, SMTP server, frontend, Redis/Celery, or deployment configuration.

## Implemented architecture (Phases 1–4)

MailFlow is a FastAPI modular monolith with SQLAlchemy models and Alembic migrations under `backend/`. The API stores email records and outbox jobs in one transaction; a separate, externally scheduled worker tick polls the database and calls the fake provider. PostgreSQL is the intended database; fast local API and migration tests use SQLite. The SQLite tests do **not*** establish PostgreSQL compatibility.

| Phase | Implemented scope | Migration |
| --- | --- | --- |
| **1 — foundation** | Environment settings, PostgreSQL engine configuration, FastAPI liveness/readiness (`SELECT 1`) checks, provider contract and in-memory fake. | `0001_initial` (empty baseline) |
| **2 — users and organizations** | Argon2id passwords, registration/login/logout, expiring and revocable opaque sessions, ownership/memberships and membership-scoped organization endpoints. | `0002_auth_orgs` |
| **3 — API keys and fake REST email** | Owner-managed organization API keys, API-key-only email submission/read/list, validation, tenant isolation, idempotent request handling, transactional message/outbox persistence and bounded fake-provider retries. | `0003_delivery` |
| **4 — worker hardening** | Atomic claims, renewable leases and completion fencing, expired-lease recovery, safe worker logging, aggregate status and manual failed-job requeue, plus opt-in PostgreSQL integration tests (not yet executed against PostgreSQL). | `0004_worker` |

### Current components

+- `app/main.py`: app factory, error responses, health checks, router mounting.
+- `app/api/auth.py`, `api/dependencies.py`, `api/organizations.py`: user session authentication and membership-scoped control plane. `api/keys.py` restricts API-key management to owners; `api/email_auth.py` separately authenticates `X-API-Key`; `api/emails.py` validates and scopes message operations.
+- `app/models/identity.py`, `organization.py`, `delivery.py`: users/sessions, organizations/memberships, and API keys/messages/outbox events. `app/db/ownership.py` registers the ORM owner-consistency guard. `app/services/organizations.py` pairs creation of an organization and its owner membership.
+- `app/providers/email.py`: provider-neutral `OutboundEmail`/`SubmissionResult`, fake provider, deterministic failure simulator and in-memory idempotent fake. `app/services/outbox.py`: worker claim, heartbeat, retry, status and recovery; run separately from the HTTP process.
+- `backend/alembic/versions/0001` through `0004`: versioned schema changes. `backend/tests/`: local regressions plus opt-in real-PostgreSQL integration coverage.

## Current HTTP contract

| Route | Authentication | Behavior |
| --- | --- | --- |
| `GET /health/live`, `GET /health/ready` | None | Process liveness and database readiness. |
| `POST /v1/auth/register`, `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me` | Public for register/login; token optional on logout; session required on me | Register a user/default owner organization; issue, revoke or inspect a session. |
| `GET /v1/organizations`, `POST /v1/organizations`, `GET /v1/organizations/{organization_id}` | User session | Membership-scoped list/detail; creation atomically establishes owner membership. |
| `POST /v1/organizations/{organization_id}/api-keys`, `GET /v1/organizations/{organization_id}/api-keys`, `POST /v1/organizations/{organization_id}/api-keys/{key_id}/revoke`, `DELETE /v1/organizations/{organization_id}/api-keys/{key_id}` | User session **and owner membership** | Create (raw key returned once), list metadata, revoke or delete a key. |
| `POST /v1/emails`, `GET /v1/emails`, `GET /v1/emails/{email_id}` | Active `X-API-Key` | Accept/list/read messages in that key's organization. A foreign ID returns `404`. |

Detailed request/response examples are in [backend/README.md](backend/README.md). `POST /v1/emails` accepts `from`, `to`, `subject`, optional `reply_to`, and at least one nonempty `text_body` or `html_body`. It rejects unknown fields/attachments; limits include 50 recipients, 100,000 characters per body and 200,000 serialized characters per request. Listing returns at most 100 most recent records. This is fake-provider acceptance only, never external delivery.

### Authentication and organization consistency

Passwords are Argon2id hashes. A 256-bit random opaque user session token is issued in the fixed-name `mailflow_access` HttpOnly, SameSite=Strict cookie; `Secure` is set in production. Only its SHA-256 verifier is stored. A supplied Bearer scheme takes precedence even if its credential is malformed or empty; non-Bearer Authorization schemes leave cookie authentication available. Inactive users cannot use sessions. Before introducing a browser frontend, add exact-Origin checks for state-changing cookie-authenticated requests, a CSRF token or equivalent verified custom-header defense, and credentialed CORS restricted to explicit trusted origins.

New organizations and matching owner memberships are staged together in a transaction. An ORM `before_flush` guard rejects inconsistent new rows, ownership/role/identity changes and owner-membership removal while the organization remains. Database constraints enforce FKs, valid membership roles, key uniqueness and **at most one** owner membership, but cannot declaratively require exactly one matching cross-table owner row. Direct SQL bypasses the ORM guard; a database trigger would be required if direct writers need that protection.

API keys are random 256-bit values prefixed `mfk_`; only SHA-256 verifiers are stored. A key belongs to one organization; revocation or inactivity blocks its use. Email endpoints derive tenant scope from the key, not request parameters. Key deletion leaves existing messages intact by setting their `api_key_id` to null. Protect database credentials and stored message content; no API-key or message-body logging is intended.

### Persistence, retries and limitations

`email_messages` stores organization, sender, recipient JSON, subject, text/HTML bodies, status, provider acceptance metadata, attempt count, timestamps and safe error code. `outbox_events` holds one unique event per message with next-attempt time, state, lease expiry and random per-claim lease token. The API commits both rows atomically. An optional `Idempotency-Key` is unique per organization; replay with identical content returns the existing message, while changed content returns `409`.

The scheduled worker atomically claims a due/expired job with conditional UPDATE, commits the claim, and calls the provider outside that transaction. A 120-second lease is renewed every 30 seconds. Conditional renewal and completion use the lease token, so a stale worker cannot overwrite a replacement worker's database result. A transient or unknown provider failure is retried with capped exponential backoff up to five attempts; permanent errors stop immediately. Crash-consumed attempts count toward the cap. Failed records remain observable; privileged operators may explicitly reset and requeue a failed email. `sent` means provider acceptance, **not** delivered; no delivery/bounce events or recipient-level statuses exist. Worker `--status` reports aggregate pending/due/leased/failed counts; its logs include safe event/email IDs and outcome codes only. The due-work query has `(state, next_attempt_at)` and `(state, lease_until)` indexes.

Processing is **at least once**, not exactly once. A crash after provider acceptance but before committing success, or a pause/failed heartbeat longer than the lease, can cause another provider call. Lease fencing prevents stale database completion, not external side effects. Every attempt passes the stable email UUID as a provider-neutral idempotency key; `IdempotentFakeEmailProvider` models a cooperating provider but its dedupe state is only in-memory. A future real adapter must negotiate durable provider-side idempotency. Rate limiting, encryption-at-rest policy, payload retention/cleanup, domain checks, suppression, webhooks and delivery events are **not implemented**.

## PostgreSQL validation status

`backend/tests/test_postgres_integration.py` is an **opt-in, unvalidated-on-PostgreSQL test** requiring `MAILFLOW_TEST_POSTGRES_URL` pointing to a dedicated test database with schema-create permission. It creates/drops a random schema, exercises Alembic, API flows and concurrent worker claims. Without a live PostgreSQL URL it skips. SQLite migration upgrade/downgrade/re-upgrade and API tests passed, but PostgreSQL compatibility remains **pending**; do not interpret the presence of the test as a successful PostgreSQL run. See [DEVELOPMENT.md](DEVELOPMENT.md).

## Future roadmap (planned, not implemented)

| Phase | Planned scope |
| --- | --- |
| **Phase 5 — Domain management and sender verification** | Organization-scoped domain registration, DNS verification, sender authorization and tests; no provider integration implied. |
| **Phase 6 — Amazon SES integration and delivery events** | Real provider adapter, verified-domain coordination, authenticated/deduplicated delivery/bounce/complaint events and suppression behavior. Provider-side replay protection needs explicit evaluation. |
| **Phase 7 — SMTP submission** | Separate TLS-required SMTP ingress using the existing tenant/auth and send pipeline; validate MIME and relay safety. |
| **Phase 8 — Production readiness** | Operational security, rate limits, retention, monitoring, backup/restore, load validation and deployment plans as requirements mature. |

No work on Phases 5–8 is claimed here; PostgreSQL validation is a prerequisite to treating Phase 4 as operationally validated.
