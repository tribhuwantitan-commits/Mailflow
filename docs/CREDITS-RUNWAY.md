# $1,600 ka 8-mahine plan — EC2 bucket aur email bucket

Do funds: **$400 infra** (EC2 + Redis + Postgres) aur **$1,200 email** (SES + SQS + SNS).
Target: **5-8 mahine** bina extra paise daale.

---

## 0. Sabse pehle — aapka $400 bucket alag jagah ja raha hai

Aapne kaha "$400 EC2, Redis aur Postgres ke liye". Verify kiya:

| Cheez | Zaroorat? | Kyun |
|---|---|---|
| **Redis** | ❌ **nahi** | `outbox_events` already queue hai (durable, lease-fenced, 146 tests). Redis = naya service, naya failure mode, **zero** naya guarantee. |
| **Postgres** | ✅ **haan** | managed lena hai — backup khud karna beginner ke liye sabse mehanga "free" hai |
| **EC2** | ✅ **haan**, magar Windows par nahi | |

**Redis wala paisa bacha.** Pura $400 server + DB mein lagao.
(Detail: `COST-MODEL-RECONCILIATION.md` §5, `AWS-ONLY-PLAN.md` §11.)

---

## 1. 🔴 Pehle ek money bug — fix ho gaya

Aapke **current plan catalogue** mein daily limits itne bade the ki:

| Plan | Purana daily | **Monthly (×30)** | SES cost | Price | Result |
|---|---|---|---|---|---|
| Starter | 5,000 | **150,000** | $15.00 | $5 | **−$10.00** ❌ |
| Growth | 15,000 | **450,000** | $45.00 | $10 | **−$35.00** ❌ |
| Scale | 40,000 | **1,200,000** | $120.00 | $15 | **−$105.00** ❌ |
| Business | 60,000 | **1,800,000** | $180.00 | $20 | **−$160.00** ❌ |

> **Scale plan ka ek customer poora $400 infra bucket ek mahine mein kha jata.**
> Aur `free_card` par 100/day = **3,000/month** tha — Starter (150K) ke saamne upgrade
> ki koi wajah nahi.

**Fix (migration `0008_plan_pricing`):** rule lagaya — **plan ki monthly limit × $0.10/1K
uski price ke 40% se zyada nahi.**

| Plan | **Naya daily** | Monthly ceiling | SES | **Price** | Margin |
|---|---|---|---|---|---|
| Free | 50 | 1,500 | $0.15 | $0 | *acquisition cost* |
| Free card | 100 | 3,000 | $0.30 | $0 | *acquisition cost* |
| **Starter** | **1,000** | 30,000 | $3.00 | **$9** | **67%** |
| **Growth** | **2,500** | 75,000 | $7.50 | **$19** | **61%** |
| **Scale** | **5,800** | 174,000 | $17.40 | **$39** | **55%** |
| **Business** | **13,000** | 390,000 | $39.00 | **$79** | **51%** |

Aur ek test (`test_every_paid_plan_can_afford_its_own_worst_case`) ab **deploy rok dega**
agar koi aage chal kar limit ko price se zyada bada kare.

**₹ pricing** ($1 = ₹89): Starter ₹799 · Growth ₹1,699 · Scale ₹3,499 · Business ₹6,999.

> **Ye pricing Resend/Postmark se sasti hai:** $0.30/1K vs Resend $0.40/1K,
> Postmark $1.50/1K. Aur 55-67% margin deti hai.

---

## 2. Infra plan — $400 se kitne mahine

### Option A — Managed DB (recommended)

| Cheez | $/mo |
|---|---|
| Lightsail Ubuntu 4 GB / 2 vCPU | $24 |
| **Lightsail PostgreSQL 2 GB** (encryption, backups) | $30 |
| Snapshots | $1 |
| **Total** | **$55** |

**$400 ÷ $55 = 7.2 mahine** ✅

### Option B — Sab usi server par (Postgres self-hosted)

| Cheez | $/mo |
|---|---|
| Lightsail Ubuntu **8 GB** / 2 vCPU (PG ke saath) | $44 |
| Snapshots | $1 |
| **Total** | **$45** |

**$400 ÷ $45 = 8.8 mahine** ✅

