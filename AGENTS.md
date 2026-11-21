# AGENTS.md — instructions for an AI coding agent

You are helping deploy and extend **MailFlow**, a multi-tenant transactional email
platform. Read this before touching anything. It exists so an agent does not
rediscover, the hard way, decisions that were already made deliberately.

---

## 0. The one thing that will waste your time

**All recent work is on a feature branch, not `main`.**

```
main                            → 31ef3a1  (old: no quota, no domains, no events, no dashboard)
arena/67b5c744-mailflow         → 17 commits: Phase 7a, 7b, 7c, pricing, Phase 9   ← WORK HERE
```

Check before you clone:

```bash
git log --oneline -1 origin/arena/67b5c744-mailflow
```

If it is not `cbc1fa9` or newer, you are not looking at the current code. On `main`
you will find none of: `app/models/delivery_events.py`, `app/models/quota.py`,
`app/api/domains.py`, `app/api/stats.py`, `app/api/dashboard.py`,
`alembic/versions/0005`–`0009`.

There is an open PR from this branch into `main`. Do not merge it, do not rebase it,
do not "helpfully" switch branches. Work only on `arena/67b5c744-mailflow`.

---

## 1. How to run things

```bash
cd backend
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

Every command goes through the venv's interpreter. On Windows that means
`.venv\Scripts\python.exe`, not `python`.

| Task | Command | Expected |
|---|---|---|
| Tests | `python -m pytest -q` | **157 passed, 1 skipped** |
| Lint | `python -m ruff check .` | `All checks passed!` |
| Format check | `python -m ruff format --check .` | `N files already formatted` |
| Migrations | `python -m alembic upgrade head` | head is `0009_monthly_quota` |
| API | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | `/health/live` → `{"status":"ok"}` |
| Outbox worker | `python -m app.services.outbox` | one tick, then exit |
| Event poller | `python -m app.services.event_poller --loop` | needs `SQS_EVENT_QUEUE_URL` |
| Maintenance | `python -m app.services.maintenance` | nulls old bodies/payloads |

**The one skipped test is deliberate.** `tests/test_postgres_integration.py` skips unless
`MAILFLOW_TEST_POSTGRES_URL` is set. Everything else runs on SQLite. Do not "fix" the
skip by hardcoding a URL.

### Where to run what

The same tests run in **GitHub Actions** (`.github/workflows/ci.yml`) on every push and
pull request: ruff, format check, pytest, plus a guard that fails if fewer than 150
tests are collected. **Do not open the RDP box to find out whether code is broken** —
read the Actions tab. The server is for the four things CI cannot do: real Postgres
migrations, real SES calls, the SQS event path, and OS-level auto-start.

Do not bind uvicorn to `0.0.0.0` on the RDP host. `/v1/auth/register` is unauthenticated,
so a public port 8000 lets strangers create tenants that send mail through the owner's
SES account. `127.0.0.1:8000` serves `/dashboard` inside RDP perfectly well.

See `docs/TESTING-SURFACES.md` for the full split (CI, Codespaces, Android, server).

---

## 2. Things that look like bugs and are not

Read this list before you "fix" any of it.

| Looks wrong | It is deliberate | Why |
|---|---|---|
| `send_email` returns `status: "accepted"`, not `"sent"` | yes | SES accepting is not delivery. Delivery arrives later through `delivery_events`. |
| A hard bounce sets `status: "failed"` **and** writes a suppression | yes | The suppression is written **before** the counter, so a crash in between still protects the tenant. |
| `per_recipient_daily_limit = 0` on paid plans | yes | `0` means "no cap" in the guard. That is only safe on paid plans. |
| Tenant gets `403 sender_domain_not_verified` | yes | Phase 7a gate. Every tenant must verify its own domain (SES identities are account-wide, so a shared apex would let one customer send as another). |
| `DELETE` happens after commit in the poller | yes | Crash before commit → SQS visibility timeout retries it. Crash after → duplicate is a no-op because of the `provider_event_id` unique constraint. |
| Writes `payload` then nulls it after 7 days | yes | The raw SES payload is ~88% of the row and nobody reads it after parsing is proven. |
| The dashboard is one big HTML string in Python | yes | No Node, no bundler, no template dir that can go missing at deploy time. |
| No Redis anywhere | yes | `outbox_events` is the queue: durable, lease-fenced, crash-recoverable. Redis would add a service and a failure mode and zero new guarantee. |
| Monthly quota is summed from `usage_daily`, not a counter | yes | One source of truth cannot drift. The index already exists. |

---

## 3. Architecture in ten lines

```
POST /v1/emails  →  domain gate (7a)  →  pause gate (7c)  →  quota reserve (7b/0009)
                 →  email_messages row + outbox_events row       [one transaction]
                                    │
                    outbox worker (lease, retry, backoff)
                                    │
                                  SES  ──events──> SNS ──> SQS
                                                            │
                                       event poller ────────┘
                                             │
                          delivery_events · suppressions · tenant_reputation
                                             │
                              email_messages.delivered_at etc.
                                             │
                                  GET /v1/organizations/{id}/stats
                                             │
                                       GET /dashboard
