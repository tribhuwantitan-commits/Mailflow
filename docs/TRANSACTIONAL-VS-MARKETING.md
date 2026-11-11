# Transactional vs Marketing — definition, separation, aur kab kya banega

**Decision:** dono rahenge, par **alag product lines** — alag sending stream, alag
reputation, alag code path, alag pricing. Marketing baad mein (Phase 12+), aur us waqt
tak transactional akela ship hoga.

---

## 1. Transactional kya hota hai

Rule (feeling se nahi, rule se): **recipient ke apne action se trigger ho, ya legal/
security obligation ho → transactional. Business promotion ho → marketing.**

### Poori list — transactional

| Category | Examples |
|---|---|
| **Authentication / access** | OTP, login code, magic link, 2FA setup, email verification, signup confirmation |
| **Password** | password reset link, password changed notice, account locked |
| **Security alerts** | new device login, suspicious activity, API key created/revoked, session revoked |
| **Payments** | receipt, invoice, payment confirmed, payment failed, dunning (retry notice), refund issued, subscription renewed |
| **Orders** | order confirmation, shipping/tracking update, delivery status, return/exchange status |
| **Account/ops** | usage quota warning, billing alert, plan changed, service outage notice, maintenance window |
| **Collaboration (1:1 event)** | team invite (inviter → invitee), task assigned, comment mention, share granted |
| **Async job output** | export ready, report ready, backup complete, invoice generated |
| **Support** | ticket reply notification, ticket closed |

### Borderline — rule se decide karo

| Email | Verdict | Kyun |
|---|---|---|
| Welcome email (sirf greeting) | transactional | user ne signup kiya |
| Welcome email **+ discount code** | **marketing** | promotion primary purpose hai |
| Trial expiring (fakt "trial khatam ho raha hai") | transactional | user ka account state |
| Trial expiring **+ "upgrade karo 20% off"** | **marketing** | upsell primary purpose |
| Product update / new feature announcement | **marketing** | user action ne trigger nahi kiya |
| NPS / feedback survey | **marketing** | — |
| Cart abandonment | **marketing** | promotional (India: DPDP consent) |
| Re-engagement / "hum yaad kar rahe hain" | **marketing** | — |
| Newsletter, blog digest | **marketing** | — |

### ⚠️ "Transactional+" trap — ye galti mat karna

Sabse common galti: "transactional mail ka open rate zyada hai, to receipt ke neeche
offer chipka do." Iske teen nuksan:

1. **Reputation**: promotional content spam filters ko signal deta hai; complaint rate
   badhta hai; aapka OTP bhi spam mein jaane lagta hai.
2. **Legal**: US CAN-SPAM mein "primary purpose" test hai — agar email ka main maqsad
   promotion hai, to wo commercial mail hai aur unsubscribe requirement lagti hai,
   chahe usme receipt ho. India ke DPDP Act mein bhi consent ka scope isi tarah kaam
   karta hai.
3. **Product**: aapke customer ko pata nahi hota ki uski OTP mail ke saath aapka
   offer kisne bheja — trust tootta hai.

Isliye: **stream ka faisla API endpoint se hota hai, content se nahi.**
`POST /v1/emails` = transactional. `POST /v1/campaigns` = marketing. Ek hi email body
do jagah accept nahi hogi.

---

## 2. Marketing alag kyun hona chahiye — 3 layer separation

| Layer | Transactional stream | Marketing stream |
|---|---|---|
| **AWS account** | main account | **alag account** (recommended) |
| SES config set | `mailflow-transactional` | `mailflow-marketing` |
| Sending subdomain | `mail.customer.com` | `news.customer.com` (alag DKIM) |
| SNS topic → SQS queue | `mf-txn-events` | `mf-mkt-events` |
| Worker | `outbox_events` (existing) | `campaign_recipients` (bulk, chunked) |
| API | `POST /v1/emails` | `POST /v1/campaigns` |
| IP | shared SES IPs | **dedicated/managed IP** (volume par) |
| Quota | 50-100/day free | paid only, per-campaign caps |
| Suppression | per-address | **per-list + global complaints** |

