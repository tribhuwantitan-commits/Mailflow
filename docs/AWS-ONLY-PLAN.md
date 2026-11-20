# AWS-only plan — 2 to 4 months, credits se, Neon hata kar

Decision: **2-4 mahine tak sab kuch AWS par.** Server + managed Postgres dono AWS se.
Neon nahi. Budget ~$75/mo. Kharcha AWS credits se.

**OS: Ubuntu 24.04 LTS.** Windows nahi — §1 mein hisaab hai.

---

## 0. Pehle: code change chahiye kya? Nahi.

Repo check kiya — `backend/app` aur `backend/tests` mein **ek bhi** OS-specific line nahi:

| Cheez | Windows-specific? |
|---|---|
| `win32`, `WindowsPath`, `ntpath` | ❌ kuch nahi |
| Hardcoded paths | ❌ kuch nahi |
| Platform-specific deps | ❌ kuch nahi (pure Python + psycopg + uvicorn) |
| Tests | ❌ kuch nahi |

**Matlab: migration = sirf naya server + `.env`.** Code ko haath lagane ki zaroorat nahi.
143 tests Linux par waise hi pass honge.

> Note: `docs/PHASE-7C-EVENTS.md` etc. mein PowerShell commands hain
> (`.venv\Scripts\python.exe`). Wo sirf **commands** hain, code nahi. Translation table
> §7 mein hai.

---

## 1. Windows kyun mehnga tha — do jagah se

Windows par **do baar** pay karna padta hai: licence mein, aur RAM mein.

### (a) Licence

| | Linux | Windows | Farq |
|---|---|---|---|
| Lightsail 8 GB / 2 vCPU | **$44** | **$74** | **+$30/mo** |
| Lightsail 16 GB / 4 vCPU | $84 | $124 | +$40/mo |
| Lightsail 4 GB / 2 vCPU | **$24** | **$44** | **+$20/mo** |

### (b) RAM — asli chhupa hua kharcha

| | Idle RAM jo OS khaata hai |
|---|---|
| Ubuntu 24.04 | **~350 MB** |
| Windows Server 2022 | **~1,500 MB** |

Aapka app (4 API workers + 3 background process) ~1.1 GB leta hai. To:

| Server | Linux par bacha | Windows par bacha |
|---|---|---|
| 4 GB | 4.0 − 0.35 − 1.1 = **2.5 GB free** ✅ | 4.0 − 1.5 − 1.1 = **1.4 GB free** ⚠️ |
| 8 GB | bahut aaram | 5.4 GB ✅ |

**Isliye Windows par 8 GB chahiye tha ($74).** Linux par **4 GB kaafi hai ($24)** —
aur phir bhi zyada khaali RAM bachti hai.

**Yahi asli farq hai: $50/mo, ya 68% sasta.**

---

## 2. Teen options — asli price (Nov 2026, Mumbai)

### ✅ Option A — Recommended: Lightsail Linux 4 GB + PG 2 GB

| Cheez | Plan | $/mo | ₹/mo |
|---|---|---|---|
| Server | Lightsail **Ubuntu 24.04, 4 GB / 2 vCPU / 80 GB** | **$24** | ₹2,100 |
| PostgreSQL | Lightsail **2 GB managed** (encryption ✅) | **$30** | ₹2,650 |
| SES | ~50k emails | ~$3 | ₹270 |
| SNS + SQS | Phase 7c pipeline | <$1 | ₹60 |
| **Total** | | **~$57** | **~₹5,050** |

Static IP, 4 TB transfer (Mumbai mein 2 TB), snapshots alag se — sab included.

### Option B — Sabse sasta, testing ke liye

| Cheez | Plan | $/mo |
|---|---|---|
| Server | Lightsail Linux **2 GB** | $12 |
| PostgreSQL | Lightsail **1 GB** (encryption ❌) | $15 |
| SES | ~$3 | $3 |
| **Total** | | **~$30** (₹2,650) |

Sirf pehle 1-2 mahine, jab koi asli customer na ho. 2 GB par 2 API workers chalao, 4 nahi.

### Option C — Windows (jo pehle plan kiya tha)

| Cheez | $/mo |
|---|---|
| Lightsail Windows 8 GB | $74 |
| Lightsail PG 1 GB | $15 |
| SES | $3 |
| **Total** | **~$92** |

**Option A se $35/mo zyada**, aur kam RAM. Koi fayda nahi — sirf GUI.

---

## 3. Credits se kitne mahine — Linux ka asli faayda

