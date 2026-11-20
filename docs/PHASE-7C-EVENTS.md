# Phase 7c — delivery events, suppression, auto-pause, retention

Status: **implemented.** Tests: **143 passed, 1 skipped** (PostgreSQL still unvalidated).

Ye doc Phase 7 ke bache hue saare kaam ko cover karta hai: **7c + cleanup job + `Source` fix**.

---

## 1. Ek line mein

`send_email` sirf **"SES ne le liya"** batata hai. Delivery, bounce, complaint — wo
**baad mein, alag raste se** aata hai. Phase 7c wahi rasta banata hai:

```
SES ──event──→ SNS topic ──→ SQS queue ──→ event_poller ──→ Postgres ──→ API ──→ dashboard
```

Aur us data se **teen kaam** hote hain:
1. Message ka sach (`delivered` / `bounced` / `complained`)
2. **Suppression** — bounce/complaint wale address ko dobara mat bhejo
3. **Auto-pause** — ek tenant ka bounce rate 5% cross kare to usko rok do, poore account ko nahi

---

## 2. Kya bana

| Cheez | File | Kaam |
|---|---|---|
| `delivery_events` table | `app/models/delivery_events.py` | append-only audit trail, tenant-scoped |
| `suppressions` table | same | bounce/complaint wale addresses |
| `tenant_reputation` table | same | per-tenant daily counters (pause decision) |
| `EmailMessage` delivery columns | `app/models/delivery.py` | `delivered_at`, `bounced_at`, `complained_at`, `bounce_type`, `bounce_reason` |
| `Organization` pauses + verification | `app/models/organization.py` | `sending_paused_at`, `email_verified_at`, `card_verified_at` |
| Event ingest | `app/services/delivery_events.py` | SQS body → DB |
| SQS poller | `app/services/event_poller.py` | long-poll loop |
| Retention job | `app/services/maintenance.py` | body cleanup + counter purges |
| `GET /v1/emails/{id}/events` | `app/api/emails.py` | timeline |
| Migration `0007_events` | `alembic/versions/0007_delivery_events.py` | 3 tables + 9 columns |

---

## 3. Ingest — order matter karta hai

Har event par, isi order mein:

```
1. SES MessageId se tenant dhoondo
2. delivery_events row likho          ← provider_event_id (SNS MessageId) se dedupe
3. Suppression likho (hard bounce / complaint)
4. Reputation counter badhao
5. Pause decision dekho
```

**Kyun ye order:** suppression counter se **pehle** likhti hai. Beech mein crash ho to
tenant **protected** reh jata hai, sirf counted nahi.

### SNS redelivery harmless hai

```sql
UNIQUE (provider_event_id)      -- SNS MessageId
```

SNS **at-least-once** deliver karta hai — wahi event do baar aa sakta hai. Unique
constraint ki wajah se doosri baar `duplicate` return hota hai, kuch write nahi hota.

### Jo event attribute nahi ho paya

`unknown_message` return hota hai, **store nahi hota** — magar log hota hai. Ye bug ka
sign hai (MessageId match nahi hua), aur usko chhupana agla bug dhoondhna mushkil kar dega.

---

## 4. Suppression — sirf hard bounce aur complaint

| Event | Address suppress? |
|---|---|
| `Bounce` + `bounceType=Permanent` | ✅ haan |
| `Bounce` + `bounceType=Transient` | ❌ nahi (soft — server busy tha) |
| `Complaint` | ✅ haan (spam mark) |
| `Reject`, `DeliveryDelay` | ❌ |

**Transient kyun nahi:** soft bounce ka matlab "abhi nahi hua", "kabhi nahi hoga" nahi.
Usse suppress karna legit customer ko permanently block kar dega.

### Suppression **tenant-scoped** hai

```sql
UNIQUE (organization_id, recipient)
```

Customer A ne `user@x.com` suppress kiya — **customer B usko bhej sakta hai**. Ye
intentional hai: dono ka rishta alag hai.

### Send se pehle check

Worker mein, provider call se **pehle**:

```python
blocked = suppressed_recipients(db, message.organization_id, list(recipients))
if blocked:
    message.status = "failed"
    message.error_code = "recipient_suppressed"
    # provider ko call hi nahi kiya
```

Test `test_suppressed_recipient_never_reaches_the_provider` verify karta hai:
`provider.submitted_messages == []`.

---

## 5. Auto-pause — poore account ko bachane ke liye

**Ye Phase 7c ka sabse important hissa hai.**

AWS **poore account** ko pause kar deta hai jab bounce 10% ya complaint 0.5% cross ho.
Matlab: **ek galat customer sabko maar deta hai.** Isliye hum usse **pehle** act karte hain.

