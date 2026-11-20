# VPS sizing — 20,000 emails/day, 500-1,000 concurrent

Date: Nov 2026. Target: **20,000 emails/day**, **500-1,000 concurrent API requests**.

> **TL;DR:** 4 vCPU / 8 GB RAM kaafi hai — **magar VPS bada karne se pehle 4 code changes
> zaroori hain.** Bina unke 16 GB par bhi 500 concurrent nahi sambhalega.
> Aur ek cheez sabse pehle: **database 3-6 GB/month badhega**, Neon free 1 GB hai.

---

## 1. Pehle numbers clear karo

"20,000" ka matlab kya hai? Teen alag cheezein ho sakti hain, aur teeno ka load alag hai:

| Matlab | Monthly emails | API requests/day | Load |
|---|---|---|---|
| **20,000 emails/day** | 600,000 | ~20,000 | moderate |
| 20,000 tenants × 500 emails/mo | **10,000,000** | 20,000 | **heavy** |
| 20,000 API calls/day | varies | 20,000 | light |

Neeche **20,000 emails/day = 600,000/month** maan ke chala hoon. Agar 20,000 *tenants*
hain to section 7 padho — wahan numbers 10x hain.

### Load ka asli shape

| Metric | Average | Peak (3x) | Burst (5 min) |
|---|---|---|---|
| Emails/day | 20,000 | — | — |
| Emails/hour | 833 | 2,500 | — |
| **Emails/second** | 0.23 | **0.7** | **3.3** |
| API requests/day | 20,000 + reads | — | — |
| **Concurrent requests** | 50-150 | **500** | **1,000** |

**Nateeja:** 20,000/day **throughput ka problem nahi hai.** Problem **500-1,000 concurrent**
hai — aur wo memory/threads/connections ka problem hai, CPU ka nahi.

---

## 2. Code se 3 bottlenecks (yahi asli jawab hai)

Maine `backend/` padha. Ye teen cheezein **VPS se pehle** theek karni hain.

### Bottleneck 1: endpoints `def` hain, `async def` nahi

`app/api/emails.py` line 86:
```python
@router.post("", status_code=202)
def submit_email(...)          # ← sync, not async
```

FastAPI sync endpoint ko **thread pool** mein chalata hai. Uska default size **40** hai
(anyio limiter). Matlab:

```
500 concurrent requests aa gaye
  → 40 threads kaam kar rahe hain
  → 460 queue mein wait kar rahe hain
  → latency 10ms se 2+ second
  → zyada der wait kare to timeout / 503
```

**Ye VPS ki galti nahi hai.** 8 core par bhi 1 worker = 40 concurrent. Fix:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

4 workers × 40 threads = **160 concurrent**. 8 workers = 320.

### Bottleneck 2: DB pool sirf 15 connections

`app/config.py`:
```
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10      → max 15 connections
```

Har request ek session leta hai. `POST /v1/emails` mein **6 DB round trips** hain:
1. idempotency lookup (`existing`)
2. `INSERT email_messages`
3. `INSERT outbox_events`
4. `COMMIT`
5. `REFRESH`
6. (rollback path par extra)

15 connections × 6 round trips = **~90 DB operations in flight**. 500 concurrent par
pool khatam → `QueuePool limit ... connection timed out`.

**Fix:**
```
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=10      → 20 per worker, × 4 workers = 80
```

⚠️ **Magar Neon par:** 80 direct connections frontend ke limit se takra sakte hain.
Isliye **API ke liye Neon ka pooled endpoint** use karo (`-pooler`), migrations/worker ke
liye unpooled. Ye pahle bhi phansa tha — yaad rakho.

### Bottleneck 3: worker **serial** hai aur ek tick karta hai

`app/services/outbox.py` line 199:
```python
return sum(process_event(factory, provider, event_id) for event_id in ids)
```

Ye **ek-ek karke** bhejta hai. Har email = lease acquire + SES call (~150-400ms) + DB update.
Matlab **~3 emails/second per worker**.

Aur `main()` sirf **ek tick** chalata hai (`limit=50`), phir exit. Loop nahi hai.

| Setup | Emails/second | 20,000/day peak (0.7/s) |
|---|---|---|
| 1 tick per minute, limit 50 | 0.83 | ✅ barely |
| 1 tick per minute, burst 3.3/s | — | ❌ queue banega |
| 2 worker processes, back-to-back | ~6/s | ✅ comfortable |
| Serial worker, 1 process, 3.3/s burst | 3/s | ⚠️ lag |

**Fix:** worker ko 2 process mein chalao, ya `process_due` ko `ThreadPoolExecutor` se
parallel karo (asyncio + `run_in_executor`). Aur ek proper loop + supervisor (NSSM ya
Task Scheduler har 10 second).