| Credit | Option A ($57) | Option B ($30) | Option C Windows ($92) |
|---|---|---|---|
| $100 | 1.7 mahina | 3.3 mahina | 1 mahina |
| $500 | 8.7 mahine | 16 mahine | 5.4 mahine |
| **$1,000** | **17 mahine** | 33 mahine | 10 mahine |

**Same $1,000 credits: Windows par 10 mahine, Linux par 17 mahine.**

Aapko 2-4 mahine chahiye — matlab Linux par credits ka **13 mahine bacha** rahega
revenue aane ke baad bhi.

**AWS Activate Founders** (self-funded, accelerator nahi): $1,000, 2 saal valid.
Chahiye: pre-Series B, 10 saal se chhoti company, **Paid tier account**, ek **website**.
5-10 business days. Lightsail credits par chalta hai ✅.

---

## 4. Linux ke aur faayde (paise ke alawa)

| | Windows | Ubuntu |
|---|---|---|
| **Docker** | ❌ Windows Server par Docker Desktop **unsupported** | ✅ native `docker compose` — local dev + test asaan |
| **Auto-restart on crash** | NSSM / Task Scheduler setup karna padta | ✅ `systemd` — 10 line ki file |
| **Logs** | Event Viewer (dhundhna mushkil) | ✅ `journalctl -u mailflow` |
| **Updates** | Reboot maangta hai, RDP band | ✅ `unattended-upgrades`, reboot kabhi bhi |
| **Idle RAM** | 1.5 GB | 0.35 GB |
| **Attack surface** | RDP port 3389 — bot attacks ka favourite | SSH key-only, port badal do |
| **Session** | RDP toot jaye to kaam ruk gaya? | SSH toot jaye to **kaam chalta rehta hai** (tmux/systemd) |
| **Boot time** | 60-90 s | 15-20 s |

**Sabse bada practical faayda:** `systemd` se app crash ho to **10 second mein khud wapas
aa jayega**. Windows par ye NSSM se karna padta hai aur woh bhi kabhi kabhi chup-chaap
mar jaata hai.

---

## 5. Kya khoyenge — aur uska hal

**Kho rahe hain:** RDP ka Windows desktop (GUI).

**Hal: VS Code Remote-SSH.** Aapke Windows laptop par VS Code, usme remote server ka
**poora folder tree, file editor, terminal** — bilkul jaise local ho. Beginner ke liye
ye RDP se **behtar** hai, kyunki copy-paste saaf chalta hai aur file editing GUI se hoti hai.

| Kaam | Windows (RDP) | Linux (Remote-SSH) |
|---|---|---|
| File edit | Notepad/RDP | VS Code, same jaisa local |
| Terminal | PowerShell | VS Code ka built-in terminal |
| File transfer | Drag-drop RDP | Drag-drop VS Code |
| Restart app | Manual | `sudo systemctl restart mailflow` |

**Setup time: 30 minute** (SSH key + VS Code extension). Iske baad sab normal lagta hai.

---

## 6. Command translation — Windows se Linux

| Kaam | Windows | Ubuntu |
|---|---|---|
| venv activate | `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |
| Python chalao | `.venv\Scripts\python.exe` | `.venv/bin/python` |
| Migration | `.venv\Scripts\python.exe -m alembic upgrade head` | `.venv/bin/python -m alembic upgrade head` |
| Tests | `.venv\Scripts\python.exe -m pytest -q` | `.venv/bin/python -m pytest -q` |
| API | `uvicorn app.main:app --port 8000` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Path separator | `\` | `/` |

**Naya venv banana padega** (Windows ka venv Linux par nahi chalta):
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## 7. Lightsail ka VPC trap (dono OS par same)

**Lightsail instance ka apna VPC hota hai. RDS usme nahi hota.**

```
Lightsail VPC  ──✗ no peering──>  default VPC (RDS rehta hai)
```

Isliye **Lightsail liya to database bhi Lightsail ka**. Ye accha hai — $30 vs RDS $37-40,
aur console mein ek hi jagah.

RDS tab hi lena jab EC2 bhi le rahe ho (default VPC) — wo $150+/mo ka raasta hai.

---

## 8. Connection budget — 2 GB DB par

| Process | Pool | Instances | Total |
|---|---|---|---|
| API (uvicorn) | 6 | 4 | 24 |
| Outbox worker | 2 | 1 | 2 |
| Event poller | 2 | 1 | 2 |
| Maintenance | 2 | 1 (roz 4 baje) | 2 |
| **Peak** | | | **30** |

`.env`:
```
DATABASE_POOL_SIZE=6
DATABASE_MAX_OVERFLOW=0
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800
```

`MAX_OVERFLOW=0` = pool 6 se kabhi nahi badhega. Request connection **wait** karegi (30s
tak) instead of 7th connection kholne ke. Chhoti DB par: **thoda slow, crash se accha**.

**2 GB plan par `DATABASE_POOL_SIZE=4`** rakho (total ~20).

> Worker mein bug tha jo ye env vars ignore karta tha — isi branch par fix hua.

---

## 9. Neon se migrate

### Agar asli customer data nahi hai (most likely)

```bash
# 1. Lightsail mein PostgreSQL banao
# 2. .env mein DATABASE_URL badlo
# 3. naya venv banao (Linux)
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 4.
python -m alembic upgrade head

