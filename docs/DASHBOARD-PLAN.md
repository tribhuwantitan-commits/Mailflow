# Dashboard Plan — Resend / Brevo jaisa data apne users ko dena

Status: **plan only — no code yet.** Phase 6 shipped sending. Ye document batata hai
kaun sa metric kahan se aayega, kya honestly possible hai, kya nahi, aur kis order
mein banana chahiye.

---

## 0. TL;DR (ek nazar mein)

| Chahiye | Mil sakta hai? | Source |
|---|---|---|
| Sent / accepted | ✅ | hamara DB (already hai) |
| Delivered | ✅ | SES `Delivery` event |
| Bounced (hard/soft) | ✅ | SES `Bounce` event |
| Complained (spam report) | ✅ (partial) | SES `Complaint` event |
| Rejected / rendering failed | ✅ | SES `Reject`, `RenderingFailure` |
| Delayed | ✅ | SES `DeliveryDelay` |
| Opened | ⚠️ mil jayega, par number jhooth bolta hai | SES `Open` (pixel) |
| Clicked | ✅ (sabse bharosemand engagement metric) | SES `Click` (link rewrite) |
| **Spam folder mein gaya? (per message)** | ❌ **kabhi nahi** | koi provider nahi deta |
| **Inbox placement approx** | 🟡 sirf paid seed-test se, sample ke roop mein | GlockApps / MailReach type API |
| Domain reputation | 🟡 per-domain, hamare domain par | Gmail Postmaster Tools, SNDS |
| Suppression list | ✅ | hamara DB + SES suppression |

Do cheezein jo aapko product promise se pehle samajhni hain:
1. **"Ye email spam folder mein gaya" per-recipient kabhi pata nahi chal sakta.** Resend
   bhi nahi batata. Jo "inbox vs spam" dikhta hai wo **seed test** hota hai — ek sample.
2. **Open rate 2026 mein fake hai** — Apple Mail Privacy Protection ~50% opens
   pre-fetch karta hai. Isliye Resend/Brevo bhi "clicked" ko primary rakhte hain.

---

## 1. Resend / Brevo actually kya dikhate hain

Dono ka dashboard structure lagbhag same hai:

**Resend (Email detail page):** `Sent → Delivered → Opened → Clicked`, plus `Bounced`,
`Complained`, per-recipient list, aur "Events" timeline with timestamps.

**Brevo (Statistics):** sent / delivered / opens / clicks / unsubscribes / hard bounces /
soft bounces / spam reports, plus per-campaign table aur "sender reputation".

Koi bhi ye nahi dikhata: "ye message inbox mein gaya ya spam mein". Wo metric
**inbox placement testing** ke naam se alag product hai (GlockApps, MailReach, ZeroBounce
Inbox Placement) — paise lagte hain, aur wo **aapke asli recipients ke data par nahi**,
balki unke seed mailboxes par based hota hai.

---

## 2. Metric → source matrix (yehi core hai)

| Metric | Kahan se | Grain | Caveat |
|---|---|---|---|
| `accepted` | `email_messages` (POST /emails) | per message | sirf "SES ne le liya" |
| `sent` | SES `Send` event | per message | = accepted, technically duplicate |
| `delivered` | SES `Delivery` | per recipient actually (event has `destination[]`) | recipient mailbox ne accept kiya, inbox guarantee nahi |
| `bounced` (hard) | SES `Bounce` + `bounceType=Permanent` | per recipient | `bouncedRecipients[]` |
| `bounced` (soft) | `bounceType=Transient` | per recipient | SES khud retry karta hai; final failure par event |
| `complained` | SES `Complaint` | per recipient | **sirf wahi ISP jo FBL dete hain**; Gmail reporting limited → isko "floor" samjho |
| `rejected` | SES `Reject` | per message | virus/scan reject |
| `rendering_failed` | SES `RenderingFailure` | per message | template issue |
| `delayed` | SES `DeliveryDelay` | per recipient | temporary; baad mein delivered ya bounce |
| `opened` | SES `Open` (1x1 pixel) | per recipient | MPP/proxy inflation; ek message multiple opens |
| `clicked` | SES `Click` (link rewrite) | per recipient + link | sabse honest engagement signal |
| `unsubscribed` | SES `Subscription` | per recipient | `List-Unsubscribe` header chahiye |
| spam **rate** (account) | `complaints / delivered * 100` | aggregate | derived, hamara calculation |
| inbox placement (approx) | ❌ SES se nahi | — | seed test vendor |
| domain auth pass rate | DMARC RUA reports (baad mein) | per domain | Phase 10+ |
| reputation | Gmail Postmaster / SNDS | per **hamara** domain | customer ka nahi |