---

## 3. VPS size — exact

Assumptions: 4 uvicorn workers, 2 worker processes, Python 3.12, PostgreSQL Neon par.

### RAM (sabse zyada chahiye)

| Component | RAM |
|---|---|
| Windows Server 2022 base | **1.5-2 GB** |
| Python process (uvicorn worker, sync SQLAlchemy + boto3) | ~120-160 MB each |
| 4 uvicorn workers | ~600 MB |
| 2 outbox workers | ~250 MB |
| OS cache / headroom | ~1 GB |
| **Total** | **~4 GB minimum, 6-8 GB comfortable** |

### CPU

Request **wait** karti hai (DB + SES), compute nahi karti. 6 DB round trips = ~40-60ms CPU.
500 concurrent / 60ms = ~8,300 req/s theoretical. **2 vCPU bhi kaafi hain** agar threads/workers sahi hon.

Magar Windows Server + 6 workers + antivirus = **4 vCPU** comfortable.

### Disk

| Cheez | Size |
|---|---|
| OS + Python + venv | 10 GB |
| Logs (30 day retention) | 2-5 GB |
| OS updates / temp | 10 GB |
| **Total** | **40 GB minimum, 80 GB comfortable** |

### Final spec

| | Minimum | **Recommended** | Comfortable |
|---|---|---|---|
| vCPU | 2 | **4** | 8 |
| RAM | 4 GB | **8 GB** | 16 GB |
| Disk | 40 GB SSD | **80 GB NVMe** | 160 GB |
| Bandwidth | 2 TB | **4 TB** | — |

**Bandwidth check:** 20,000 emails/day × 5 KB = 100 MB/day = **3 GB/month** egress.
Kuch bhi nahi. 4 TB par 0.07% use.

---

## 4. VPS options — price ke saath

### Windows Server chahiye to

| Provider | Plan | Spec | Price | Note |
|---|---|---|---|---|
| **Aapka current VPS** | ? | ? | **already paid** | ✅ pehle isko check karo |
| Kamatera | 4 vCPU / 8 GB | Mumbai available | ~$40-50/mo | Windows license included |
| Contabo | VPS L | 8 vCPU / 30 GB | ~€15-20/mo | sasta, magar oversold; Windows extra |
| IONOS | VPS L | 4 vCPU / 8 GB | ~€20/mo | Windows add-on |
| AccuWebHosting | Windows VPS | 4 vCPU / 8 GB | ~$45/mo | India DC |

### Linux chahiye to (sasta, aur is scale par behtar)

| Provider | Plan | Spec | Price | Location |
|---|---|---|---|---|
| **Hostinger** | **KVM 4** | 4 vCPU / **16 GB** / 200 GB NVMe | **₹1,099/mo intro, ₹2,399 renew** | 🇮🇳 India |
| Hostinger | KVM 8 | 8 vCPU / 32 GB | ₹2,199 intro, ₹4,399 renew | India |
| Hetzner | CAX21 | 4 ARM vCPU / 8 GB / 80 GB | **€10.49/mo** | 🇪🇺 EU only |
| Hetzner | CAX31 | 8 ARM vCPU / 16 GB | €20.99/mo | EU only |
| Hetzner | CPX31 | 4 / 8 GB | €62.49/mo (US) | US only |

⚠️ **Hetzner par Windows nahi milta** (unka policy hai), aur EU location se Neon
Singapore tak ~180 ms latency hai — har DB query 6 round trips = **1+ second per request**.
**India ya Singapore hi chuno.**

### Sabse important: **app aur database paas hon**

```
Neon region: ap-southeast-1 (Singapore)   ← aapka DB
     ↑
     │ 50-70 ms  ✅
     │
VPS: India (Mumbai) ya Singapore
```

Agar VPS EU/US mein ho aur DB Singapore mein, **600,000 emails/month par har request
slow hogi**. Ye VPS size se zyada matter karta hai.

### Meri recommendation (aapke case mein)

| Stage | Kya |
|---|---|
| **Aaj** | Apna current Windows VPS — pehle specs check karo (neeche command) |
| **20k/day + 500 concurrent** | 4 vCPU / 8 GB / 80 GB. Windows chahiye to Kamatera Mumbai |
| **Agar 1,000 concurrent + 20k tenants** | 8 vCPU / 16 GB, ya 2 VPS + load balancer |
| **Long term** | Linux (Hostinger KVM 4 India, ₹1,099-2,399) — 3x sasta, aadha dard |

Note: Windows par 6 services (4 uvicorn + 2 worker) manually manage karne padenge.
NSSM (Non-Sucking Service Manager) use karo — reboot par khud chalu, crash par restart.

