# Development guide

**Current implemented stage:** Phase 4 worker reliability hardening (PostgreSQL integration validation pending). AI-assisted coding happens in the Arena.ai sandbox and the private GitHub repository is the permanent source of truth. Windows Server over RDP is the intended host for a future PostgreSQL validation run; such a run has not been completed here. A personal PC is not part of the workflow.

Implemented: Phase 1 FastAPI/SQLAlchemy/Alembic, health checks and fake provider; Phase 2 sessions and membership-scoped organizations; Phase 3 owner-managed API keys, REST email submission and transactional outbox; Phase 4 fenced worker leases, retry recovery and operator status. The fake provider sends no real mail. There is still no frontend, verified sender-domain management, SES integration, SMTP listener, Redis/Celery, or deployment setup. PostgreSQL integration testing is pending.

## 1. Work and file-transfer workflow

### Normal path: Arena → private GitHub → Windows Server RDP

1. Make AI-assisted changes in the Arena.ai repository sandbox on the active working branch.
2. Use the private GitHub repository as the permanent source of truth. Review and push changes through the repository's normal Git workflow; do not treat an RDP copy as canonical.
3. From the Windows Server RDP session, clone or pull the branch/revision to be tested. Use the organization's approved GitHub sign-in/credential manager. Never put a GitHub token in a command URL, source file, `.env`, ZIP file, or chat.
4. Run migrations, tests, and the application on the Windows Server. The server is the execution/integration-test machine.
5. If testing reveals a code change, make it in Arena/GitHub and refresh the RDP test copy. Avoid fixes that exist only on the server.

Example PowerShell commands; GitHub should prompt through the approved credential mechanism if authentication is needed:

```powershell
$RepoUrl = Read-Host "Private Git repository URL"
$BranchToTest = Read-Host "Branch to test"
git clone $RepoUrl C:\MailFlow
Set-Location C:\MailFlow
git fetch origin
git switch --track "origin/$BranchToTest"
git pull
```

For an existing checkout, skip `git clone` and switch/pull the approved branch. Do not embed a password or access token in the repository URL. Use the approved Git credential manager or SSH setup.

### Fallback: ZIP export → TransferNow → Windows Server RDP

Use this only when the RDP server cannot pull from GitHub or a particular snapshot needs to be transferred:

1. Export a source-only ZIP from Arena and identify its revision/branch in the filename or transfer note.
2. Inspect the archive. Exclude `.env`, credentials, certificates, `.venv`, Python caches, test databases, logs, and local state. Do not include AWS credentials or real customer data.
3. Transfer using the approved TransferNow process; restrict the link to authorized recipients and use expiry/access controls where available and allowed. Download and extract inside the RDP session to a separate test directory.
4. Keep GitHub as the permanent source of truth. Treat the ZIP as a disposable test snapshot, then delete it according to the organization's retention policy.

Do not route source through a personal PC. Configure local-only settings directly on the Windows Server; never transfer secrets in a ZIP or through TransferNow.

## 2. Windows Server and Docker compatibility

**Docker Desktop is not supported on Windows Server.** I checked Docker's official Windows installation guide and Windows FAQ on 2026-11-04; Docker states that Desktop is unsupported on Windows Server versions (the guide gives Server 2019 and 2022 as examples) and lists desktop Windows versions instead:

- [Docker Desktop — Install on Windows (system requirements)](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Desktop Windows FAQ — Can I run Docker Desktop on Windows Server?](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/windowsfaqs/#can-i-run-docker-desktop-on-windows-server)

Do not make this project depend on Docker Desktop on the RDP server. Phases 1–4 do not need Docker or Redis. Run Python natively on Windows Server and install PostgreSQL as a native Windows service using the [official PostgreSQL Windows download page](https://www.postgresql.org/download/windows/). If server policy does not allow a local PostgreSQL install, use an approved PostgreSQL host reachable over TLS and a restricted network path.

Redis is not required in Phase 4. If a later phase introduces Celery/Redis, prefer an approved managed Redis service or a small Linux VM reachable over a private network. WSL2 is only an option if the exact Windows Server version, virtualization settings, and organizational policy support it; confirm with the server administrator. Do not depend on an unofficial native Windows Redis port.

## 3. Windows Server prerequisites and PostgreSQL

- RDP access to the Windows Server and permission to install/use Python and PostgreSQL, or access to an approved remote PostgreSQL instance.
- 64-bit Python 3.11 or newer and `pip`. No Node.js is required.
- Git for Windows for the normal clone/pull path; ZIP export is the fallback.

Install PostgreSQL on the Windows Server and leave the PostgreSQL service configured to start normally. `pgAdmin` is optional; `psql` is sufficient. Create a local application role/database with a unique local-only password, for example in `psql` as the PostgreSQL administrator:

```sql
CREATE ROLE mailflow WITH LOGIN PASSWORD 'replace-with-a-local-only-password';
CREATE DATABASE mailflow OWNER mailflow;
```

If the password contains URL-reserved characters, URL-encode them in `DATABASE_URL`. Do not reuse the password for GitHub, TransferNow, or a production service.

Keep the API bound to `127.0.0.1` for RDP-local testing. Do not open a Windows Firewall port or bind the API to all network interfaces unless remote access is explicitly required and approved.

## 4. Set up and configure the backend

The following PowerShell commands assume the checkout is at `C:\MailFlow`. Run them from `backend` so `.env` and Alembic configuration are found:

```powershell
Set-Location C:\MailFlow\backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
notepad .env
```

Set local values in `.env`:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://mailflow:your-local-password@127.0.0.1:5432/mailflow
DATABASE_CONNECT_TIMEOUT_SECONDS=5
AUTH_TOKEN_EXPIRE_MINUTES=30
```

`.env` is ignored by Git. Do not copy it into Arena, GitHub, a source ZIP, or TransferNow. The example URL is local-only and must be replaced with the actual local PostgreSQL password. `AUTH_TOKEN_EXPIRE_MINUTES` defaults to 30 and is bounded to 5–1440 minutes.

Passwords must be 12–128 characters. The service uses Argon2id with per-password salts; it never stores plaintext passwords. Email addresses are validated and normalized to lowercase for account uniqueness.

Login tokens are random, opaque 256-bit values. Only a SHA-256 verifier is stored in `auth_sessions`; the raw token is sent in the fixed-name `mailflow_access` HttpOnly, SameSite=Strict cookie, not in the JSON response. The cookie name is a code constant, not a configurable setting, so runtime and OpenAPI cannot diverge. `Authorization: Bearer` is also accepted and takes precedence over a cookie; an empty or malformed explicit Bearer credential does not fall back to a valid cookie on protected endpoints or logout. Non-Bearer Authorization schemes leave cookie authentication available. Logout always clears the cookie but only revokes the selected credential. Cookies are marked `Secure` when `APP_ENV=production`; local HTTP testing uses `APP_ENV=development`. Inactive users cannot log in or use existing sessions, and invalid/corrupted stored password hashes fail closed with the generic login error. No static token-signing secret is required for this database-backed token design. Keep database credentials and all local secrets in environment configuration only.

## 5. Migrations and running the service

Phase 1's `0001_initial` is an empty baseline; Phase 2 `0002_auth_orgs` adds users/sessions/organizations/memberships; Phase 3 `0003_delivery` adds API keys, email messages and outbox events; Phase 4 `0004_worker` adds lease fencing and due-work indexes. PostgreSQL execution of this chain remains pending.

Apply and inspect migrations from `backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic history
```

Then run the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open these from a browser inside the RDP session:

- `http://127.0.0.1:8000/health/live` — liveness, independent of PostgreSQL.
- `http://127.0.0.1:8000/health/ready` — runs `SELECT 1` against the configured PostgreSQL database.
- `http://127.0.0.1:8000/docs` — generated API/OpenAPI documentation.

Stop the server with `Ctrl+C`. Do not run migrations against a production/shared database from this development workflow.

## 6. Implemented API behavior (Phases 2–4)

All endpoints are under `/v1`:

| Endpoint | Authentication | Behavior |
| --- | --- | --- |
| `POST /v1/auth/register` | Public | Accepts `name`, `email`, `password`; creates the user, default `"'s Organization"`, and owner membership in one transaction. Returns public user/organization fields; does not auto-login. Duplicate normalized email returns `409`. |
| `POST /v1/auth/login` | Public | Accepts `email`, `password`; uses a generic `401` for unknown email and wrong password. Sets the expiring HttpOnly cookie. JSON contains public user fields only. |
| `POST /v1/auth/logout` | Token optional | Revokes the presented session when valid and clears the cookie. |
| `GET /v1/auth/me` | Required | Returns only the authenticated user's ID, name, email, and creation time. |
| `GET /v1/organizations` | Required | Lists only organizations with a membership for the authenticated user. |
| `POST /v1/organizations` | Required | Creates an organization with the authenticated user as owner and inserts the owner membership atomically. |
| `GET /v1/organizations/{organization_id}` | Required | Requires a membership; a foreign/nonexistent organization returns the same `404` response. |

Example registration body:

```json
{
 "name": "Alice Example",
 "email": "alice@example.com",
 "password": "a-long-unique-passphrase"
}
```

Example organization creation body:

```json
{"name": "Transactional Mail"}
```

Phase 3 additionally exposes owner-only key creation/list/revocation/deletion at `/v1/organizations/{organization_id}/api-keys` and API-key-only `POST /v1/emails`, `GET /v1/emails`, and `GET /v1/emails/{email_id}`. See [backend/README.md](backend/README.md) for examples. Phase 4 changes worker reliability, not the HTTP contract. The generated OpenAPI schema declares `BearerAuth` and `SessionCookie` schemes on user-protected endpoints and `EmailAPIKey` on email endpoints. Authentication and validation errors use a safe envelope such as `{"error":{"code":"authentication_required","message":"Authentication is required."}}`. Request validation details are intentionally not echoed, so submitted passwords are not returned in error bodies. Registration and login responses never include password hashes or a JSON access-token field.

## 7. Automated tests and quality checks

Run the official test and quality commands on the Windows Server over RDP. The same offline suite can be run in Arena for quick feedback, but it does not replace the RDP/PostgreSQL check:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests alembic
.\.venv\Scripts\python.exe -m ruff format --check app tests alembic
.\.venv\Scripts\python.exe -m pip check
```

The test suite covers:

- Phase 1 health endpoints, environment settings, database-engine configuration, fake provider, and migration baseline;
- registration, normalized duplicate-email rejection, input validation, and default organization/owner membership;
- Argon2id hashing and responses that omit plaintext passwords/password hashes;
- successful/invalid/inactive login, corrupt password-hash handling, token expiry/revocation, Bearer-versus-cookie precedence, and cookie flags/clearing (including database-error logout);
- missing/invalid token rejection and protected endpoint access;
- organization creation/listing/ownership, ORM rejection of inconsistent owner writes, and cross-organization IDOR attempts; and
- API key lifecycle, fake email submission, tenant isolation, idempotency, transactional outbox, temporary/permanent failures and retry limits;
- worker concurrency, stale-lease fencing, crash recovery, stable provider idempotency ID, manual requeue and status; and
- applying, inspecting, downgrading, and reapplying the Alembic migration chain through `0004_worker`.

Default automated API tests use SQLite; the migration regression uses a disposable SQLite file. PostgreSQL integration validation remains **pending**: the opt-in test skips when `MAILFLOW_TEST_POSTGRES_URL` is absent, and no PostgreSQL service was available in the sandbox. On a dedicated PostgreSQL test database, run the opt-in test described below, inspect `alembic current`, and confirm `/health/ready` before claiming PostgreSQL compatibility.

The current Starlette release emits a deprecation warning when its `TestClient` falls back to the standard `httpx` package. Tests still pass; MailFlow does not depend on `httpx2`.

## 8. Security and current limitations

- Auth uses 256-bit random opaque tokens; only SHA-256 token hashes are stored. Logout revokes a session, and tokens expire after the configured interval.
- Cookies remain HttpOnly and SameSite Strict; production-mode cookies are Secure and production deployments require HTTPS. SameSite is not the complete CSRF defense: before adding a browser frontend, enforce an exact allowed-Origin policy for state-changing cookie-authenticated requests, add a CSRF token or equivalent verified custom-header defense, and restrict credentialed CORS to explicit trusted origins (never `*`).
- Password hashes use Argon2id. Unknown-email login attempts perform dummy Argon2 work and return the same error as a wrong password.
- Organization list/detail queries require a membership join; foreign IDs do not reveal whether an organization exists. Both organization-creation paths use one transactional helper, and a SQLAlchemy `before_flush` guard requires a matching owner membership on insert while rejecting later owner-ID, membership-role/identity, or owner-membership deletion changes.
- The database enforces foreign keys, valid membership roles, membership-key uniqueness, and at most one owner membership. It cannot declaratively enforce exactly one matching owner row across these two tables; privileged raw SQL can bypass the ORM guard. Any future ownership transfer needs a dedicated atomic implementation, tests, and a database trigger if raw SQL must also be constrained.
- Validation errors do not echo request values. Auth responses do not include password hashes or JSON access tokens. The application does not log passwords or raw tokens.
- Email verification, password reset, MFA, login rate limiting, member invitations/role management, and scheduled cleanup of expired auth-session rows are not implemented yet. User deletion and ownership transfer are also not exposed.
- REST email acceptance and the outbox are implemented. The provider is selected with `MAIL_PROVIDER`: `fake` (default, sends no real mail) or `ses` (real Amazon SES `SendEmail`). Sender-domain management, delivery-event ingestion, SMTP submission, frontend, Redis/Celery and deployment are **not** implemented. `status=sent` means the provider accepted the message, not that the recipient server delivered it. Message bodies are stored in the database; retention/cleanup and rate limiting are not implemented. PostgreSQL integration validation is pending for the pooled Neon endpoint.

**Planned only:** sender-domain management and verification, delivery-event ingestion (SNS/SQS), open/click tracking, the user dashboard, SMTP submission, production access. See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/DELIVERY-EVENTS.md](docs/DELIVERY-EVENTS.md),
[docs/DASHBOARD-PLAN.md](docs/DASHBOARD-PLAN.md),
[docs/DOMAIN-VERIFICATION.md](docs/DOMAIN-VERIFICATION.md),
[docs/TRANSACTIONAL-VS-MARKETING.md](docs/TRANSACTIONAL-VS-MARKETING.md),
[docs/COMPETITOR-BENCHMARKS.md](docs/COMPETITOR-BENCHMARKS.md) and
[docs/LAUNCH-CHECKLIST.md](docs/LAUNCH-CHECKLIST.md) for scope, limitations and sequencing.
Do not treat these phases as implemented.

## Amazon SES setup and verification

The SES adapter is selected with `MAIL_PROVIDER=ses` and configured by `AWS_REGION`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `SES_FROM_EMAIL` and optionally
`SES_CONFIGURATION_SET` (see `backend/.env.example`). Two helper scripts exist:

```bash
cd backend
python -m app.scripts.check_ses --offline   # validate .env only, no AWS calls
python -m app.scripts.check_ses             # credentials, identity, config set, quota
python -m app.scripts.send_test --to success@simulator.amazonses.com
```

`check_ses` sends nothing and prints no secrets. `send_test` sends exactly one message
and refuses to run unless `MAIL_PROVIDER=ses`. Prefer the SES **mailbox simulator**
addresses (`success@`, `bounce@`, `complaint@simulator.amazonses.com`) — they exercise
the same API path without touching a real inbox.

Note: SES identities are **per Region**. A domain verified in `ap-south-1` is not
verified in `us-east-1`; `AWS_REGION` and the console Region must match.

## Phase 3 local workflow

From the repository root on a Unix-like development host, apply `cd backend && .venv/bin/alembic upgrade head` to create `api_keys`,
`email_messages`, and `outbox_events` (then `0004_worker` for lease fencing). Use the owner cookie to create a key at
`POST /v1/organizations/{organization_id}/api-keys`; keep its returned `mfk_...`
value out of logs and shell history. Submit with `X-API-Key` and optionally
`Idempotency-Key`. See `backend/README.md` for exact request/response examples.
Run `.venv/bin/python -m app.services.outbox` from `backend/` periodically to
process up to 50 due jobs per invocation. This invokes the fake provider only;
there is no automatic worker on API startup. Transient failures are retried with
bounded backoff; provider acceptance is `sent`, not proof of delivery. Future
provider integration must support provider-side deduplication with the stable
message ID to close the unavoidable post-acceptance crash window. Do not start
multiple workers against SQLite; PostgreSQL should be used in deployment.

Run `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check app tests alembic`,
`.venv/bin/python -m ruff format --check app tests alembic`, and
`.venv/bin/python -m pip check`. Keep key material out of source control and
protect stored email content; no real provider or frontend exists in the current Phase 4 implementation.

## Phase 4 validation and recovery

Set `MAILFLOW_TEST_POSTGRES_URL` to a **dedicated PostgreSQL test database**
with schema-create permission, then run `cd backend && .venv/bin/python -m pytest
-q tests/test_postgres_integration.py`. The test creates a random temporary
schema, upgrades migrations to head, exercises registration, login, organization
access, key creation/revocation, email submission/idempotency and concurrent
outbox claims, downgrades/re-upgrades the worker migration, and removes that
schema. It is **skipped**, not passed as PostgreSQL validation, when no URL is
provided. Do not use a production database. Avoid logging connection URLs.

Run `python -m app.services.outbox --status` for aggregate queue/failed counts
(no message bodies). Run `python -m app.services.outbox --requeue EMAIL_UUID` only
after investigating a failed job: it explicitly resets the attempt budget and
may cause another provider submission. Neither command is an HTTP endpoint;
protect database access to operators. Run the normal bounded worker tick with
`python -m app.services.outbox` under an external scheduler. Lease duration is
120 seconds; renewal every 30 seconds. A long process pause or failed heartbeat
can lead to duplicate provider calls, even with DB fencing. Prefer a future
provider with durable idempotency keyed by the stable message UUID.