> **Important**: SES ka `Delivery` event per-recipient granularity deta hai
> (`mail.destination`), par `MessageId` ek hi hota hai. Isliye status **message par nahi,
> recipient par** rakhna padega. (Neeche data model.)

---

## 3. Teen hard truths (inhe product copy mein maan lena)

### 3.1 Open tracking ka number jhooth bolta hai
Apple MPP delivery ke waqt hi pixel fetch kar leta hai. 2026 ke benchmarks: tracked
opens ka **~49% Apple servers** hain. B2B lists par 40-45% inflation normal hai.
Kya karein:
- Open dikhao, par label ke saath: *"Opens are approximate — Apple Mail Privacy
  Protection prefetches images."*
- **Click / Click-to-open** ko primary engagement metric banao.
- "Last opened at" ko user-facing promise mat banao.

### 3.2 "Inbox vs spam" per message possible nahi
Koi SMTP response ye nahi deta. Jo bhi tool "inbox placement %" dikhata hai wo
**seed-list sampling** karta hai (GlockApps type). Hum bhi wo kar sakte hain, par:
- paid third-party API (₹4,000-15,000/month type),
- sample hai, aapke asli 1 lakh recipients ka sach nahi,
- test email alag se jaata hai, campaign ka hissa nahi.

**Recommendation**: v1 mein "Inbox placement" widget **mat** banao. Uski jagah dikhao:
`Delivered %`, `Bounce %`, `Complaint %`, aur `Authentication (SPF/DKIM/DMARC)` —
ye chaar asli signals hain. Phase 11 mein chahein to seed-test add-on bana sakte hain
(separate pricing, clearly "approximate").

### 3.3 Abhi sab customers **ek hi domain** se bhejte hain
`SES_FROM_EMAIL=noreply@testingmail2btd.net` — matlab:
- sab tenants ki reputation ek hi pool mein,
- ek customer spam bhejega → **sabka** deliverability gir jayega,
- Gmail Postmaster / SNDS data **hamare** domain ka hoga, customer ke brand ka nahi.

Resend/Brevo isi problem ko **per-customer domain verification** se solve karte hain
(customer apna `mail.theirdomain.com` verify karta hai, 3 CNAME). Ye dashboard ka
naturally agla kaam hai — Phase 9. Iske bina "aapke domain ki reputation" bolna jhooth
hoga; tab tak "shared sending domain" likhna padega.

---

## 4. Architecture (jo banega)

