# AWS-only plan — 2 to 4 months, credits se, Neon hata kar

Decision: **2-4 mahine tak sab kuch AWS par.** Windows server + managed Postgres dono
AWS se. Neon nahi. Budget ~$75/mo. Kharcha AWS credits se.

Ye doc sirf **is window** ke liye hai. 4 mahine baad revenue aaye to `VPS-SIZING.md`
wala sasta model (VPS + managed DB) dobara dekhna — table §8 mein hai.

---

## 0. Teen sach, jo pehle pata hone chahiye

| # | Sach | Matlab |
|---|---|---|
| 1 | **Windows licence Linux se ~2x mehnga hai** | Gemini ka `t4g` (Graviton) plan **Windows par exist hi nahi karta** — arm64 hai |
| 2 | **Lightsail ka apna VPC hai, RDS se peer nahi hota** | Set up ke waqt network choose karna hoga, warna DB "unreachable" dikhega |
| 3 | **1 GB managed DB par encryption at rest nahi** | $15 plan par nahi, $30 (2 GB) se shuru. Email = PII |

Teesra point important hai: testing ke waqt theek hai, **asli customer data se pehle** $30
plan par jaana.

---

## 1. Teen options — asli price (Nov 2026, Mumbai)

### Option A — Recommended: Lightsail Windows + Lightsail Postgres

| Cheez | Plan | $/mo | ₹/mo |
|---|---|---|---|
| Windows server | Lightsail **8 GB** / 2 vCPU / 160 GB SSD | **$74** | ₹6,500 |
| PostgreSQL | Lightsail **1 GB** managed | **$15** | ₹1,300 |
| SES | 50k emails test ke liye | ~$5 | ₹450 |
| **Total** | | **~$94** | **~₹8,250** |

**Windows licence bundle mein hai** — alag nahi lagta. Static IP, 2.5 TB transfer
(Mumbai mein half), RDP browser se — sab included.

**Budget mode (tight):** Windows **4 GB** ($44) + PG 1 GB ($15) = **$59/mo**.
Magar 4 GB par Windows khud ~1.5 GB khaata hai. API ke 4 workers + 2 background workers
ke saath ye **OOM ke bilkul kinare** hai. Raat 3 baje server mar jaye — beginner ke liye
sabse bura outcome. Isliye 8 GB recommend karta hoon.

### Option B — Gemini ka plan, Windows ke saath (sach mein kitna)

| Cheez | $/mo |
|---|---|
| EC2 **t3.medium** Windows (2 vCPU / 4 GB) | **~$100** |
| RDS db.t4g.small + 50 GB | ~$37 |
| Redis (ElastiCache) | ~$15 |
| **Total** | **~$152** |

Gemini ne `t4g.large` ka **Linux** price ($44) bataya (**asli $33**) aur usko Windows
samajh liya. Windows par wahi 4 GB ka server **$100** hai.

Aur Redis ki zaroorat nahi — already `outbox_events` queue hai (Phase 3).

### Option C — $75 ke andar, sabse sasta

| Cheez | $/mo |
|---|---|
| Lightsail Windows **4 GB** | $44 |
| Lightsail PG 1 GB (encryption nahi) | $15 |
| SES | ~$5 |
| **Total** | **~$64** |

Chalega, magar 4 GB ka OOM risk aur no encryption. **Pehle 1-2 mahine testing ke liye
theek**, asli customers ke saath nahi.

---

## 2. Credits se kitne mahine

| Credit | Option A ($94) | Option B ($152) | Option C ($64) |
|---|---|---|---|
| $100 | 1 mahina | — | 1.5 mahine |
| $500 | 5 mahine | 3 mahine | 7 mahine |
| **$1,000** (Activate Founders) | **10 mahine** | 6 mahine | 15 mahine |

**AWS Activate Founders** (self-funded, koi accelerator nahi chahiye) — **$1,000**,
2 saal valid. Eligibility: pre-Series B, 10 saal se kam purani company, **Paid tier
account**, aur ek **website** chahiye. Approval 5-10 business days.