### Alag AWS account kyun (sirf config set se kaam nahi chalta)

SES ke bounce/complaint thresholds aur Trust & Safety enforcement **account-level**
hote hain. Agar marketing wahi account hai:

> Ek customer ka galat list import → 12% bounce → **AWS poora account pause** →
> aapke saare customers ki **OTP aur password reset band**. Login toot gaya.

SES **Tenants** se ye risk kam hota hai (per-tenant pause), par AWS docs saaf kehte hain
combined activity account reputation ko affect karti hai. **Do account = zero blast
radius**, aur cost extra zero hai (sirf ek free AWS account).

Bill consolidation ke liye AWS Organizations use kar sakte hain. Dhyan: Activate credits
jis account par mile hain usi par lagte hain — marketing account alag bill karega.

---

## 3. Marketing system mein kya-kya chahiye (yehi "strong antispam")

### Consent & compliance (non-negotiable)

- **Consent ledger**: kaun, kab, kis source se opt-in hua (form URL, IP, timestamp,
  double opt-in confirmation) — DPDP/GDPR mein ye proof chahiye
- **Double opt-in** default; single opt-in ko explicitly allow karna pade
- **Unsubscribe**: RFC 8058 one-click (`List-Unsubscribe` + `List-Unsubscribe-Post`),
  public token-based endpoint, instantly honored (24h legally, practically seconds)
- **Preference center** (topics frequency)
- **AUP enforcement**: purchased/scraped lists contract se banned, aur technically bhi
  block (import par verification)

### Deliverability guardrails

- **Pre-send email validation** (ZeroBounce/NeverBounce ~$0.004/address) — bounce 5% se
  neeche rakhne ka sabse asaan tareeka
- **Bounce/complaint auto-pause** per campaign aur per tenant (threshold marketing ke
  liye sakht: bounce <2%, complaint <0.08%)
- **Warm-up ramp**: naye domain/IP par day 1 = 200, day 2 = 500 ... 2-4 hafte
- **Rate throttle** per second + per hour; SES rate limit se race na ho
- **Blocklist monitoring** (Spamhaus), DMARC aggregate reports
- **Content check** pre-send: spam keywords, link reputation, image/text ratio,
  HTML validity (SpamAssassin rules ka subset)
- **Kill switch** per campaign + global (ek button, sab marketing ruk jaye,
  transactional chalta rahe)

### Product features (marketing-specific)

- Contact lists, segments, custom fields
- Campaign: template + subject + audience → draft → review → scheduled → sending → done
- **New account ka pehla campaign manual review** — Resend/Brevo yahi karte hain, aur
  yahi sabse bada spam-rok hai
- Batch send API (SES `SendBulkEmail` / templated)
- Open/click tracking (yahi wo jagah hai jahan ye metrics matter karte hain)
- Campaign stats: delivered, bounce, complaint, unsub, open, click
- A/B subject testing, scheduling, send-time optimization (baad mein)

---

## 4. Cost (jo aapne "high cost" kaha — sahi hai)

| Item | Rate | 100k emails/month |
|---|---|---|
| SES sending (separate account) | $0.10/1K (à la carte) | $10 |
| **Managed dedicated IP** | $15/mo + $0.08/1K | $15 + $8 = **$23** |
| Email validation | ~$0.004/address | $400 (100k validated) |
| Tracking domain + ACM | free | $0 |
| SNS/SQS | free tier | $0 |
| **Rough total** | | **~$30-45** (validation optional/partial) |

Validation sabse mehnga hai — isliye smart approach: sirf **naye/imported** addresses
validate karo, dobara nahi. Aur validation ko paid plan ka feature rakho.