```
                    ┌─────────────── user dashboard ───────────────┐
                    │  stats  │  messages  │  detail timeline     │
                    └────────────────────▲─────────────────────────┘
                                         │  GET /v1/stats, /v1/emails...
                                   ┌─────┴─────┐
                                   │  FastAPI  │
                                   └─────▲─────┘
                                         │ SQL (rollup + raw)
                                   ┌─────┴──────────┐
                                   │   Postgres     │
                                   │ delivery_events│  ← append-only
                                   │ email_recipients│ ← per-recipient state
                                   │ daily_rollups  │  ← charts ke liye
                                   └─────▲──────────┘
                                         │ INSERT (idempotent)
                                   ┌─────┴──────────┐
                                   │ events poller  │  long-poll 20s
                                   └─────▲──────────┘
                                         │ ReceiveMessage / DeleteMessage
                                   ┌─────┴──────┐
                                   │    SQS     │ ← DLQ (5 receives)
                                   └─────▲──────┘
                                         │ subscription
                                   ┌─────┴──────┐
                                   │    SNS     │ ← fan-out (future: ops alerts)
                                   └─────▲──────┘
                                         │ event destination
                                   ┌─────┴──────┐
                                   │  SES conf  │ ← mailflow-transactional
                                   │    set     │   + open/click tracking domain
                                   └────────────┘
```

Phase 6 sender (`outbox.py`) aur event poller **alag process** rahenge — queue slow ho
to sending na ruke.

---

## 5. Data model (migrations 0005 + 0006)

### 0005 — delivery tracking

```sql
-- per-recipient state (kyunki ek MessageId, kai recipients)
CREATE TABLE email_recipients (
    id                  uuid PRIMARY KEY,
    organization_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email_id            uuid NOT NULL REFERENCES email_messages(id) ON DELETE CASCADE,
    address             varchar(320) NOT NULL,
    status              varchar(24) NOT NULL DEFAULT 'queued',
    -- queued|sent|delivered|bounced|complained|delayed|rejected|suppressed
    bounce_type         varchar(16),          -- Permanent | Transient
    bounce_subtype      varchar(40),
    diagnostic          text,                 -- SMTP diagnostic code
    delivered_at        timestamptz,
    bounced_at          timestamptz,
    complained_at       timestamptz,
    first_opened_at     timestamptz,
    last_opened_at      timestamptz,
    open_count          int NOT NULL DEFAULT 0,
    click_count         int NOT NULL DEFAULT 0,
    first_clicked_at    timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email_id, address)
);

-- append-only audit trail (raw events, debugging + replay)
CREATE TABLE delivery_events (
    id                  uuid PRIMARY KEY,
    organization_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email_id            uuid REFERENCES email_messages(id) ON DELETE CASCADE,
    recipient_address   varchar(320),
    provider_message_id varchar(255),
    event_type          varchar(32) NOT NULL,
    provider_event_at   timestamptz,
    received_at         timestamptz NOT NULL DEFAULT now(),
    payload             jsonb NOT NULL,
    provider_event_id   varchar(128) NOT NULL,   -- SNS MessageId → idempotency
    UNIQUE (provider_event_id)
);

CREATE INDEX ix_events_org_time ON delivery_events (organization_id, provider_event_at);
CREATE INDEX ix_events_message  ON delivery_events (provider_message_id);

-- suppression (bounce/complaint ke baad khud banao, SES ki copy alag)
CREATE TABLE suppressions (
    id              uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    address         varchar(320) NOT NULL,
    reason          varchar(32) NOT NULL,   -- hard_bounce|complaint|manual|unsubscribe
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, address)
);

ALTER TABLE email_messages
    ADD COLUMN delivered_count int NOT NULL DEFAULT 0,
    ADD COLUMN bounced_count   int NOT NULL DEFAULT 0,
    ADD COLUMN opened_count    int NOT NULL DEFAULT 0,
    ADD COLUMN clicked_count   int NOT NULL DEFAULT 0;
```

### 0006 — rollups (charts fast rakhne ke liye)

```sql
CREATE TABLE daily_stats (
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    day             date NOT NULL,
    sent            int NOT NULL DEFAULT 0,
    delivered       int NOT NULL DEFAULT 0,
    bounced         int NOT NULL DEFAULT 0,
    complained      int NOT NULL DEFAULT 0,
    opened          int NOT NULL DEFAULT 0,
    clicked         int NOT NULL DEFAULT 0,
    PRIMARY KEY (organization_id, day)
);
```