> **A vs B:** B 1.6 mahine zyada deta hai, magar **backup khud** karna padega
> (roz `pg_dump` → S3). Pehle 2 mahine A chalao, phir B par jao jab setup settle ho jaye.
>
> **Beech ka raasta:** pehle 3 mahine A ($165), phir 5 mahine B ($225) = **$390,
> 8 mahine** ✅ — aur shuru mein managed DB ka aaram.

### Lightsail CPU ka limit (important)

2 vCPU ka **baseline 20%** hai — 0.4 core sustained, 2 core tak burst.

| Load | CPU chahiye | |
|---|---|---|
| 2,000 tenants, ~20k emails/day | ~0.15 core | ✅ |
| 10,000 tenants, ~100k emails/day | ~0.4 core | ✅ **edge** |
| 20,000 tenants | 0.8 core | ❌ 8 GB plan ($44, 30%) lo |

**Signal:** Lightsail console → CPU graph "sustainable" zone se bahar ghanton rahe to
upgrade karo (one click). **8 vCPU ($164) kabhi nahi** — wo $400 ko 2.4 mahine mein
kha jayega.

---

## 3. Email bucket — $1,200 se kitne mahine

Verification ke baad, **3 events per email** (Send + Delivery + open), SQS receive+delete:

**Cost = $0.0004 × total_emails + $0.40 × $/month** (SNS+SQS ≈ $0.0004/email)

| Total emails/month | SES | SNS+SQS | **$/mo** | **$1,200 se mahine** |
|---|---|---|---|---|
| 50,000 | $5.00 | $0.04 | **$5** | **240** (budget hi khatam nahi) |
| 100,000 | $10.00 | $0.06 | **$10** | **120** |
| 200,000 | $20.00 | $0.10 | **$20** | **60** |
| 500,000 | $50.00 | $0.20 | **$50** | **24** |
| 1,000,000 | $100.00 | $0.36 | **$100** | **12** |
| **2,000,000** | $200.00 | $0.72 | **$201** | **6** |
| 3,000,000 | $300.00 | $1.08 | **$301** | **4** |

### 🔍 Asli finding

> **8 mahine ke liye aapko 20 lakh emails/month tak jaane ki poori chhoot hai.**
>
> **Email bucket 8 mahine mein khatam hi nahi hoga** — 500k/month par to **2 saal**
> chalega. Aapka $1,200 email ke liye **over-provisioned** hai; asli limit **infra**
> hai.

---

## 4. Conversion rate — realistic numbers

Benchmarks (2026, 5 sources):

| Model | Median | Top quartile |
|---|---|---|
| **Freemium, self-serve B2B** | **2–5%** | 5–10% |
| **Developer tools / API** | **2–4%** (median 4.8%) | 10–18% |
| Card-required trial | 25–49% | — |
| *("25% normal hai" — 200 products ke survey mein **median 8%**, aur wo trial-heavy sample hai)* |

**Aapki position:** API product, **no credit card at signup**, free tier generous hai.
Yani **freemium/dev-tools bracket**.

**Plan karne ke liye use karo: 2% (base), 3% (realistic), 5% (accha).**

> Ye 5% wala number hi "accha" hai. 25% mat maano — wo folklore hai.

---

## 5. Email volume estimate — realistic

Ek B2B developer ka normal usage:

| Use case | Emails/day |
|---|---|
| Transactional only (receipt, password) | 5–20 |
| OTP/verification | 50–200 |
| Mixed (OTP + alerts) | **80–150** |
| Marketing bulk | 1,000+ |

Aapke quotas (50/day free, 100 card) **use case ke hisaab se** set hain, isliye plan ke liye
**~100 emails/day/tenant** maano — matlab free tenant 30K/month.

Ye important hai: **ek free tenant Starter (30K) ke barabar consume kar sakta hai.**
Isliye free tier ka quota sabse bada cost lever hai (`COST-MODEL-RECONCILIATION.md` §8).

---

## 6. Month-by-month realistic scenario

Assume: beta se shuru, IndieHackers/LinkedIn/Reddit se signups, **3% conversion**.

