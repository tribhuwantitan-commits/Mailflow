# Cost model reconciliation — 7 Nov 2026

Do cost models bane the: ek ChatGPT ke saath (2.45M emails/month, $334.16/mo), ek is
repo ke saath. Ye doc dono ko aamne-saamne rakhta hai, verified 2026 prices ke saath, aur
batata hai kya sahi tha, kya galat, aur kya badla.

---

## 0. Sabse pehle: ek cheez jo poora model hila deti hai

**21 July 2026 se naye SES accounts `Essentials` plan par shuru hote hain — $0.16/1K,
$0.10 nahi.**

| Plan | Rate | 2.45M/month |
|---|---|---|
| **À la carte** | **$0.10/1K** | **$245** |
| Essentials (default!) | $0.16/1K | $392 |
| Pro | $0.22/1K + $105 | $644 |

Aapka poora model `$0.10` par khada hai. Agar account `Essentials` par bana to **+$147/mo**
seedha. Isliye:

> **Console → SES → Pricing plan → "Cancel plan"** (à la carte par wapas).
> Yahi wo step hai jo poore model ko valid rakhta hai.

Ye 7a ke time se pending reminder hai. Ab iska **$147/mo** ka price tag hai.

---

## 1. Teen models, aamne-saamne (2.45M emails/month)

### Aapka ChatGPT model

| Line | $/mo |
|---|---|
| SES (2.45M) | 245.00 |
| VPS | 8.61 |
| S3 archive storage | 8.50 |
| S3 PUT requests | 12.25 |
| S3 GET requests | 0.40 |
| DB backup | 0.50 |
| SNS + SQS | 3.50 |
| Monitoring | 2.00 |
| Retrieval reserve | 2.50 |
| **Subtotal** | **283.26** |
| Tax reserve 18% | 50.90 |
| **Total** | **$334.16** |

### Corrected — managed DB (recommended abhi)

| Line | $/mo | Note |
|---|---|---|
| SES 2.45M | **245.00** | ✅ same |
| SNS (7.35M events) | 3.18 | $0.50/M, 1M free |
| SQS (14.7M req) | 5.48 | $0.40/M, 1M free — **$3.50 kam tha** |
| S3 archive | **0** | hata diya — §3 |
| VPS (Lightsail 4 GB) | **24.00** | $8.61 real nahi tha — §2 |
| Managed PostgreSQL 2 GB | 30.00 | VPS par nahi |
| Backup (snapshots) | 1.00 | |
| Monitoring | 0 | CloudWatch free tier |
| **Subtotal** | **308.66** | |
| GST 18% | 55.56 | |
| **Total** | **$364.22** | |

### Corrected — self-hosted Postgres

| Line | $/mo |
|---|---|
| Ses + SNS + SQS + backup | 254.66 |
| VPS (4 GB, PG usi par) | 24.00 |
| Managed DB | **0** |
| **Subtotal** | **278.66** |
| GST 18% | 50.16 |
| **Total** | **$328.82** |

### 🔍 Asli finding

> **Aapka total ($334.16) actually lagbhag sahi tha — $328-364 ke beech.**
>
> Magar **paisa galat jagah** ja raha tha: $23.65 har mahine **email bodies archive**
> karne mein (jo koi nahi padhta), aur server ke liye $8.61 (jo us kaam ke liye exist
> nahi karta).
>
> Usi paise se ek **asli chalne wala server** aa jata hai. **Total same, allocation sahi.**

---

## 2. Galat #1 — $8.61 ka VPS

Aapke model ne khud likha: *"$8.61/month VPS estimate ki performance verify nahi hui."*
Sahi shak tha. Verify kiya:

| Provider | Plan | $/mo | PG + API + workers? |
|---|---|---|---|
| Hetzner CX22 | 2 vCPU / 4 GB | ~$4-5 | ❌ EU only, ~180ms India se |
| Hostinger KVM 1 | 1 vCPU / 4 GB | ₹599 (~$7) | ⚠️ 1 vCPU, PG ke saath tang |
| **Lightsail 4 GB** | **2 vCPU / 4 GB** | **$24** | ✅ |
| Lightsail 2 GB | 2 vCPU / 2 GB | $12 | ⚠️ PG + API dono ke liye kam |

**$8.61 = ~₹760.** Us range mein sirf Kontabo/Hetzner entry plans hain — India se door,
ya 1 vCPU. Postgres + FastAPI + 2 workers + nginx **4 GB se kam par nahi chalte**
comfortably (Windows par to 8 GB, Linux par 4 GB).

**Sahi line: $24.**

---

## 3. Galat #2 — S3 archive sabse mehnga decision tha

Model mein S3 = **$23.65/mo** — SES ke baad doosra sabse bada line item. Verify kiya:

| Cheez | Rate | Model mein |
|---|---|---|
| S3 Standard storage | $0.023/GB | $8.50 (340 GB) |
| PUT | $0.005 / 1,000 | **$12.25** ✅ sahi ginti |
| GET | $0.0004 / 1,000 | $0.40 |