Rollup ek nightly job (ya `delivery_events` par `ON CONFLICT DO UPDATE`) se. 100k emails
se neeche rollup ki zaroorat nahi — direct `GROUP BY` chal jayega. Isliye 0006 **optional**
hai, jab volume aaye tab.

---

## 6. API surface

```
POST /v1/emails                       (already) → 202, message_id
GET  /v1/emails/{id}                  → + counts, status rollup
GET  /v1/emails/{id}/recipients       → per-recipient table (paginated)
GET  /v1/emails/{id}/events           → timeline, raw
GET  /v1/emails?status=bounced        → filter by aggregate status
GET  /v1/stats?from=&to=&group=day    → chart series
GET  /v1/stats/summary?from=&to=      → dashboard cards (sent/delivered/bounce/open/click/complaint)
GET  /v1/suppressions                 → list
POST /v1/suppressions                 → manual add
DELETE /v1/suppressions/{address}     → remove
```

`/v1/stats/summary` ka core query (per tenant, ek hi round trip):

```sql
SELECT
  COUNT(*)                                   AS sent,
  COUNT(*) FILTER (WHERE status='delivered') AS delivered,
  COUNT(*) FILTER (WHERE status='bounced')   AS bounced,
  COUNT(*) FILTER (WHERE status='complained')AS complained,
  COUNT(*) FILTER (WHERE open_count > 0)     AS opened,
  COUNT(*) FILTER (WHERE click_count > 0)    AS clicked
FROM email_recipients
WHERE organization_id = :org AND created_at >= :from AND created_at < :to;
```

Percentages backend mein hi calculate karo (`delivered / sent`, etc.) taaki frontend
mein rounding ka jhagda na ho.

---

## 7. UI spec — 4 screens

### 7.1 Overview (dashboard home)
```
┌ Sent ──────── Delivered ──── Bounce % ──── Complaint % ──┬ Opens* ─ Clicked ┐
│  12,480       12,301 (98.6%)   1.2%        0.04%        │  41.2%   8.4%    │
└──────────────────────────────────────────────────────────┴──────────────────┘
   graph: stacked area, daily (sent/delivered/bounced)
   * Opens are approximate (Apple Mail prefetches images)
   table: recent 10 emails with status chip
```

### 7.2 Email detail
```
Subject · to 3 recipients · accepted 09:15:02
[Accepted] → [Delivered 09:15:04] → [Opened 09:41] → [Clicked 09:41]
recipients table: address | status | bounce reason | opens | clicks | last event
events timeline (collapsible, raw JSON optional)
```

### 7.3 Deliverability
```
Authentication: SPF ✓ DKIM ✓ DMARC ✓   (hamare domain ke liye)
Sending domain: shared (testingmail2btd.net)   ← Phase 9 ke baad per-customer
Bounce trend / complaint trend (bar, 30 days)
"Complaint rate 0.04% — safe (threshold 0.10%)"  ← Google/Postmaster guideline
```
Yahan **inbox placement % co mat likho** jab tak seed test nahi jodte.

### 7.4 Suppressions
List + "why" + manual add. Naye mail bhejte waqt yahi list check hogi.

---

## 8. Event state machine (poller ka dil)

```
queued → sent → delivered
               ↘ delayed → delivered | bounced
               ↘ bounced        (terminal, hard)
               ↘ complained     (terminal)
queued → rejected | suppressed | rendering_failed  (terminal)
open/click events state nahi badalte — sirf counters badhate hain
```

Rules:
- unknown address → event drop, `delivery_events` mein `email_id NULL` ke saath rakho
  (debugging ke liye), warna DLQ bharta rahega.
- terminal state se peeche kabhi nahi.
- `provider_event_id` (SNS MessageId) par unique = duplicate delivery safe.
- **delete after commit** — crash hua to SNS dobara dega, unique index kha jayega.

---

## 9. Open/Click setup (jo aaj missing hai)

