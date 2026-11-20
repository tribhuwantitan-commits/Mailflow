# Deploy runbook — Windows Server (RDP)

Ye runbook **copy-paste** ke liye hai. Har step ka ek checkpoint hai. Checkpoint fail ho
to **aage mat badho**.

Har command PowerShell mein, **Administrator** ke roop mein.

---

## ⚠️ Step 0: Ye pehle — 3 minute

Agar ye fail hote hain to baaki sab bekaar hai.

```powershell
Test-NetConnection 1.1.1.1 -Port 443
Test-NetConnection email.ap-south-1.amazonaws.com -Port 443
(Invoke-RestMethod https://api.ipify.org)
```

| Result | Matlab |
|---|---|
| Dono `TcpTestSucceeded : True` | ✅ internet + AWS theek |
| Pehla False | ❌ internet nahi — provider se poochho |
| Doosra False | ❌ outbound blocked — email nahi jayega |

Teen line chhapo aur sambhal ke rakho — aage kaam aayengi.

**Checkpoint:** dono True, aur ek public IP dikha.

---

## Step 1: Python + Git

```powershell
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
winget install --id Git.Git -e --accept-source-agreements
```

**Terminal band karo, naya kholo** (PATH refresh ke liye), phir:

```powershell
python --version
git --version
```

**Checkpoint:** `Python 3.12.x` aur `git version 2.x`

> Agar `winget` nahi hai: Windows Server 2019 par purana hai. `python.org` se installer
> manually lo, "Add python.exe to PATH" tick karo.

---

## Step 2: Code clone

```powershell
New-Item -ItemType Directory -Force -Path C:\apps | Out-Null
cd C:\apps
git clone https://github.com/tribhuwantitan-commits/Mailflow.git
cd Mailflow
git log --oneline -1
```

**Checkpoint:** last commit `cbc1fa9` ya naya dikhe, aur `git branch --show-current` → `arena/67b5c744-mailflow`

> **Agar `main` par ho** (aur commit `31ef3a1` dikhe) — **galat branch hai**, Phase 7
> aur 9 ka kuch nahi milega:
> ```powershell
> git checkout arena/67b5c744-mailflow
> ```

Private repo hai — GitHub credential manager khulega. Browser se sign in karo.
**Token URL mein kabhi mat daalo.**

---

## Step 3: venv + dependencies

```powershell
cd C:\apps\Mailflow\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

**Checkpoint:** `python -c "import fastapi, sqlalchemy, alembic; print('ok')"` → `ok`

---

## Step 4: `.env`

```powershell
copy .env.example .env
notepad .env
```

Minimum (SQLite, fake provider — sirf app chalane ke liye):

```
DATABASE_URL=sqlite:///./mailflow.db
MAIL_PROVIDER=fake
SECRET_KEY=<run the command below and paste the output>
```

Secret banao:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Checkpoint:** `.env` save ho, aur `git status` mein `.env` **`untracked`** dikhe
(matlab gitignore kaam kar raha hai). Kabhi `.env` commit na karo.

---

## Step 5: Migration + full test suite

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m pytest -q
```

**Checkpoint:**

| | Expected |
|---|---|
| alembic | last line `Running upgrade 0008_plan_pricing -> 0009_monthly_quota` |
| pytest | **`157 passed, 1 skipped`** |
| ruff | `python -m ruff check .` → `All checks passed!` |

> **`1 skipped` normal hai** — PostgreSQL integration test, `MAILFLOW_TEST_POSTGRES_URL`
> set nahi hai. Baaki sab pass hone chahiye.
>
> **Kuch fail ho to yahin ruko.** Machine ka issue hai (Python version, path), code ka
> nahi. Error paste karo.

---

## Step 6: Firewall

```powershell
New-NetFirewallRule -DisplayName "MailFlow API 8000" -Direction Inbound `
  -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
```

**Checkpoint:** `Get-NetFirewallRule -DisplayName "MailFlow API 8000" | Format-List Name,Enabled,Direction`

> ⚠️ **8000 poore internet par khula hai.** Testing ke liye theek. Baad mein:
> sirf 443 kholo (Caddy/nginx ke through) aur 8000 ko `127.0.0.1` par band karo.

---

## Step 7: API chalao (manual, pehli baar)

```powershell
cd C:\apps\Mailflow\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Checkpoint** — **doosri** PowerShell window mein:

