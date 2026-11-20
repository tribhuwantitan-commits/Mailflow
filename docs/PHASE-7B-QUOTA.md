# Phase 7b — quota enforcement aur per-recipient guard

Status: **implemented on `arena/67b5c744-mailflow`.** Tests: **90 passed, 1 skipped.**
PostgreSQL par nahi chala (Neon connection string abhi tak nahi mila) — sirf SQLite.

---

## 1. Kya bana

| Cheez | File | Kaam |
|---|---|---|
| `sending_plans` table | `app/models/quota.py` | plan catalogue: daily email/recipient limit, per-email recipients, per-recipient cap, price |
| `usage_daily` table | `app/models/quota.py` | ek row per (tenant, UTC din): kitne emails/recipients kharch hue |
| `recipient_daily_counts` | `app/models/quota.py` | per-recipient counter (OTP bombing rok) |
| `organizations.plan` + `plan_overrides` | `app/models/organization.py` | tenant kis plan par hai; support ek tenant ko limit de sakta hai |
| `reserve_send()` | `app/services/quota.py` | atomic reservation — limit cross ho to kuch bhi write nahi hota |
| `GET /v1/emails/usage` | `app/api/emails.py` | dashboard ke liye aaj ka usage + limits |
| Migration `0005_quota` | `alembic/versions/0005_quota.py` | tables + seed catalogue |

---

## 2. Plan catalogue (launch)

| Slug | Daily emails | Daily recipients | Max per email | Per-recipient cap | Price |
|---|---|---|---|---|---|
| **`free`** ← default | **50** | 50 | **5** | **10/day** | $0 |
| `free_card` | 100 | 100 | 10 | off | $0 |
| `starter` | 5,000 | 5,000 | 50 | off | $5 |
| `growth` | 15,000 | 15,000 | 50 | off | $10 |
| `scale` | 40,000 | 40,000 | 50 | off | $15 |
| `business` | 60,000 | 60,000 | 50 | off | $20 |

**Naya tenant hamesha `free` par aata hai** (`server_default="free"`), kyunki
`plan` column NOT NULL hai aur FK `sending_plans.slug` par. Matlab: **naya org
kabhi unlimited nahi hota** — ye silent failure ka sabse aam type tha.

### Kyun `per_recipient_daily_limit` sirf free par

Free plan par ek address ko **10 emails/day** se zyada nahi. Isse OTP bombing
(free account se kisi ko 500 emails bhejna) ruk jati hai. Paid plans par ye off
hai (`0`), kyunki paying customer ki apni list hoti hai.

### `plan_overrides` — support ke liye

```
organizations.plan = 'free'
organizations.plan_overrides = '{"daily_email_limit": 500}'
```

Overrides plan se **jeette** hain, magar **limit hata nahi sakte** (negative
ignore hota hai, plan value reh jati hai). Isse ek tenant ko bada limit de sakte
ho, bina naya plan banane ke.

---

## 3. Atomicity — sabse important design decision

Quota check **ek single locked UPDATE** hai, email insert ke **same transaction**
mein:

```sql
UPDATE usage_daily
   SET emails_sent = emails_sent + 1,
       recipients_sent = recipients_sent + $2
 WHERE organization_id = $1
   AND usage_date = CURRENT_DATE
   AND emails_sent + 1 <= $3
   AND recipients_sent + $2 <= $4;
-- rowcount == 0  →  limit cross  →  raise 429, kuch bhi write nahi
```

**Kyun:** do concurrent requests "ek slot bacha hai" dono dekh lete, aur dono le
lete. Lock ke saath sirf ek jeetta hai. Test `test_last_slot_cannot_be_taken_twice`
yahi verify karta hai.

**Order matters:**
```
1. idempotency lookup   ← replay yahan ruk jayega, quota nahi khayega
2. reserve_send()       ← limit cross to 429, kuch insert nahi
3. INSERT email
4. INSERT outbox event
5. COMMIT               ← dono ya koi nahi
```

Idempotent replay step 1 par return hota hai — isliye **replay quota double nahi
karta**. Ye test `test_idempotent_replay_does_not_consume_quota_twice` cover karta hai.

---

## 4. API behaviour

### Limit cross ho to

```http
HTTP/1.1 429 Too Many Requests
X-Quota-Plan: free
X-Quota-Limit: 50
X-Quota-Remaining: 0
Retry-After: 3600

{"error": {"code": "email_quota_exceeded",
           "message": "Daily limit of 50 emails reached for this plan."}}
```

| Code | Kab |
|---|---|
| `email_quota_exceeded` | daily email limit khatam |
| `recipient_quota_exceeded` | daily recipient limit khatam |
| `too_many_recipients` | ek email mein plan se zyada `to:` |
| `recipient_daily_limit_exceeded` | ek address ko cap se zyada (free) |
| `plan_not_configured` | **(503)** plan row hi nahi mil raha — fail closed |

### Successful send par

`202` ke saath `X-Quota-Remaining` header aata hai — SDK ko extra call nahi karni padegi.

### Naya endpoint

```http
GET /v1/emails/usage
X-API-Key: mfk_...
```

```json
{
  "plan": "free",
  "limit": {"daily_emails": 50, "daily_recipients": 50,
            "max_recipients_per_email": 5, "per_recipient_daily_limit": 10},
  "used": {"emails": 12, "recipients": 12},
  "remaining": {"emails": 38, "recipients": 38},
  "resets_at": "2026-11-11T24:00:00Z"
}
```