Lightsail, RDS, EC2, S3 — sab eligible hain. Ineligible: Marketplace, Route 53 **domain
registration** fee, support plans, RI upfront fees.

### ⚠️ Lightsail Windows par free tier bekaar hai

3 mahine free tier **$22 tak ke Windows plan** par hai. Wo 2 GB ka plan hai. Windows
Server akela 1.2-1.5 GB khaata hai — **API chalane ke liye kaafi nahi**. Isko mat
count karo. (PG ka $15 plan 1 mahina free hai — wahi kaam aayega.)

---

## 3. ⚠️ Setup ka sabse bada trap

**Lightsail instances ka apna VPC hota hai. RDS usme nahi hota.**

```
Lightsail VPC  ──✗ no peering──>  default VPC (RDS rehta hai)
```

Isliye **do hi safe raaste hain:**

| Raasta | Kya karo | Kab |
|---|---|---|
| **A1 (recommended)** | Lightsail Windows + **Lightsail managed Postgres** | Ab — sab ek hi VPC mein |
| A2 | RDS banao par **same VPC** mein Lightsail ka… | ❌ possible nahi |
| B | Sab EC2 + RDS (default VPC) | Budget $152 ho tab |

**Matlab: Lightsail choose kiya to database bhi Lightsail ka lena.** Ye asal mein accha
hai — $15 vs RDS $37, aur console mein ek hi jagah.

---

## 4. Connection budget — 1 GB DB par

1 GB managed DB ginti mein chhoti hai. Pool ko **manually** set karna padega.

| Process | Pool | Instances | Total |
|---|---|---|---|
| API (uvicorn) | 6 | 4 | 24 |
| Outbox worker | 2 | 1 | 2 |
| Event poller | 2 | 1 | 2 |
| Maintenance job | 2 | 1 (roz 4 baje) | 2 |
| **Peak total** | | | **30** |

`.env` mein:

```
DATABASE_POOL_SIZE=6
DATABASE_MAX_OVERFLOW=0
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800
```

`MAX_OVERFLOW=0` matlab pool 6 se kabhi nahi badhega — request connection ka **wait**
karegi (30s tak) instead of DB par 7th connection kholne ke. Chhoti DB par yahi sahi
hai: thoda slow hona, crash se behtar.

> **Note:** ye env vars asli mein apply hote hain — worker mein ek bug tha jo unko
> ignore kar raha tha (`create_database_engine()` bare call). Isi commit mein fix kiya.
> Iske bina workers default `pool_size=5, overflow=10` = 15 per worker lete.

---

## 5. Neon se migrate — 4 step

### Agar abhi koi asli customer data nahi hai (most likely)

Bahut simple — kuch dump/restore nahi chahiye:

1. Lightsail mein PostgreSQL banao (same region)
2. `.env` mein `DATABASE_URL` badlo
3. `.venv\Scripts\python.exe -m alembic upgrade head`
4. `.venv\Scripts\python.exe -m pytest -q` → 143 passed

Bas. Naya khaali DB, saari tables ban jayengi.

### Agar data hai

```powershell
# 1. Neon se dump — UNPOOLED endpoint use karo
pg_dump "$env:NEON_URL" -Fc -f mailflow.dump

# 2. Lightsail/RDS par restore
pg_restore -d "$env:AWS_DB_URL" --no-owner --no-acl mailflow.dump

# 3. .env badlo, phir migration + test
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m pytest -q
```

`pg_dump`/`pg_restore` ke liye Windows par **PostgreSQL client tools** chahiye
(`winget install PostgreSQL.PostgreSQL`).

**Faayda:** Neon ke pooled/unpooled ka jhanjhat khatam. Lightsail DB direct connection
deta hai.

---

## 6. SES credentials — Lightsail par IAM role nahi milta

EC2 par IAM role attach hota hai (key ki zaroorat nahi). **Lightsail par nahi.** Isliye:

1. IAM mein ek **dedicated user** banao — `mailflow-ses-sender`
2. Policy: sirf `ses:SendEmail` + `ses:SendRawEmail` (SES resource ARN tak limited)
3. Access key → `.env` mein `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
4. **Admin key kabhi mat use karo** server par

Risk: key `.env` mein plaintext hai. Mitigation: file permissions, RDP par sirf aap,
aur key ko 90 din mein rotate.

---

## 7. Kya lena hai — aur kya *nahi*

| ✅ Lena | ❌ Nahi lena | Kyun |
|---|---|---|
| Lightsail Windows 8 GB | EC2 Windows | RDP + licence + IP bundled, $26/mo sasta |
| Lightsail managed PG | RDS | Lightsail VPC se peer nahi hota; $22/mo sasta |
| SES | — | already |
| SNS + SQS | SQS wala DLQ haan | Phase 7c ka pipeline |
| Lightsail snapshots | EBS snapshots alag | ₹40/mo, ek click |
| CloudWatch basic | — | free tier |
| — | **ElastiCache Redis** | outbox already queue hai |
| — | **ALB / Load balancer** | 1 server hai |
| — | **NAT Gateway** | ~$32/mo, bilkul zaroorat nahi |
| — | **CloudFront** | abhi nahi |
| — | **Route 53 hosted zone** | domain jahan hai wahi DNS rakho ($0.50/mo bachta hai) |
| — | **Multi-AZ** | $30 extra, pre-revenue par nahi |

---

## 8. 4 mahine baad — decide karne ka table

| Situation | Kya karo |
|---|---|
| Revenue ~0, credits khatam | **Lightsail Linux $12 + Neon free/Lightsail PG $15** = ~$30 |
| 2-5 paid customers | Lightsail Windows 8 GB + PG 2 GB (encryption) = $104 |
| 20+ paid customers | RDS + Multi-AZ, ya 2nd server + LB |
| Credits bache hue | Lightsail Windows + **RDS db.t4g.medium** ($100/mo) — Mumbai, no VPC issue |

**RDS tab hi jab budget $150+ ho** — kyunki RDS ke saath EC2 chahiye, Lightsail nahi.

---

## 9. Setup order — ek ek step, checkpoint ke saath

### Step 1: Lightsail Windows instance
- Region: **Mumbai (ap-south-1)**
- Blueprint: **Windows Server 2022**
- Plan: **8 GB / 2 vCPU / 160 GB — $74**
- Static IP attach karo

**✅ Checkpoint:** browser RDP khulta hai, Windows desktop dikhta hai.

### Step 2: Lightsail PostgreSQL
- Region: **Mumbai (same)**
- Engine: **PostgreSQL 16**
- Plan: **1 GB — $15** (asli data se pehle 2 GB)
- **"Advanced database options"** → `mailflow-owner` user + strong password

**✅ Checkpoint:** Lightsail console → database → **Connect** tab par "Connected" dikhe.

### Step 3: DB connection test (Windows par)
```powershell
Test-NetConnection <db-endpoint> -Port 5432
```
`TcpTestSucceeded : True` chahiye. False aaye to **Lightsail firewall rule** — instance
ke networking tab se DB ko allow karo.

**✅ Checkpoint:** True.

### Step 4: App deploy + migration
```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m pytest -q
```

**✅ Checkpoint:** `143 passed, 1 skipped`.

### Step 5: API + workers chalao
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
.venv\Scripts\python.exe -m app.services.outbox
.venv\Scripts\python.exe -m app.services.event_poller --loop
```

**✅ Checkpoint:** `https://<static-ip>/health` (ya port 8000) 200 deta hai.

### Step 6: Snapshot lo
Lightsail console → instance → **Snapshots** → Create.

**✅ Checkpoint:** snapshot "Available".

---

## 10. Monthly bill kaise dekhein

**Billing → Cost Explorer** → Group by **Service**.

| Service | Expected $/mo |
|---|---|
| Lightsail (Windows) | 74 |
| Lightsail (Database) | 15 |
| SES | 0-5 (volume ke hisaab se) |
| SNS / SQS | <1 |
| Data transfer | 0 (bundle mein) |
| **Total** | **~$90-95** |

**Budget alarm lagao:** Billing → Budgets → $100/mo, 80% par email.
Ye ek-line ka guard hai — galat instance type ya bhoola hua NAT Gateway turant pakda
jayega.