SES ko open/click ke liye do cheezein chahiye:
1. `{{ses:openTracker}}` placeholder ya default pixel insertion — hum `SendEmail` use karte
   hain to SES khud pixel daal deta hai jab `OPEN` event destination enabled ho.
2. **Click tracking ke liye custom redirect domain** — warna links `*.awstrack.me` ho
   jate hain (customer ke liye bhadda + spam filters ko shak).
   - Ek subdomain: `t.testingmail2btd.net` (ya `links.mailflow.app`)
   - Us par **ACM certificate, ap-south-1 mein** (region must match SES region)
   - SES console jo CNAME dega wo DNS mein daalo
   - Configuration set par `CustomRedirectDomain` set karo
3. Event types on: `SEND, DELIVERY, BOUNCE, COMPLAINT, REJECT, DELIVERY_DELAY, OPEN, CLICK`

⚠️ Click tracking links rewrite karta hai — kuch legal/financial emails mein ye
undesirable hota hai. Isliye per-message opt-out flag rakhna behtar hai
(`track_opens`, `track_clicks` in request body). Phase 7 mein hi daal lo, warna baad
mein API migration karni padegi.

---

## 10. Cost (ap-south-1, 10k emails/month)

| Item | Rate | Cost |
|---|---|---|
| SES sending | $0.10/1K | $1.00 |
| SES → SNS publish | free | $0 |
| SNS → SQS delivery | free tier 1M | $0 |
| SQS requests (~4/event × 5 events) | free tier 1M | $0 |
| Postgres rows (30k events/month) | already paying | ~$0 |
| ACM certificate | free | $0 |
| **Extra** | | **≈ $0** |

Agar GlockApps-type inbox placement add-on liya (Phase 11): ~$50-100/month, aur wo
customer ke paise se (add-on pricing) recover karna padega.

---

## 10.5 Do streams: transactional pehle, marketing alag pipeline par

Product decision: **transactional pehle ship hoga; marketing rahega magar alag product
line** ke roop mein — alag sending stream, alag AWS account, alag pricing. Poori list,
separation ka architecture aur marketing ka anti-spam stack
[docs/TRANSACTIONAL-VS-MARKETING.md](TRANSACTIONAL-VS-MARKETING.md) mein hai.

Neeche sirf **transactional** dashboard ka scope hai; marketing ka dashboard alag
banega (Phase 13), jisme open/click/campaign analytics honge.

### Transactional stream mein ye sab **mat** banao (marketing stream mein alag se aayenge)

| Feature | Kyun nahi chahiye |
|---|---|
| Campaigns / bulk send API | aap bhejte hi nahi |
| Subscriber lists / segments / tags | koi audience manage nahi |
| Double opt-in flow | single-recipient, one-to-one mail |
| Template editor + visual builder | API se bhejte ho, template aapke customer ka kaam |
| A/B testing, subject optimization | transactional mail A/B test nahi hota |
| RSS-to-email, scheduling, send-time optimization | event-driven mail |
| Broadcast scheduling, drip sequences | — |
| Unsubscribe/preference center | transactional mail par unsubscribe fit nahi hota* |
| Open/click analytics ka bada dashboard | clicks OTP mein almost zero — chart khaali dikhega |
| Inbox-placement seed testing | bulk-only problem |
| Lists/segments per tenant | — |

\* `List-Unsubscribe` header **optional** hai jab mail pure transactional ho
(Gmail/Yahoo bulk-sender rules 5,000+/day bulk senders par lagte hain, aur unme bhi
transactional mail ko chhoot hai). Aapke volume se pehle hafte mein 5,000/day nahi
hoga, to ye baad ka kaam hai. **Magar** header add karna sasta hai — 7c mein ek
optional flag ke saath daal denge.

### Bacha — yehi asli dashboard hai (transactional)

