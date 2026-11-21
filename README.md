# MailFlow

[![CI](https://github.com/tribhuwantitan-commits/Mailflow/actions/workflows/ci.yml/badge.svg)](https://github.com/tribhuwantitan-commits/Mailflow/actions/workflows/ci.yml)

**Implemented through Phase 9.** MailFlow is a multi-tenant transactional email platform: a FastAPI backend for organization-scoped REST email submission, plus a server-rendered tenant dashboard. Nine migrations (`0001`–`0009_monthly_quota`) are on `main`.

The provider is still the **fake**: no real mail leaves the machine until `MAIL_PROVIDER=ses` and an SQS event queue are configured. PostgreSQL integration validation is **pending** — the opt-in test has not run against a live PostgreSQL instance.

| Phase | Implemented |
| --- | --- |
| **1 — backend foundation** | FastAPI, environment configuration, SQLAlchemy/Alembic baseline, health checks, network-free fake provider. |
| **2 — authentication and organizations** | Registration, Argon2id passwords, opaque expiring/revocable sessions, membership-scoped organization access. |
| **3 — API keys and REST email** | Owner-managed organization API keys, `POST /v1/emails`, `GET /v1/emails`, `GET /v1/emails/{email_id}`, input validation, idempotency and transactional message/outbox persistence using the fake provider. |
| **4 — worker reliability** | Atomic job claims, renewable fenced leases, bounded retries, crash recovery, failed-job status and explicit operator requeue. PostgreSQL integration test is present but was skipped without a live database. |
| **7a–7c — domains, quota, events** | Per-tenant sender-domain verification, daily and monthly sending plans with a locked counter, SES event ingestion (bounce, complaint, suppression, reputation) with pause thresholds. |
| **9 — dashboard** | Server-rendered tenant page at `/dashboard`: activation checklist, daily and monthly usage, deliverability rates, 14-day volume. No build step, no CDN. |

Not implemented: login/signup pages, billing and upgrade flow, open/click tracking, an email-detail page, Redis/Celery (the outbox is the queue), SMTP submission. Amazon SES is coded and tested but **not connected** — the running default is the fake provider. Provider acceptance (`sent`) is not proof of delivery. Processing is at least once; provider-side durable idempotency would be needed to prevent all external duplicates. See [ARCHITECTURE.md](ARCHITECTURE.md) for current behavior and limitations.

**Next:** connect Amazon SES in the sandbox (Phase 6) — verified domain, configuration set, SNS → SQS event queue, `MAIL_PROVIDER=ses`. Production access and Activate come later, before a business launch, not now.

- [Where to test: CI, Codespaces, phone, server](docs/TESTING-SURFACES.md)
- [Deploy runbook: Windows Server, step by step](docs/DEPLOY-RUNBOOK.md)
- [Architecture, data model, security boundaries and roadmap](ARCHITECTURE.md)
- [Development, testing and PostgreSQL validation instructions](DEVELOPMENT.md)
- [Backend setup, API request/response examples and worker operations](backend/README.md)