| Threshold | Value | AWS ka |
|---|---|---|
| Bounce | **5%** | 10% |
| Complaint | **0.1%** | 0.5% |
| Minimum sample | **100 sends** | — |

### Minimum sample kyun

```
3 sends, 1 bounce  =  33%  → pause?  ❌ absurd
100 sends, 6 bounce =  6%  → pause?  ✅
```

Test `test_small_volume_does_not_pause` yahi pin karta hai.

### Pause hone par

```
POST /v1/emails → 403
{"code": "sending_paused",
 "message": "Sending is paused for this organization:
             bounce rate 6/106 above 5%. Contact support to resume."}
```

Worker bhi refuse karta hai (`error_code: organization_paused`) — queued messages
provider tak nahi jaate.

---

## 6. `Source` fix — ab customer ka domain

Phase 7a ne **gate** lagaya tha, magar provider abhi bhi `ses_from_email` use kar raha tha.
Ab:

```python
source = message.sender or self.settings.ses_from_email
```

- Customer ka mail → `noreply@acme.com` (verified, 7a ne check kiya)
- Platform ka mail (test script) → `SES_FROM_EMAIL`

Isliye ab DKIM bhi sahi lagta hai — signing customer ke domain ki hoti hai.

---

## 7. List-Unsubscribe — Gmail/Yahoo ke liye

`UNSUBSCRIBE_MAILTO` set ho to har mail par:

```
List-Unsubscribe: <mailto:unsub@acme.com?subject=unsubscribe>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

**Kyun:** Gmail aur Yahoo bulk senders ke liye ye expect karte hain. Bina iske
complaint rate badhta hai — aur complaint 0.1% par pause lag jata hai.

**Set nahi ho to header nahi lagta.** Kyun: dead mailbox advertise karna us se bura hai
ki kuch na ho — jo user wahan reply karega, wo **complaint** ban jayega.

### Implementation detail

Headers sirf **raw MIME** par lag sakte hain, `send_email` API par nahi. Isliye:

```python
if message.headers:
    return self._send_raw(message, source)   # send_raw_email
return self._send_email(...)                  # normal path
```

Jab headers nahi hain, simple path hi chalta hai — koi extra cost nahi.

---

## 8. Retention — DB ko phoolne se bachana

Ye **VPS-SIZING.md** mein flag kiya gaya tha: 20,000 tenants = **100 GB/month** body.

### Body retention (default 30 din)

```python
UPDATE email_messages
   SET text_body = NULL, html_body = NULL
 WHERE created_at < now() - interval '30 days';
```

**Row rehti hai**, sirf body jaati hai. Metadata, status, `provider_message_id`,
delivery timeline — sab bacha rehta hai.

**Kyun 30 din:** end customer ko 30 din purana email body chahiye bhi nahi hota — status
(`delivered`/`bounced`) chahiye. Aur support ko timeline chahiye, content nahi.

### Counter windows

| Table | Retention | Kyun |
|---|---|---|
| `recipient_daily_counts` | **7 din** | guard sirf aaj dekhta hai |
| `usage_daily` | **90 din** | monthly reporting + invoice dispute |
| `tenant_reputation` | **90 din** | trend questions |
| `delivery_events` | **90 din** | support ka "mail nahi mili" investigation |

### Batched delete

Har delete **`batch` rows** mein hota hai (default 1000). Ek first-run par lakhon rows
ek hi statement mein delete karna table lock kar dega.

```powershell
cd backend
.venv\Scripts\python.exe -m app.services.maintenance --dry-run   # windows dekho
.venv\Scripts\python.exe -m app.services.maintenance              # actually chalao
```

**Roz chalao** — Task Scheduler se, subah 4 baje.

---

## 9. Chalane ka order — SQS pipeline

### 9.1 AWS console (ek baar, 15 min)

| # | Kahan | Kya |
|---|---|---|
| 1 | **SQS** → Create queue | Standard, name `mailflow-ses-events`, region **ap-south-1** |
| 2 | SQS queue → **Dead-letter queue** | naya queue `mailflow-ses-events-dlq`, `maxReceiveCount=5` |
| 3 | **SNS** → Create topic | Standard, `mailflow-ses-events` |
| 4 | SNS topic → **Subscriptions** | Protocol **SQS**, endpoint = queue ARN |
| 5 | SQS → **Access policy** | SNS ko `sqs:SendMessage` allow karo |

⚠️ **Step 5 bhoolna sabse common galti hai** — subscription "confirmed" dikhega, magar
messages aayenge hi nahi.

### 9.2 SES configuration set

| # | Kahan | Kya |
|---|---|---|
| 1 | SES → **Configuration sets** → Create | name: `mailflow-events` |
| 2 | **Event destinations** → Add | **SNS**, topic `mailflow-ses-events` |
| 3 | Events choose karo | **SEND, DELIVERY, BOUNCE, COMPLAINT, REJECT, DELIVERY_DELAY** |
| 4 | **Reputation metrics** | ✅ on |
| 5 | Open/click tracking | ❌ **abhi nahi** (Phase 9, aur apni tracking better hai) |

Phir `.env` mein:
```
SES_CONFIGURATION_SET=mailflow-events
SQS_EVENT_QUEUE_URL=https://sqs.ap-south-1.amazonaws.com/123456789012/mailflow-ses-events
```

### 9.3 Local test — simulator se

```powershell
# terminal 1: poller
.venv\Scripts\python.exe -m app.services.event_poller --loop