# 5.
python -m pytest -q          # → 143 passed, 1 skipped
```

### Agar data hai

```bash
pg_dump "$NEON_URL_UNPOOLED" -Fc -f mailflow.dump     # Neon ka UNPOOLED endpoint
pg_restore -d "$AWS_DB_URL" --no-owner --no-acl mailflow.dump
python -m alembic upgrade head
```

**Faayda:** Neon ke pooled/unpooled ka jhanjhat **khatam**.

---

## 10. SES credentials — Lightsail par IAM role nahi

EC2 par role attach hota hai. **Lightsail par nahi.** Isliye:

1. IAM user `mailflow-ses-sender`, policy **sirf** `ses:SendEmail` + `ses:SendRawEmail`
2. Key `.env` mein (`chmod 600 .env`)
3. **Admin key kabhi server par nahi**

---

## 11. Kya lena hai — aur kya *nahi*

| ✅ Lena | ❌ Nahi lena | Kyun |
|---|---|---|
| Lightsail Ubuntu 4 GB | EC2 (koi bhi) | licence + IP + transfer bundled |
| Lightsail managed PG 2 GB | RDS | VPC peer nahi; $7-10 sasta |
| SES + SNS + SQS + DLQ | **ElastiCache Redis** | `outbox_events` already queue hai |
| Lightsail snapshots | **ALB** | 1 server hai |
| CloudWatch basic | **NAT Gateway** | ~$32/mo, zaroorat nahi |
| Budget alarm | **CloudFront** | abhi nahi |
| — | **Multi-AZ** | $30 extra, pre-revenue nahi |
| — | **Route 53 hosted zone** | jahan domain hai wahi DNS rakho |

---

## 12. Setup order — ek ek step, checkpoint ke saath

### Step 0: AWS Activate apply (pehle ye)
Website chahiye. 5-10 din. **Credits aane se pehle paid setup shuru mat karo.**

**✅ Checkpoint:** approval email.

### Step 1: Lightsail Linux instance
- Region: **Mumbai (ap-south-1)**
- Blueprint: **Ubuntu 24.04 LTS**
- Plan: **4 GB / 2 vCPU / 80 GB — $24**
- Static IP attach karo
- Networking → firewall: **22 (apna IP), 80, 443** — 8000 band rakho

**✅ Checkpoint:** `ssh ubuntu@<static-ip>` se login ho jaye.

### Step 2: Lightsail PostgreSQL
- Region: **Mumbai (same)**
- Engine: **PostgreSQL 16**, plan **2 GB — $30** (encryption isliye)
- User `mailflow_owner`, strong password

**✅ Checkpoint:** console → database → "Connected".

### Step 3: Server se DB test
```bash
sudo apt install -y postgresql-client
psql "$DATABASE_URL" -c "select version();"
```

**✅ Checkpoint:** version string dikhe. Fail ho to Lightsail firewall mein DB ko
instance se allow karo.

### Step 4: App deploy
```bash
sudo apt update && sudo apt install -y python3.12-venv git
cd ~ && git clone <private-repo> && cd Mailflow/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # phir values bharo
python -m alembic upgrade head
python -m pytest -q
```

**✅ Checkpoint:** `143 passed, 1 skipped`.

### Step 5: systemd service (auto-restart)
`/etc/systemd/system/mailflow-api.service`:
```ini
[Unit]
Description=MailFlow API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Mailflow/backend
EnvironmentFile=/home/ubuntu/Mailflow/backend/.env
ExecStart=/home/ubuntu/Mailflow/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now mailflow-api
```

Isi tarah `mailflow-outbox.service` aur `mailflow-poller.service` (worker commands ke
saath, `Restart=always`).

**✅ Checkpoint:** `curl localhost:8000/health` → 200. `sudo systemctl status mailflow-api`
→ **active (running)**.

### Step 6: Caddy (HTTPS, 2 line mein)
```bash
sudo apt install -y caddy
```
`/etc/caddy/Caddyfile`:
```
api.aapkadomain.com {
    reverse_proxy localhost:8000
}
```
**✅ Checkpoint:** `https://api.aapkadomain.com/health` → 200, lock icon ✅.