---

## 5. Code changes — VPS se pehle (priority order)

| # | Change | File | Kyun |
|---|---|---|---|
| 1 | `--workers 4` uvicorn | run command | 40 → 160 concurrent |
| 2 | `DATABASE_POOL_SIZE=10`, overflow 10 | `.env` | 15 → 80 pool |
| 3 | API ke liye Neon **pooled** endpoint | `.env` | 80 connections Neon par |
| 4 | Worker: 2 process + loop + NSSM | `outbox.py` | 3/s → 6/s, lag khatam |
| 5 | `process_due` parallel (`run_in_executor`) | `outbox.py` | burst 3.3/s sambhalega |
| 6 | **Email body retention** | naya migration | DB 3-6 GB/month badh raha hai |
| 7 | Rate limit per API key | naya code | 500 concurrent = ek customer DB flood kar sakta hai |

### #6 sabse urgent hai — explain karta hoon

`app/models/delivery.py` mein `text_body` aur `html_body` **Postgres `Text`** hain. Har
email ka pura body DB mein rehta hai, **forever**.

```
20,000 emails/day × 5 KB avg body = 100 MB/day
                                 = 3 GB/month
                                 + indexes, ~3.5 GB/month
```

| Neon plan | Storage | Kitne mahine |
|---|---|---|
| **Free** | **1 GB** | **teesra mahina** cross |
| Launch ($19) | 10 GB | ~3 mahine |
| Scale ($69) | 50 GB | ~14 mahine |

**Aur Neon storage bill alag hai** — 1 GB se zyada par extra charge.

**Fix (teen options):**

| Option | Kaise | Effort |
|---|---|---|
| **A. Body retention** | 30 din baad `text_body`/`html_body` NULL kar do, metadata rakho | chhota migration + cron |
| **B. S3 archive** | 7 din baad body S3 mein, DB mein pointer | medium |
| **C. Sirf metadata** | body kabhi store hi mat karo | ❌ dashboard/preview nahi banega |

**Recommendation: A abhi, B jab 500+ customers ho.** End customer ko 30 din se purana
email body chahiye bhi nahi hota — sirf status (delivered/bounced) chahiye.

---

## 6. Agar 20,000 *tenants* hain (10M emails/month)

Numbers 17x ho jate hain:

| | 20k emails/day | 10M emails/month |
|---|---|---|
| Emails/second (peak) | 0.7 | **17** |
| SES bill | $60/mo | **$1,000/mo** |
| DB growth | 3 GB/mo | **50 GB/mo** |
| VPS | 4 vCPU / 8 GB | **8 vCPU / 16 GB** ya 2 boxes |
| Workers needed | 2 | **6+** |
| SES rate limit | 14/s default | **isliye aur maango** |
| Neon | Free / Launch | **Scale ($69)** |

10M/month par **SES ka rate limit hi bottleneck** ban jayega (17/s chahiye, default 14/s).
Production access ke waqt `10,000/day` nahi, **50,000/day + 50/s** maango.

---

## 7. Aaj ka action — 3 commands

**1. Apne current VPS ke specs check karo** (PowerShell):

```powershell
Get-CimInstance Win32_ComputerSystem | Select-Object NumberOfProcessors, @{n='RAM_GB';e={[math]::Round($_.TotalPhysicalMemory/1GB,1)}}
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Get-PSDrive C | Select-Object @{n='Free_GB';e={[math]::Round($_.Free/1GB,1)}}
```

**2. Jo mile, usse ye decide karo:**

| Result | Kya karo |
|---|---|
| 4+ vCPU, 8+ GB RAM, 40+ GB free | ✅ **kuch kharidna nahi**, sirf code changes |
| 2 vCPU, 4 GB RAM | ⚠️ 500 concurrent tak theek, magar tight. Code changes ke baad test karo |
| 2 vCPU, 2 GB RAM | ❌ Windows + 4 workers nahi chalega. Upgrade karo |

**3. Server ka location check karo:**

```powershell
# apna public IP
(Invoke-RestMethod https://api.ipify.org)
```

Phir us IP ko `ipinfo.io` par daalo — India/Singapore hai to ✅, US/EU hai to **DB latency
problem** hogi.

---

## 8. Ek line ka verdict

> **4 vCPU / 8 GB / 80 GB — bas itna.** 16 GB ki zaroorat nahi jab tak 20,000 *tenants*
> na hon. Magar **VPS badalne se pehle 4 code changes** karo (`--workers 4`, pool 80,
> Neon pooled, worker parallel) — warna bada box bhi 500 concurrent par nahi chalega.
> Aur **sabse pehle DB retention** — 20k emails/day par Neon free 1 GB **3 mahine** mein
> bhar jayega.