Toh marketing stream transactional se **~3x mehnga** padta hai, aur isliye uski pricing
bhi alag honi chahiye (per 1,000 emails zyada, plus plan fee).

---

## 5. Code structure (ek repo, do streams)

```
app/
  providers/
    ses.py                  # shared boto3 adapter, but two clients
    __init__.py             # get_email_provider() / get_marketing_provider()
  services/
    outbox.py               # transactional (existing, untouched)
    campaigns.py            # NEW: bulk enqueue + chunked sending + throttle
    suppression.py          # NEW: shared read, stream-scoped write
  api/
    emails.py               # /v1/emails  (existing)
    campaigns.py            # /v1/campaigns, /v1/contacts, /v1/unsubscribe
  models/
    delivery.py             # email_messages, outbox_events (existing)
    marketing.py            # NEW: contacts, consents, campaigns, campaign_recipients
```

### Settings (additive, transactional untouched)

```python
# transactional (existing)
mail_provider: Literal["fake", "ses"]
aws_region, aws_access_key_id, aws_secret_access_key, ses_from_email,
ses_configuration_set

# marketing (new, separate account)
marketing_enabled: bool = False
marketing_aws_region: str = "ap-south-1"
marketing_aws_access_key_id: str | None
marketing_aws_secret_access_key: SecretStr | None
marketing_configuration_set: str | None
marketing_tracking_domain: str | None   # links.news.example.com
marketing_daily_cap: int = 0            # 0 = disabled
```

`marketing_enabled = False` by default — jab tak pipeline na bane, code chalta rahe
magar marketing endpoints 404/403 dein. Isse transactional ka behaviour bilkul nahi
badalta.

### Key isolation rule (code level)

`get_email_provider()` **kabhi** marketing credentials use nahi karega, aur
`get_marketing_provider()` transactional credentials use nahi karega. Do function, do
clients. Ye ek test se enforce karo — warna 6 mahine baad koi galti kar dega.

---

## 6. Phasing (revised — marketing ab end mein)

| Phase | Kaam | Stream |
|---|---|---|
| 6.5 | SES live test, DKIM/SPF/DMARC | txn |
| 7a | per-customer domain verification + per-tenant `Source` | txn |
| 7b | quota + per-recipient rate limit (OTP bombing guard) | txn |
| 7c | SNS/SQS events + suppression + auto-pause | txn |
| 7d | dashboard (latency, failures, timeline) | txn |
| 8 | paid plans + card verification | txn |
| **9** | **marketing: separate AWS account + config set + subdomain discipline** | mkt |
| 10 | consent ledger + unsubscribe + preference center | mkt |
| 11 | contacts/lists + campaign send engine + throttle + warm-up | mkt |
| 12 | validation + content check + blocklist + manual review | mkt |
| 13 | campaign analytics (open/click) + A/B | mkt |

Marketing alag ship hoga — alag pricing, alag onboarding, alag dashboard. Transactional
product pehle revenue banayega, marketing uske baad.

**Important:** Phase 9-13 ka kaam transactional ke kaam se **3-5x** hai. Isliye
transactional ko pehle poora karo, warna dono adhoore rahenge.

---

## 7. Ek chhoti si architikture decision jo aaj hi le lena chahiye

`domains` table mein **`stream` column** abhi daal do:

```sql
stream varchar(16) NOT NULL DEFAULT 'transactional'   -- transactional | marketing
```

Aur `UNIQUE (domain)` ki jagah `UNIQUE (organization_id, domain, stream)`.

Kyun: customer apna `mail.theirdomain.com` transactional ke liye aur
`news.theirdomain.com` marketing ke liye verify karega — do separate identities, do
separate reputation. Agar ye column aaj nahi daala, kal migration + data backfill
karna padega.

Same reason se `email_messages` mein bhi `stream` (ya `kind`) column daal do:
`'transactional'` default, marketing rows alag table mein hain to zaroori nahi — par
reporting query simple ho jayegi.