### Step 7: Snapshot
Lightsail console → instance → **Snapshots** → Create.

**✅ Checkpoint:** "Available".

---

## 12b. Storage aur CPU — asli ginti

### Pehle ek galat-fehmi door karo

| | Kya hai |
|---|---|
| **2 GB** | **RAM** (memory), disk nahi |
| Disk | Lightsail PG 2 GB plan par **80 GB SSD** |

"2 GB mein kitne email" ka jawab do alag sawaalon mein banta hai:
**(a) kitne bhej sakte ho** (RAM/CPU) aur **(b) kitne store ho sakte hain** (disk).

---

### (a) Kitne bhej sakte ho — RAM/CPU se

DB par har send ka kharcha:

| Kaam | Time |
|---|---|
| Quota `UPDATE` (locked) | ~1.5 ms |
| `email_messages` insert | ~1 ms |
| `outbox_events` insert | ~1 ms |
| **Total per email** | **~3.5 ms** |

14 emails/sec par: 14 × 3.5 ms = **4.9% ek core ka**.
Events (42/sec) + dashboard reads mila kar ~**15% ek core**.

**2 GB RAM DB yahan bilkul aaram mein hai.** 14/sec = **12 lakh emails/din** bhej sakta
hai — RAM se limit nahi hota, SES quota se hota hai.

**Asli RAM kharcha API server par hai, DB par nahi:**

```
4 API workers × 90 MB          = 360 MB
2 background workers × 70 MB   = 140 MB
+ OS (Ubuntu)                  = 350 MB
+ argon2 login (64 MB peak each, kuch second)
                               ─────────
                                ~0.9 GB baseline
```

4 GB server par 4 concurrent logins bhi aaram se. **Server 4 GB kaafi hai.**

---

### (b) Kitne store ho sakte hain — disk se

Ye hisaab **schema se** nikala hai, andaaza nahi:

| Cheez | Per email | Retention |
|---|---|---|
| `email_messages` row + indexes | ~0.7 KB | permanent |
| `delivery_events` (~3 events) | ~0.75 KB | permanent |
| **Permanent total** | **~1.5 KB/email** | — |
| Body (text + html) | ~8 KB | **30 din** |
| Raw SES payload (3 events) | ~3.3 KB | **7 din** ✅ naya |

> **Payload retention isi commit mein add kiya.** Raw SES payload har event ka **~1.3 KB**
> hota hai — jo table ka 88% hai, aur ek hafte baad koi nahi padhta. 7 din baad null ho
> jata hai; timeline ke saare columns bache rehte hain. **Disk 7x kam.**

### 80 GB disk par kitna aayega

Postgres WAL + bloat + autovacuum ke liye **40-50% khaali** chhodna zaroori hai.
Usable maano **40 GB**.

| Roz | Body (30 din) | Permanent/maheena | **Kaafi hai?** |
|---|---|---|---|
| **10,000** | 2.4 GB | 0.45 GB | ✅ **saalon** (3+ saal) |
| **25,000** | 6 GB | 1.1 GB | ✅ **2 saal+** |
| **50,000** | 12 GB | 2.2 GB | ✅ ~1.5 saal |
| **100,000** | 24 GB | 4.5 GB | ⚠️ ~1 saal, body retention **14 din** karo |
| **400,000** | **96 GB** | 18 GB | ❌ **disk phat jayega** |

### Yaad rakhne wali line

> **80 GB disk = ~2.5 crore emails permanent.** Bleed body storage se hota hai, rows se nahi.
>
> **25,000 emails/din tak 2 GB plan bilkul theek hai.** Aap wahan abhi nahi ho.

### 100k+/din par kya karo (jab waqt aaye)

| Raasta | Kya | Cost |
|---|---|---|
| A | Body retention 30 → **7 din** | $0, ek line |
| B | Bodies **S3** mein rakho, DB mein sirf metadata | +$2/mo, 96 GB ke liye |
| C | DB plan 4 GB (**120 GB disk**) | +$30/mo |

