# MailFlow

**Current implemented phase: Phase 4 (reliability hardening).** MailFlow is a FastAPI backend for organization-scoped, fake-provider REST email submission. It does **not** send real mail. PostgreSQL integration validation is **pending**: the opt-in test has not run against a live PostgreSQL instance.

| Phase | Implemented |
| --- | --- |
| **1 — backend foundation** | FastAPI, environment configuration, SQLAlchemy/Alembic baseline, health checks, network-free fake provider. |
| **2 — authentication and organizations** | Registration, Argon2id passwords, opaque expiring/revocable sessions, membership-scoped organization access. |
| **3 — API keys and REST email** | Owner-managed organization API keys, `POST /v1/emails`, `GET /v1/emails`, `GET /v1/emails/{email_id}`, input validation, idempotency and transactional message/outbox persistence using the fake provider. |
| **4 — worker reliability** | Atomic job claims, renewable fenced leases, bounded retries, crash recovery, failed-job status and explicit operator requeue. PostgreSQL integration test is present but was skipped without a live database. |

No frontend, Redis/Celery, Amazon SES, SMTP listener, sender-domain verification or deployment has been implemented. Provider acceptance (`sent`) is not proof of delivery. Processing is at least once; provider-side durable idempotency would be needed to prevent all external duplicates. See [ARCHITECTURE.md](ARCHITECTURE.md) for current behavior and limitations.

**Future roadmap — planned, not implemented:** Phase 5: domain management and sender verification; Phase 6: Amazon SES integration and delivery events; Phase 7: SMTP submission; Phase 8: production readiness. Phase 5 has not started.

- [Architecture, data model, security boundaries and roadmap](ARCHITECTURE.md)
- [Development, testing and PostgreSQL validation instructions](DEVELOPMENT.md)
- [Backend setup, API request/response examples and worker operations](backend/README.md)