# terminal 2: bounce generate karo (asli inbox ko chhue bina)
.venv\Scripts\python.exe -m app.scripts.send_test --to bounce@simulator.amazonses.com
```

30-60 second mein poller log karega:
```
event_poll received=3 stored=3 duplicates=0 unattributed=0 failed=0 paused=0
```

Aur `GET /v1/emails/{id}/events` par timeline dikhega.

### 9.4 Production mein

```powershell
# do poller processes, NSSM/Task Scheduler se supervised
.venv\Scripts\python.exe -m app.services.event_poller --loop
```

**Kyun loop:** SQS long-poll already 20s wait karta hai. `--loop` ke bina ek batch aur exit.

---

## 10. Naya endpoint

```http
GET /v1/emails/{id}/events
X-API-Key: mfk_...
```

```json
{
  "id": "...",
  "status": "bounced",
  "events": [
    {"type": "Send",      "recipient": "user@example.com", "occurred_at": "...", "received_at": "..."},
    {"type": "Bounce",    "recipient": "user@example.com", "occurred_at": "...", "received_at": "..."}
  ]
}
```

Tenant-scoped: doosre tenant ka email id → `404`.

---

## 11. Production access ke liye ab kya ready hai

`docs/LAUNCH-CHECKLIST.md` ke prerequisites:

| # | Requirement | Status |
|---|---|---|
| 1 | Domain verified, Easy DKIM | ✅ console (aapke paas) |
| 2 | SPF + DMARC | ⬜ **DNS** — 10 min, aapko karna |
| 3 | Configuration set + `ReputationMetricsEnabled` | ✅ code + 9.2 |
| 4 | SNS + event destination (BOUNCE, COMPLAINT) | ✅ code + 9.1 |
| 5 | Events consume karne wala code | ✅ **7c** |
| 6 | Suppression list + send se pehle check | ✅ **7c** |
| 7 | `List-Unsubscribe` headers | ✅ **7c** |
| 8 | Per-tenant daily quota | ✅ **7b** |
| 9 | Per-customer domain verification | ✅ **7a** |
| 10 | Website + ToS + AUP + Privacy | ⬜ launch se pehle |
| 11 | Bounce < 5%, complaint < 0.1% measurable | ✅ **7c** (dashboard Phase 9) |

**Matlab: technical prerequisites 8/9 done.** Sirf SPF/DMARC aur website baaki.

---

## 12. Kya nahi bana (jaan-boojh kar)

| Cheez | Kyun nahi | Kab |
|---|---|---|
| **Open/click tracking** | Extra config set + apna tracking domain chahiye | Phase 9 |
| **Dashboard UI** | API ready hai (`/events`), UI nahi | Phase 9 |
| **`GET /v1/stats`** | `usage_daily` + `delivery_events` se query, magar rollup pehle | Phase 9 |
| **Suppression list API** | support ke liye chahiye, customer ke liye nahi | Phase 9 |
| **DLQ redrive tooling** | AWS console se ho jata hai | jab zaroorat pade |
| **SES full-rate parallel worker** | abhi serial, 3/s. VPS-SIZING mein plan hai | scale par |
| **Neon par migrate** | connection string nahi mila abhi | aapke paas |

---

## 13. Aapka checklist

| # | Kaam | Kaun | Time |
|---|---|---|---|
| 1 | `alembic upgrade head` (`0007_events`) | aap | 1 min |
| 2 | SQS queue + DLQ + SNS topic + policy | aap | 15 min |
| 3 | SES config set + event destination | aap | 5 min |
| 4 | `.env` mein 3 lines | aap | 2 min |
| 5 | SPF + DMARC DNS records | aap | 10 min |
| 6 | Simulator bounce test | aap | 5 min |
| 7 | Retention job Task Scheduler mein | aap | 10 min |
| 8 | Dashboard (Phase 9) | main | next |