**A ya B pehle try karo.** C sabse aakhir mein.

---

### CPU — 4 vCPU / 6 / 8 chahiye ya nahi?

**Nahi. 2 vCPU kaafi hai.** Magar ek chhupi hui baat samajhni zaroori hai:

**Lightsail burstable hai.** "2 vCPU" ka matlab do poore cores nahi:

| Plan | vCPU | Baseline | **Sustained milta hai** | Burst |
|---|---|---|---|---|
| $12 (2 GB) | 2 | 20% | 0.4 core | 2 core tak |
| **$24 (4 GB)** | **2** | **20%** | **0.4 core** | **2 core tak** |
| $44 (8 GB) | 2 | 30% | 0.6 core | 2 core tak |
| $84 (16 GB) | 4 | 40% | 1.6 core | 4 core tak |
| $164 (32 GB) | 8 | 40% | 3.2 core | 8 core tak |

Aapko **0.15 core** chahiye. $24 plan **0.4 core sustained** deta hai — **2.6x zyada**.
Aur spikes ke liye poore **2 core** tak burst kar sakta hai. **Bilkul sahi shape.**

### 8 vCPU lene ka asli matlab

| Plan | $/mo | Aapka $75 budget |
|---|---|---|
| 2 vCPU / 4 GB | **$24** | ✅ pura mahina |
| 4 vCPU / 16 GB | $84 | ❌ budget khatam, DB ke paise nahi bache |
| **8 vCPU / 32 GB** | **$164** | ❌ **2 mahine ka poora budget ek mahine mein** |

Aapko 8 vCPU se **20x zyada** milta hai jo chahiye. Wo paisa SES aur DB mein lagao.

### CPU kab badhana hai (signal)

Lightsail console mein CPU graph dekho — **"sustainable" zone** ke upar rehna chahiye.
Agar lagatar (ghanton) upar jaye:

| Signal | Kya karo |
|---|---|
| CPU 20% baseline par chipak raha, burst khatam | Server upgrade $44 (8 GB) — **1 click, 2 min reboot** |
| Wahi phir bhi | Workers 4 → 2 karo, phir dekho |
| Ab bhi | Tab 4 vCPU ($84) |

**Upgrade one-click hai, rebuild nahi.** Isliye bada kharid ke shuru mat karo —
chhote se shuru karo, signal aaye to badhao.

---

### Final recommendation — aapke volume ke hisaab se

| Roz | DB plan | Server | $/mo |
|---|---|---|---|
| **≤ 25,000** | PG **2 GB** — $30 | **4 GB / 2 vCPU** — $24 | **$54** ✅ |
| 25k–100k | PG **4 GB** — $60 | 4 GB — $24 | $84 |
| 100k+ | PG **8 GB** — $115 | 8 GB — $44 | $159 |

**Aap "≤ 25,000" wale row mein ho.** $54/mo, aur mahine ke baaki $21 credits mein
rehte hain.

> **Ek aur option:** credits khatam hone ke baad managed DB ($30) hata kar Postgres
> **usi server par** chala sakte ho — total **$24/mo**. Tab backup khud lena padega
> (roz `pg_dump` → S3). Beginner ke liye abhi nahi, par $0 ka raasta hai.

---

## 13. Monthly bill kaise dekhein

Billing → **Cost Explorer** → Group by **Service**.

| Service | Expected $/mo |
|---|---|
| Lightsail (Ubuntu) | 24 |
| Lightsail (Database) | 30 |
| SES | 0-5 |
| SNS / SQS | <1 |
| **Total** | **~$55-60** |

**Budget alarm:** Billing → Budgets → **$75/mo, 80% par email**.

---

## 14. 4 mahine baad — decide karne ka table

| Situation | Kya karo |
|---|---|
| Credits khatam, revenue 0 | Lightsail Linux 2 GB ($12) + PG 1 GB ($15) = **$27** |
| Credits bache, customers aa rahe | Same plan, DB **4 GB ($60)** |
| 20+ paid customers | 2nd Lightsail + LB, ya EC2 + RDS |
| Bahut zyada | Neon Scale + VPS (dekh `VPS-SIZING.md`) |

**Jab revenue aaye:** Hostinger KVM 4 (₹1,099 intro / ₹2,399 renewal, 4 vCPU/16 GB)
+ Neon — sabse sasta long-term. Lightsail se ₹500-1,000/mo bachta hai.