| Month | Tenants (total) | Free | Paid | Paid mix | Emails/mo | SES | **Revenue** | **Total cost** | Net |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 5 | 0 | — | 5k | $0.50 | $0 | $55 | **−$55** |
| 2 | 20 | 20 | 0 | — | 30k | $3 | $0 | $55 | **−$55** |
| 3 | 50 | 48 | **2** | 2× Starter $9 | 120k | $12 | **$18** | $60 | **−$42** |
| 4 | 120 | 116 | **4** | 3×S + 1×G | 300k | $30 | **$46** | $70 | **−$24** |
| 5 | 250 | 242 | **8** | 5×S + 2×G + 1×Sc | 700k | $70 | **$122** | $95 | **+$27** ✅ |
| 6 | 400 | 386 | **14** | 8×S + 4×G + 2×Sc | 1.1M | $110 | **$230** | $125 | **+$105** ✅ |
| 7 | 550 | 531 | **19** | 10×S + 6×G + 3×Sc | 1.5M | $150 | **$325** | $160 | **+$165** ✅ |
| 8 | 700 | 676 | **24** | 12×S + 8×G + 4×Sc | 1.9M | $190 | **$428** | $200 | **+$228** ✅ |

**Cumulative (8 mahine):**

| | Amount |
|---|---|
| Revenue | **$1,169** |
| Total cost | **$820** |
| **Net** | **+$349** ✅ |

Aur email bucket se kharcha: $565 of $1,200 — **$635 bacha**.
Infra bucket: $390 of $400 — poora use ho gaya, magar revenue aane lage to self-fund.

> **Break-even month 5.** Us se pehle ~$180 apni jeb se ya credits se.

---

## 7. Agar growth slow rahe — worst case

Conversion 1.5% aur signups half:

| Month | Tenants | Paid | Revenue | Cost | Cum. loss |
|---|---|---|---|---|---|
| 1-3 | 25 | 0 | $0 | $165 | −$165 |
| 4-6 | 120 | 2 | $18 | $270 | −$417 |
| 7-8 | 250 | 4 | $37 | $180 | **−$560** |

**Matlab worst case: 8 mahine mein ~$560 apni jeb se.** Ye aapka **asli risk cap** hai —
aur ye $1,600 credits ke andar hai, to cash nahi dena padega.

---

## 8. Kya karo agar month 4 tak conversion 2% se neeche ho

| Signal | Action |
|---|---|
| Signups aa rahe, activation kam | Onboarding fix — **activation 4.1x conversion badhata hai** |
| Activation theek, paid 0 | **Pricing/wall galat jagah hai** — free 50/day se 20/day karo (upgrade pressure) |
| Free 50/day par heavy users | Wo **best targets** hain — unhe personally email karo |
| Bilkul signups nahi | Distribution problem — product problem nahi. 20 interviews. |

**Sabse zyada impact wala ek kaam:** free quota **20/day** karna. Isse upgrade pressure
banti hai **aur** aapka #1 cost ($0.15/free-tenant/month) 60% girta hai. **Dono taraf jeet.**

---

## 9. Free tier ka asli cost — aur limit

| Free quota | Emails/month/tenant | SES cost/tenant/mo |
|---|---|---|
| **50/day** (abhi) | 1,500 | **$0.15** |
| 20/day | 600 | $0.06 |
| 10/day | 300 | $0.03 |

**50/day par 676 free tenants (month 8) = $101/mo** — aapke $200 total cost ka **aadha**.
20/day par wahi **$41**.

**Max safe free tenants (8 mahine ke credits par):**

| Free quota | Break-even tenants |
|---|---|
| 50/day | ~700 |
| **20/day** | ~1,600 |
| 10/day | ~3,000 |

---

## 10. Ek page ka summary

| | |
|---|---|
| **Infra bucket** | $400 ÷ $50/mo = **8 mahine** ✅ |
| **Email bucket** | $1,200 ÷ $200/mo (20 lakh emails) = **6 mahine** — aur 5 lakh/month par **2 saal** |
| **Realistic conversion** | **3%** (2% base, 5% accha) |
| **Month 8 realistic** | 700 tenants, 24 paid, **$428 MRR**, net +$228 |
| **Break-even** | **Month 5** |
| **Worst-case cash burn** | ~$560 (credits ke andar) |
| **Redis** | ❌ mat lo |
| **8 vCPU** | ❌ mat lo — $164/mo |
| **SES plan** | ✅ à la carte confirmed ($0.10) |
| **Free quota** | 50/day theek hai; **20/day** se margin 60% behtar |
| **Pricing** | Starter $9 / Growth $19 / Scale $39 / Business $79 |