```powershell
curl.exe http://localhost:8000/health/live
curl.exe http://localhost:8000/health/ready
```

| | Expected |
|---|---|
| live | `{"status":"ok"}` |
| ready | `{"status":"ready","checks":{"database":"ok"}}` |

Aur **bahar** se (apne laptop ke browser mein): `http://<public-ip>:8000/health/live`

| Result | Matlab |
|---|---|
| JSON dikha | ✅ firewall theek |
| Timeout | ❌ provider ka firewall block kar raha hai (Windows firewall nahi) |

---

## Step 8: Tenant banao + dashboard kholo

`curl.exe` use karo — PowerShell ka `curl` alias hai `Invoke-WebRequest` ka.

```powershell
$base = "http://localhost:8000"

# 1) register
curl.exe -s -X POST "$base/v1/auth/register" -H "Content-Type: application/json" `
  -d '{\"email\":\"aap@example.com\",\"password\":\"AapkaPassword2026!\",\"name\":\"Aapka Naam\",\"organization_name\":\"My Company\"}'

# 2) login -> cookie save
curl.exe -s -c cookies.txt -X POST "$base/v1/auth/login" -H "Content-Type: application/json" `
  -d '{\"email\":\"aap@example.com\",\"password\":\"AapkaPassword2026!\"}'

# 3) dashboard
start http://localhost:8000/dashboard
```

**Checkpoint:** dashboard khula — heading `My Company · free plan`, do counters
`0 of 50` / `0 of 1,000`, aur **"Get set up" mein 0 tick**.

> **4 tick kab aayenge?** Domain verify + API key + email bhejo + delivery event aaye.
> Ye Step 10-12 ka kaam hai.

---

## Step 9: API ko restart-proof karo (Task Scheduler)

**File banao** `C:\apps\Mailflow\backend\run-api.ps1`:

```powershell
 Set-Location C:\apps\Mailflow\backend
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Task Scheduler** → Create Task:

| Tab | Setting |
|---|---|
| General | Name: `MailFlow API` · Run whether user logged on or not · Run with highest privileges |
| Triggers | New → **At startup** · Delay 30 seconds |
| Actions | New → Program: `powershell.exe` · Arguments: `-NoProfile -ExecutionPolicy Bypass -File C:\apps\Mailflow\backend\run-api.ps1` · Start in: `C:\apps\Mailflow\backend` |
| Settings | **Uncheck** "Stop the task if it runs longer than" · "If the task fails, restart every 1 minute, 3 times" |

Pehli window band karo (jo Step 7 mein chali thi), phir task **Run** karo.

**Checkpoint:** `Get-Process python` mein process dikhe, aur `/health/live` phir 200 de.
Ab **server reboot** karo — api khud wapas aani chahiye.

---

## Step 10: Outbox worker (email bhejne wala)

**File banao** `C:\apps\Mailflow\backend\run-worker.ps1`:

```powershell
Set-Location C:\apps\Mailflow\backend
& .\.venv\Scripts\python.exe -m app.services.outbox
```

> Worker **ek tick** karta hai phir exit hota hai. Scheduler use har minute chalata hai.
> Ye jaan-boojh kar hai — koi `while` loop nahi, isliye crash ho to agle minute wapas
> aa jata hai.

**Task Scheduler** → Create Task:

| Tab | Setting |
|---|---|
| General | Name: `MailFlow Outbox` · Run whether user logged on or not |
| Triggers | New → **At startup** · New → **Repeat every 1 minute, indefinitely** |
| Actions | Program `powershell.exe`, Arguments `-NoProfile -ExecutionPolicy Bypass -File C:\apps\Mailflow\backend\run-worker.ps1` |
| Settings | **Uncheck** "Stop the task if runs longer than" · "Do not start a new instance" (parallel instances na chalein) |

**Checkpoint:** Task Scheduler → right-click → **Run** → Last Run Result `0x0`.
Aur log `C:\apps\Mailflow\backend\worker.log` mein `worker_tick processed=0` dikhe.

---

## Step 11: Webhook worker (SQS) — **sirf jab SQS ban jaye**

`docs/PHASE-7C-EVENTS.md` §9.1 ka AWS console kaam pehle karo (SQS + SNS +
configuration set). Phir `.env` mein:

```
SQS_EVENT_QUEUE_URL=https://sqs.ap-south-1.amazonaws.com/<account>/<queue>
SES_CONFIGURATION_SET=mailflow-events
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
```

**File banao** `run-poller.ps1`:

```powershell
Set-Location C:\apps\Mailflow\backend
& .\.venv\Scripts\python.exe -m app.services.event_poller --loop
```

Task Scheduler: same as Step 10, magar **"At startup" only** (loop khud chalta rehta hai,
repeat ki zaroorat nahi) aur `0x0` ki jagah continuous run karega.

**Checkpoint:** poller start hote hi `event_poller` log line aaye, error nahi.
Aur `bounce@simulator.amazonses.com` par bhej kar 60 second mein
`event_poll received=... stored=...` dikhe.

---

## Step 12: Retention job (roz 4 baje)

**File banao** `run-maintenance.ps1`:

```powershell
Set-Location C:\apps\Mailflow\backend
& .\.venv\Scripts\python.exe -m app.services.maintenance
```

Task Scheduler: **Daily 04:00**, "Run whether user logged on or not".

**Checkpoint:** pehli baar manually chalao — `maintenance_windows bodies=30d ...`
dikhna chahiye, error nahi. (`--dry-run` flag bhi hai.)

---

## Step 13: HTTPS (private testing ke liye zaroori nahi)

Bina HTTPS ke:
- cookie `Secure` flag ke bina rahegi
- API keys plaintext mein travel karengi
- **API clients (aapke customers) http use nahi karenge**

Do raaste:

| Raasta | Kaise | Kab |
|---|---|---|
| **Caddy** (recommended) | `caddy reverse-proxy --from api.yourdomain.com --to localhost:8000` | jab domain ho |
| Cloudflare | DNS proxy + Origin certificate | bina server change |

Phir 8000 ko sirf localhost par band karo:
```powershell
Set-NetFirewallRule -DisplayName "MailFlow API 8000" -Enabled False
```

---

## 14. Ek page ka checklist

| # | Step | Checkpoint | Time |
|---|---|---|---|
| 0 | Internet + AWS test | dono True | 3 min |
| 1 | Python + Git | `python --version` 3.12 | 5 min |
| 2 | Clone (**right branch**) | `cbc1fa9`+ on `arena/...` | 5 min |
| 3 | venv + install | `import ok` | 10 min |
| 4 | `.env` | untracked in git | 3 min |
| 5 | **migrate + pytest** | **157 passed** | 5 min |
| 6 | Firewall 8000 | rule exists | 1 min |
| 7 | uvicorn | `/health/ready` → ready | 3 min |
| 8 | **Tenant + dashboard** | page khula | 5 min |
| 9 | API auto-restart | reboot ke baad bhi 200 | 10 min |
| 10 | Outbox worker | `worker_tick` log | 10 min |
| 11 | Poller (SQS ke baad) | `event_poll` log | 10 min |
| 12 | Retention job | `maintenance_windows` log | 5 min |
| 13 | HTTPS | `https://` 200 | 15 min |

**Step 8 tak ~40 minute.** Wahan aapke paas ek chalta hua, tested system hai.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `python` not found | PATH refresh nahi hua | Terminal band karo, naya kholo |
| `Activate.ps1 cannot be loaded` | Execution policy | `Set-ExecutionPolicy -Scope Process Bypass` |
| `attempted relative import` | Galat directory | `cd backend` |
| `No module named 'app.services'` | venv activate nahi | `.venv\Scripts\Activate.ps1` |
| `alembic` says multiple heads | Branch switch ke bache hue files | `git status`, phir `alembic heads` |
| `/health/ready` → 503 | DB connect nahi | `DATABASE_URL` check, SQLite path |
| Dashboard par `401` | Login nahi, cookie nahi | Step 8 ka `curl -c cookies.txt` phir se |
| Dashboard par `404 error | Request failed` | Branch galat hai (Phase 9 nahi hai) | Step 2 ka branch check |
| Bahar se timeout | Provider firewall | Console mein port 8000 kholo |
| `157 passed` ki jagah `main` ke 100-something | **Galat branch** | `git checkout arena/67b5c744-mailflow` |