Dashboard / settings page yehi use karega (Phase 9).

---

## 5. Reset = UTC midnight

```
usage_date = UTC ka din
```

**Kyun UTC:** customers poore world se hain; local midnight par reset karne ka
matlab plan database timezone par depend kare. UTC predictable hai.

**Trade-off:** India mein UTC midnight = **5:30 AM IST**. Free user jo raat 1 baje
(IST) kaam karta hai, uske liye "din" 5:30 AM par badalta hai. Ye Resend/SendGrid
jaisa hi hai, aur dashboard par `resets_at` dikhta hai — confusion nahi hoti.

---

## 6. Purani rows — cleanup chahiye

`usage_daily` aur `recipient_daily_counts` **roz badhti hain**:

| Rows/day | Monthly |
|---|---|
| 20,000 tenants × 1 = 20,000 | **600,000 rows** |

Ye chhota hai (ek row ~50 bytes = 300 MB/month by month 12), magar **cleanup
job** chahiye:

```sql
DELETE FROM usage_daily              WHERE usage_date < CURRENT_DATE - 90;
DELETE FROM recipient_daily_counts   WHERE usage_date < CURRENT_DATE - 7;
```

`usage_daily` 90 din (analytics ke liye), `recipient_daily_counts` 7 din (guard
ke liye kaafi). Index `ix_recipient_daily_counts_date` isi delete ke liye hai.

⚠️ **Ye job abhi nahi bana.** Phase 9 (dashboard) ke saath jayega — ya usse pehle
ek simple script. Bina iske table badhta rahega.

---

## 7. Kya **nahi** bana (jaan-boojh kar)

| Cheez | Kyun nahi | Kab |
|---|---|---|
| **Per-second rate limit** | daily quota se alag. `usage_daily` second ka hisaab nahi rakhta | Phase 7c ke baad, agar chahiye |
| **Billing / plan upgrade** | koi payment gateway nahi hai abhi | Phase 10 |
| **Plan change API** | `UPDATE organizations SET plan=` direct chalega, magar admin UI nahi | Phase 9 |
| **Burst detection / auto-pause** | bounce/complaint data nahi hai abhi | Phase 7c |
| **Redis-based limiter** | DB par sahi chalta hai 20k tenants tak; Redis 500k par | scale par |
| **Cleanup job** | upar dekho | Phase 9 |

### Per-second limit ka jawab kya hai?

Daily quota **spike nahi rokta** — ek customer apna 50/day **1 second** mein bhi
use kar sakta hai. Spike protection ke teen layer hain:

| Layer | Kya rokti hai | Status |
|---|---|---|
| API concurrency (workers + threads) | total throughput | infra ✅ |
| **Daily quota** | total volume per tenant | ✅ **abhi** |
| Per-recipient cap | ek address ki bombing | ✅ **abhi** |
| Per-second / per-minute | burst | ❌ later |

**Abhi ke liye daily quota + outbox queue kaafi hai** — kyunki sends SES tak
queue se jaate hain, API se nahi. 5,000 emails ek second mein daal diye to queue
mein wait karenge, SES nahi phat jayega.

Magar **SES quota** alag hai (50k/day) — wo `usage_daily` se **alag** track hoga
jab worker banega.

---

## 8. Migration chalao

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
```

Verify:
```powershell
.venv\Scripts\python.exe -m alembic current
# 0005_quota (head)
```

Rollback (testing mein):
```powershell
.venv\Scripts\python.exe -m alembic downgrade 0004_worker
```

⚠️ **Downgrade se `sending_plans` aur `usage_daily` delete ho jate hain** — production
par mat chalao.

### Neon par ek extra baat

Migration **unpooled endpoint** se chalao (pooled `search_path` reject karta hai —
ye pehle bhi phansa tha). `.env` mein `DATABASE_URL` unpooled rakh do, migration ke
baad API ke liye pooled par switch kar sakte ho.

---

## 9. Aage kya — updated order

| # | Phase | Kya | Ab |
|---|---|---|---|
| 1 | **6.5** | SES live test (`check_ses`, `send_test`) | 🟡 aapke PC par pending |
| 2 | **7b** | quota + per-recipient guard | ✅ **done** |
| 3 | 7a | per-customer domain verification + per-tenant `Source` | next |
| 4 | 7c | SNS/SQS events + suppression + auto-pause + `List-Unsubscribe` |  |
| 5 | 9 | dashboard + `usage_daily` cleanup job |  |
| 6 | 10 | billing / plans / card verification |  |

⚠️ **7c pehle nahi ho sakta?** 7a ki zaroorat hai kyunki AWS production access ke
liye "customer apna domain verify karta hai" chahiye. Aur `app/providers/ses.py`
line ~73 abhi bhi `Source=self.settings.ses_from_email` hardcode karta hai — wo
7a mein badlega.

---

## 10. Checklist — 4 cheezein

| # | Kaam | Kaise |
|---|---|---|
| 1 | Migration chalao | `alembic upgrade head` |
| 2 | `free` plan default hai verify karo | `SELECT slug, daily_email_limit FROM sending_plans;` |
| 3 | Ek send karo, usage dekho | `GET /v1/emails/usage` |
| 4 | Cleanup job plan karo | Phase 9 mein |