**Ginti sahi hai. Decision galat hai.**

Kyun: ye bodies **koi padhta nahi.** Dashboard status dikhata hai, content nahi. Customer
ko 6 mahine purana receipt body se nahi chahiye — status chahiye.

### Sasta raasta

| Raasta | $/mo | Kya milta hai |
|---|---|---|
| **30 din baad delete** (Phase 7c, already bana) | **$0** | status + timeline hamesha |
| S3 archive 1 saal | $23.65 | body 1 saal |
| S3 archive + Glacier | ~$4 | body 1 saal, restore mein 5-12 ghante |

**$23.65/mo = $284/saal** ek feature ke liye jo koi use nahi karta. Ye paisa server mein
lagao.

> Agar **compliance** ki zaroorat ho (kuch industries mein hai) tab S3 lena — magar
> **Glacier Instant Retrieval** ($0.004/GB) mein, Standard mein nahi. 340 GB = **$1.36/mo**,
> $8.50 nahi.

---

## 4. Galat #3 — SNS/SQS kam aankaa gaya

| | Aapka | Asli |
|---|---|---|
| SNS | $3.50 (combined) | **$3.18** |
| SQS | — | **$5.48** |
| **Total** | **$3.50** | **$8.66** |

Kyun: **SQS har receive aur har delete ko bhi request maanta hai.**
7.35M events (3 per email) → 7.35M receive + 7.35M delete = 14.7M requests × $0.40/M
= $5.88, minus 1M free = **$5.48**.

SNS side: 7.35M publishes × $0.50/M − 1M free = **$3.18**. SNS→SQS delivery **free** hai.

**Farq $5/mo** — chhota, magar model mein line hi nahi thi.

---

## 5. Galat #4 — "Redis self-host if required"

Model mein Redis ka provision hai. **Zaroorat nahi.**

Aapke paas `outbox_events` already hai — durable, lease-fenced, crash-recoverable,
145 tests ke saath. Redis add karna = naya service, naya failure mode, **zero** naya
guarantee. 14 emails/sec par Postgres queue aaram se kaafi hai.

**Line item hatao: $0.**

---

## 6. Galat #5 — "Phase 7 = analytics, Phase 6 = SES"

Ye status outdated hai. Aaj:

| Phase | Kya | Status |
|---|---|---|
| 6 | SES provider + `send_test` | ✅ **code done** (live test pending) |
| 7a | Per-tenant domain verification | ✅ **committed** `ee5b4a7` |
| 7b | Daily quota + recipient guard | ✅ **committed** `331c393` |
| 7c | Events, suppression, auto-pause, retention | ✅ **committed** `0a08d6d` |
| 9 | Dashboard + analytics | ⬜ next |

Storage ka faisla bhi ho gaya: **bodies 30 din** (7c), archive nahi.

---

## 7. Sahi kya tha — credit dena chahiye

| Point | Verdict |
|---|---|
| SES à la carte $0.10 choose karna | ✅ **sahi**, aur wajah sahi thi (apna dashboard, VDM ka paisa nahi) |
| $245 for 2.45M emails | ✅ **bilkul sahi** |
| S3 PUT ginti $12.25 | ✅ **sahi** (2.45M / 1000 × $0.005) |
| 18% tax reserve | ✅ **sahi** — AWS India (AISPL) prices GST-exclusive hain |
| Apna analytics, VDM nahi | ✅ sahi |
| "VPS price unverified hai" | ✅ **sahi shak** — aur wahi sabse bada error nikla |
| "Free tier paid revenue se cover nahi ho raha" | ✅ **sahi**, aur ye asli problem hai — §8 |
| "Loss mein hai" | ✅ sahi |
| Managed DB reject karna (cost ke liye) | ⚠️ **context pe depend** — pre-revenue credits ke saath managed safer |
| Own MTA evaluate karna | ✅ sahi, aur sahi reject kiya |
| S3 archive choice | ❌ galat priority |
| Redis provision | ❌ zaroorat nahi |

---

## 8. Asli problem — free tier, infrastructure nahi

Model khud kehta hai: **2M free (81.6%) + 450K paid (18.4%)**.

| | Emails/mo | SES cost | Revenue |
|---|---|---|---|
| Free | 2,000,000 | **$200** | **$0** |
| Paid (15 × $9/30k) | 450,000 | $45 | **$135** |
| **Total** | 2,450,000 | $245 | $135 |

**Infrastructure** (VPS + DB + SNS/SQS + backup) = **$62/mo fixed**.
SES $245 + $62 = $307 + GST = **$362 cost** vs **$135 revenue** = **−$227/mo**.

### Infrastructure sasta karke ye nahi badalega