```

Ordering is not arbitrary. Domain gate before quota means a refused send does not burn
the daily allowance. Pause gate before reserve means a paused tenant never decrements
the counter.

---

## 4. Errors — do not invent new codes

| Code | Status | Where |
|---|---|---|
| `sender_domain_not_verified` | 403 | submit |
| `sending_paused` | 403 | submit and worker |
| `email_quota_exceeded` | 429 | submit |
| `recipient_quota_exceeded` | 429 | submit |
| `monthly_email_quota_exceeded` | 429 | submit |
| `monthly_recipient_quota_exceeded` | 429 | submit |
| `too_many_recipients` | 429 | submit |
| `recipient_daily_limit_exceeded` | 429 | submit |
| `plan_not_configured` | 503 | submit |
| `domain_taken`, `domain_exists` | 409 | domains |
| `domain_invalid`, `domain_not_verifiable` | 400 | domains |

Worker-side refusals reuse `organization_paused` and `recipient_suppressed` in
`email_messages.error_code`.

---

## 5. Plan catalogue — and the rule behind it

| slug | daily | monthly | per email | per recipient | price |
|---|---|---|---|---|---|
| `free` | 50 | 1,000 | 5 | 10 | $0 |
| `free_card` | 100 | 2,500 | 10 | 10 | $0 |
| `starter` | 1,000 | 30,000 | 50 | 0 | $9 |
| `growth` | 2,500 | 75,000 | 50 | 0 | $19 |
| `scale` | 5,800 | 174,000 | 50 | 0 | $39 |
| `business` | 13,000 | 390,000 | 50 | 0 | $79 |

**The rule:** a plan's monthly ceiling × $0.10/1,000 must stay under ~40% of its price.
SES costs real money per email and the price is fixed, so a generous daily limit is a
loss-making subscription. `tests/test_quota.py::test_every_paid_plan_can_afford_its_own_worst_case`
enforces this and **will fail the build** if you raise a limit without raising the price.

If the product owner asks for a bigger limit, raise the price in the same commit and say so.

---

## 6. Thresholds that must not drift

| Constant | Value | File | Why this number |
|---|---|---|---|
| `BOUNCE_PAUSE_RATE` | 0.05 | `app/services/delivery_events.py` | AWS pauses the account at 10%. Act at half. |
| `COMPLAINT_PAUSE_RATE` | 0.001 | same | AWS pauses at 0.5%. |
| `MIN_SENDS_TO_JUDGE` | 100 | same | 3 sends and 1 bounce is 33% — pausing on that is absurd. |
| body retention | 30 days | `app/config.py` | Dashboard shows status, not content. |
| event payload retention | 7 days | `app/services/maintenance.py` | 88% of the row, read once. |
| `delivery_events` retention | 90 days | same | Support reads it when a customer says "I never got it". |

---

## 7. Database rules

- **Migrations only.** Never `create_all` outside tests. New head goes on
  `alembic/versions/`, `down_revision` chained, and `tests/test_migrations.py` asserts
  the head string *and* the table list — update both.
- **Use `batch_alter_table`** for any column change, so SQLite tests keep working.
- `ON CONFLICT DO NOTHING` needs dialect branching (`postgresql` vs `sqlite`); see
  `app/services/quota.py::_ensure_row` and `delivery_events.py::_upsert_reputation`.
- Composite primary keys: `usage_daily` is `(organization_id, usage_date)`,
  `recipient_daily_counts` has a third `recipient_hash`. There is **no `id` column** on
  either. Paginate deletes by a column, not by `id`.
- `db.get(Model, {"col": "<string>"})` fails on UUID columns — wrap with `UUID(value)`.

---

## 8. Deploying on Windows

The target is a Windows Server reached over RDP. There is no Docker there (Docker
Desktop is unsupported on Windows Server) and no systemd.

- Venv interpreter: `.venv\Scripts\python.exe`
- uvicorn: bind `127.0.0.1` unless there is a reason to expose the port. The dashboard
  is used inside RDP, so `127.0.0.1:8000` is enough. `0.0.0.0` plus an open port 8000
  exposes the unauthenticated `/v1/auth/register` to the internet, which lets strangers
  send mail on the owner's SES account. Only bind `0.0.0.0` behind HTTPS, and close the
  firewall rule again the moment testing is over.
- Background workers are **one-tick processes**, not loops. Schedule them with Task
  Scheduler every minute; `Restart=always` equivalents do not exist here.
- Task Scheduler's default execution time limit silently kills a long-running task
  after three days. Always set `-ExecutionTimeLimit (New-TimeSpan -Seconds 0)`.
- A task with no window has no console output. Redirect the child process to a log file
  (`*>> logs\api.log`) or a crash leaves no evidence at all.
- Use `curl.exe` in PowerShell, not `curl` (which is an alias for `Invoke-WebRequest`).

Full step-by-step: `docs/DEPLOY-RUNBOOK.md`. Hosting choice and why Ubuntu is cheaper:
`docs/AWS-ONLY-PLAN.md`.

---

## 9. Security rules — non-negotiable

| Do | Do not |
|---|---|
| Read secrets from `.env` (gitignored) | Commit `.env`, paste keys into a commit message, or put a token in a git remote URL |
| Session cookie for browser routes | Accept an API key on `/dashboard` |
| `membership()` before **every** tenant query | Query by `organization_id` from the path without checking membership |
| `Cache-Control: no-store` on counters | Cache quota numbers |
| Least-privilege IAM user for SES (`ses:SendEmail`, `ses:SendRawEmail`) | Use an admin key on the server |
| Suppress per tenant | Suppress globally across tenants |

A verification step that is worth doing: after any auth change, confirm that
`GET /v1/organizations/{someone-elses-id}/stats` returns **404**, not data.

---

## 10. When you are done

```bash
cd backend
python -m pytest -q          # must be 157 passed, 1 skipped
python -m ruff check .       # must be clean
python -m ruff format --check .
```

Then commit to `arena/67b5c744-mailflow` and push that branch only. Write the commit
message about *why*, not *what* — the diff already says what.

**Do not** merge the PR, force-push, create a new branch, or touch `main`.
