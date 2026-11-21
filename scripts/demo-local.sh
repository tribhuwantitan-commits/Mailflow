#! /usr/bin/env bash
# Run MailFlow locally in one shot, on any box that has Python 3.11+.
#
# Why this exists: the deploy host is a Windows RDP box, and opening it just to see
# whether the dashboard still renders is expensive. This builds a throwaway SQLite
# database, seeds a tenant through the real HTTP API, and serves the app on
# 127.0.0.1. It is a demo, not a deploy: no Postgres, no SES, no workers, no
# migrations, and the data is gone when the directory is.
#
#   ./scripts/demo-local.sh                 # then open http://127.0.0.1:8000/dashboard
#   DEMO_PORT=8080 ./scripts/demo-local.sh  # another port
#   DEMO_FRESH=1 ./scripts/demo-local.sh    # wipe the demo database first
#
# Everything here has a production counterpart that this script deliberately skips:
#   create_all     -> alembic upgrade head
#   fake provider  -> MAIL_PROVIDER=ses
#   SQLite file    -> managed PostgreSQL
# Treat a green demo as "the UI renders", never as "the deploy is verified".
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT=$(pwd)
BACKEND="$REPO_ROOT/backend"
PORT="${DEMO_PORT:-8000}"
DATA_DIR="${DEMO_DIR:-$REPO_ROOT/.demo}"
EMAIL="${DEMO_EMAIL:-demo@example.com}"
PASSWORD="${DEMO_PASSWORD:-demo-password-123}"
FRESH="${DEMO_FRESH:-0}"

if [ -x "$BACKEND/.venv/bin/python" ]; then
  PY="$BACKEND/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "No python3 found. Install Python 3.11+ first." >&2
  exit 1
fi

cd "$BACKEND"
if ! "$PY" -c 'import fastapi, sqlalchemy, uvicorn' 2>/dev/null; then
  echo "Dependencies are missing. Create the venv first:" >&2
  echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

mkdir -p "$DATA_DIR"
DB_FILE="$DATA_DIR/demo.db"
if [ "$FRESH" = "1" ]; then
  rm -f "$DB_FILE"
  echo "wiped: $DB_FILE"
fi

export DATABASE_URL="sqlite+pysqlite:///$DB_FILE"
export MAIL_PROVIDER="fake"
export APP_ENV="development"
unset SQS_EVENT_QUEUE_URL || true

echo "data: $DB_FILE"
echo

"$PY" - "$PORT" "$EMAIL" "$PASSWORD" <<'PY'
"""Seed a demo tenant through the real API, then hand over to uvicorn.

Seeding uses TestClient, i.e. the same route handlers, dependencies, quota checks
and ownership guards a customer hits. If this script had to write rows directly to
make the dashboard work, the dashboard would have a bug worth knowing about.

TestClient is used rather than HTTP to a live server because it needs no port and
no network: seeding therefore cannot fail because the server is not up yet.
"""

from __future__ import annotations

import os
import sys
import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.db.base import Base
from app.database import create_database_engine, create_session_factory
from app.main import create_app
from app.models.quota import DEFAULT_PLANS, SendingPlan

port, email, password = sys.argv[1], sys.argv[2], sys.argv[3]

settings = Settings()
engine = create_database_engine(
    settings.database_url,
    settings.database_connect_timeout_seconds,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
)

print(f"db: {os.environ.get('DATABASE_URL', '?')}")

# create_all does not run the seed migration, so the plan catalogue goes in by hand.
# Without a plan row every quota check fails with "unknown plan".
Base.metadata.create_all(engine)
session_factory = create_session_factory(engine)
with session_factory() as db:
    existing = {row.slug for row in db.query(SendingPlan).all()}
    for plan in DEFAULT_PLANS:
        if plan["slug"] not in existing:
            db.add(SendingPlan(**plan))
    db.commit()

client = TestClient(create_app(settings, database_engine=engine))


def step(label: str, status: int, ok: tuple[int, ...]) -> None:
    print(f"  [{'ok  ' if status in ok else 'skip'}] {label}: HTTP {status}")


print("seeding (real routes, in-process):")
resp = client.post(
    "/v1/auth/register", json={"name": "Demo User", "email": email, "password": password}
)
status = resp.status_code
org_id = None
if status == 201:
    org_id = resp.json()["organization"]["id"]
    step(f"register {email}", status, (201,))
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    step(f"login {email} (cookie in this client)", login.status_code, (200,))
else:
    # A second run against the same file: log in and reuse the organization.
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    step(f"login {email} (already registered)", login.status_code, (200,))
    # The session cookie is what the tenant routes require, so sign in first.
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    step(f"login {email} (cookie in this client)", login.status_code, (200,))
    listing = client.get("/v1/organizations")
    if listing.status_code == 200 and listing.json():
        org_id = listing.json()[0]["id"]
    if not org_id:
        raise SystemExit("could not find the demo organization; rerun with DEMO_FRESH=1")

domain = f"demo-{org_id[:8]}.example.com"
resp = client.post(f"/v1/organizations/{org_id}/domains", json={"domain": domain})
# 409 means a previous run already created it, which is fine for a demo.
step(f"sender domain {domain}", resp.status_code, (200, 201, 202, 409))

resp = client.post(
    f"/v1/organizations/{org_id}/api-keys", json={"name": f"demo-{uuid.uuid4().hex[:6]}"}
)
step("api key", resp.status_code, (200, 201))
body = resp.json() if resp.content else {}
api_key = body.get("key") or body.get("api_key") or body.get("token")

if api_key:
    resp = client.post(
        "/v1/emails",
        headers={"X-API-Key": api_key},
        json={
            "from": f"noreply@{domain}",
            "to": ["recipient@example.com"],
            "subject": "Demo message",
            "text_body": "Hello from the MailFlow demo.",
        },
    )
    step("send one email", resp.status_code, (200, 201, 202))

print()
print("ready.")
print(f"  dashboard: http://127.0.0.1:{port}/dashboard")
print(f"  email:     {email}")
print(f"  password:  {password}")
print()
print("The page needs the session cookie. Sign in once from this machine:")
print(f"  curl -c cookies.txt -H 'Content-Type: application/json' \\")
print(f"       -d '{{\"email\":\"{email}\",\"password\":\"{password}\"}}' \\")
print(f"       http://127.0.0.1:{port}/v1/auth/login")
print()
print("The fourth checklist step stays unticked on purpose: first delivery needs a")
print("real SES event, and this demo uses the fake provider.")
print("Ctrl+C stops it. Nothing survives a reboot; that is Step 9's job.")
PY

cd "$BACKEND"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