| Kya karo | Bachat | Naya loss |
|---|---|---|
| Self-host PG | $30 | −$197 |
| S3 archive hatao | $24 | −$173 |
| Sab kuch free kar do | $54 | **−$173** |

**Infrastructure $62 hai. SES $245 hai. Problem SES side hai, server side nahi.**

### Do hi lever hain

**Lever 1 — Free tier quota kam karo**

| Free quota | 1,333 devs par | Free SES cost | Total cost |
|---|---|---|---|
| **50/day** (abhi) | 2.0M | **$200** | $362 |
| 20/day | 800K | $80 | $204 |
| **10/day** | 400K | **$40** | **$164** |

Free tier **hataana** nahi — **20/day** karna. Wahi 1,333 developers, 60% kam bill.
(Free tier aapka growth engine hai; 20/day bhi OTP ke liye kaafi hai.)

**Lever 2 — Paid price badhao**

| Price | 450K paid par | Cost $362 cover? |
|---|---|---|
| $9 / 30K ($0.30/1K) | $135 | ❌ |
| $15 / 30K ($0.50/1K) | $225 | ❌ |
| **$25 / 30K ($0.83/1K)** | **$375** | ✅ |
| 450K ko $0.40/1K par (Resend level) | $180 | ❌ |

$0.83/1K mehnga hai Resend ($0.40/1K) se. **Matlab price se alone break-even nahi hoga.**

### Break-even ka asli equation

Cost = **$62 fixed** + $0.0001 × total_emails × 1.18
Revenue = $0.0003 × paid_emails

| Free quota | Free emails | Paid emails | Cost | Revenue | Result |
|---|---|---|---|---|---|
| 50/day | 2.0M | 450K | $362 | $135 | **−$227** |
| 20/day | 800K | 450K | $204 | $135 | −$69 |
| **10/day** | 400K | 450K | **$164** | $135 | −$29 |
| **10/day** | 400K | 900K | $192 | $270 | **+$78** ✅ |
| 10/day | 400K | 1.8M | $247 | $540 | **+$293** ✅ |

> **Break-even: free 10/day + paid volume double (900K).**
> Ya free 20/day + paid 1.2M.

**Infrastructure optimize karke loss −$227 se −$173 hota hai. Free quota 10/day karne se
−$29 hota hai.** Free tier ka quota 8x bada lever hai.

---

## 9. Aaj kya lena hai — 2-4 mahine, credits se

| Cheez | $/mo | Kyun |
|---|---|---|
| **Lightsail Ubuntu 4 GB / 2 vCPU** | **$24** | verified, static IP + transfer included |
| **Lightsail PostgreSQL 2 GB** | **$30** | encryption at rest, backups |
| SES (actual volume) | $0-245 | à la carte **confirm karo** |
| SNS + SQS | $0-9 | free tier se shuru |
| Snapshots | $1 | |
| **Total** | **$55-309** | volume ke hisaab se |

**$1,000 Activate credits par:**
- 50,000 emails/month par → **17 mahine**
- 500,000 emails/month par → **7 mahine**
- 2.45M emails/month par → **3 mahine**

**Self-hosting PG ($30 bachao) tab karo** jab credits khatam hone wale hon ya revenue aa
jaye — abhi nahi. Backup khud manage karna padta hai aur wo beginner ke liye sabse
mahanga "free" hai.

---

## 10. Pura ledger — kya badla

| Item | Pehle (ChatGPT) | **Ab** | Farq |
|---|---|---|---|
| SES rate | $0.10/1K | $0.10/1K (**verify karo!**) | ⚠️ +$147 risk |
| SES signup default | pata nahi tha | **Essentials $0.16** | 🆕 |
| VPS | $8.61 (unverified) | **$24** | +$15 |
| PostgreSQL | self-host, $0 | **managed, $30** | +$30 |
| S3 archive | $19.75 + $23.65 | **$0** (30-day delete) | **−$23.65** |
| SNS | $3.50 | $3.18 | −$0.32 |
| SQS | (combined) | **$5.48** | 🆕 |
| Redis | self-host if needed | **nahi chahiye** | −$0 |
| Monitoring | $2.00 | $0 (free tier) | −$2 |
| Backup | $0.50 | $1.00 | +$0.50 |
| **Subtotal (2.45M)** | **$283.26** | **$308.66** | **+$25** |
| GST 18% | $50.90 | $55.56 | |
| **Total** | **$334.16** | **$364.22** | **+$30** |
| Body retention | 7 din hot + 1 saal S3 | **30 din, phir delete** | 🆕 |
| Incident payload retention | — | **7 din** (7c, aaj) | 🆕 |
| Free tier quota | 50/day | **50/day** (recommend 20) | ⚠️ |
| Break-even | "loss mein hai" | **free 10/day + 900K paid** | 🆕 number |

**Aapka $334.16 galat nahi tha — $364.22 zyada sahi hai**, kyunki usme ek asli server hai
aur ek feature hataya hai jo koi use nahi karta.