| Widget | Kaam | Priority |
|---|---|---|
| **Delivered / Failed** (big number) | "kya pahuncha" — sabse ahem | P0 |
| **Per-message timeline** | Accepted → Delivered → Bounced, timestamps ke saath | P0 |
| **Failure reasons table** | bounce code + SMTP diagnostic ("mailbox full", "no such user") | P0 |
| **Latency: accepted → delivered** | OTP ke liye critical — "kitne second mein pahuncha" | P1 |
| Attempts / retries per message | worker ka behaviour dikhta hai | P1 |
| Suppression list (view/add/remove) | bounce ke baad dobara send na ho | P1 |
| Bounce % + Complaint % (30 din) | reputation health, threshold 5% / 0.1% | P1 |
| Opened (count only, no chart) | optional, disclaimer ke saath | P2 |
| Clicked | sirf tab jab customer ne click tracking on kiya ho | P2 |
| SPF/DKIM/DMARC status per verified domain | onboarding ka hissa | P1 |

### Ek naya metric jo transactional mein sabse zyada matter karta hai

**Delivery latency.** Password reset mein 2 second aur 40 second ka farq user
experience hai. Har message ke liye:

```
latency = delivered_at (SES Delivery event) - accepted_at (our POST /v1/emails)
```

`email_messages` mein `accepted_at` (already `created_at`) + `delivered_at` se derive
ho jayega. Dashboard card: **p50 / p95 latency, last 24h**. Ye Resend/Brevo bhi
dikhate hain, aur yahi aapka OTP-focused differentiator ban sakta hai.

### Approval ke liye bhi aasan

SES production access form mein "Mail type: **Transactional**" chunna ek bada
advantage hai — marketing ke sawal (opt-in proof, unsubscribe, list source) poochhe
hi nahi jate. `docs/LAUNCH-CHECKLIST.md` ka draft already transactional-only likha
hua hai.

## 11. Phasing

| Phase | Kaam | Naya infra | Ship hone par kya dikhega |
|---|---|---|---|
| **7a** | SES config set + SNS + SQS + DLQ + IAM; open/click tracking domain + ACM | AWS console/CLI | simulator se events aa rahe hain |
| **7b** | migration 0005, poller + state machine, tests | — | DB bharta hai |
| **7c** | `/v1/stats*`, `/v1/emails/{id}/recipients`, `/events`, filters | — | API se data |
| **7d** | Suppression list + send-time check | — | hard bounce ke baad dobara send nahi |
| **7e** | Frontend: 4 screens | pehla UI | user ko dashboard |
| **8** | Production access request (sandbox se bahar) | — | real recipients |
| **9** | **Per-customer domain verification** (domains table, DKIM CNAME flow, verify poller) | — | apni domain, apni reputation |
| **10** | DMARC RUA ingest (`rua=` mailbox → S3 → parse) | S3 | auth pass rate per domain |
| **11** | Inbox placement seed test (paid, optional add-on) | vendor API | "approx inbox %" with disclaimer |

Har phase independently shippable. 7a sirf console kaam hai — code zero.

---

## 12. Jo hum **promise nahi** karenge

- "Aapki email inbox mein gayi" — sirf "delivered to mail server" bolenge.
- "Inbox placement 97%" — sirf seed test ke saath, aur "approximate" label ke saath.
- "Open rate accurate hai" — disclaimer hamesha.
- "Aapke domain ki reputation" — jab tak Phase 9 na ho, "shared domain" bolenge.
- Complaint count ko absolute sach nahi — kuch ISPs FBL nahi dete, to ye **floor** hai.

---

## 13. Ek chhota code bug jo is phase mein theek karna hai

`app/services/outbox.py` line ~159: `message.provider = "fake"` hardcoded hai.
SES live hote hi har successful message "fake" label le lega. `SubmissionResult` mein
`provider_name: str` add karo aur `SESEmailProvider` se `"ses"` bhejo. Isi commit mein
`email_messages.status = "sent"` ka comment bhi correct karo ("accepted by provider,
not delivered").
