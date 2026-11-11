# Delivery Events: how "sent / delivered / bounced" reaches our users

Status: **design note only — not implemented.** Phase 6 shipped sending only.
This document explains what is missing, why, and how to build it in Phase 7.

---

## 1. The problem in one line

SES `send_email` returns only an **acceptance receipt** (`MessageId`). It does **not**
tell us whether the recipient's mail server accepted, bounced, or marked it as spam.
That second half of the story arrives later, asynchronously, and only if we explicitly
subscribe to it.

So today `email_messages.status` can only ever reach `sent`, which honestly means
"we handed it to SES and SES said OK". It is not delivery.

---

## 2. Why the SES dashboard is not the answer

The AWS SES console dashboard shows *our account's* aggregates: total sends, bounce
rate, complaint rate, per-ISP breakdown. That is an **operator** view. It cannot be
shown to a customer because:

- it is not tenant-scoped — customer A would see customer B's numbers;
- it needs AWS console/IAM credentials we must never give out;
- it is aggregate, not per-message — we cannot answer "did message `abc` arrive?".

Our dashboard must be built from **our own database**, filled by **our own event
ingest**. The SES dashboard is for us, the platform operator.

---

## 3. Mental model: four layers, four different jobs

Don't confuse these. Most "SNS vs SQS" confusion comes from mixing them up.

```
SES  --(event)-->  SNS topic  --(subscription)-->  SQS queue  -->  our poller  -->  Postgres  -->  our API  -->  user UI
 |                     |                              |
 hook                 fan-out / router               durable buffer + retry
```

| Layer | Plain-language job | Analogy |
|---|---|---|
| **SES event publishing** | The hook. Tell SES which events we want, and where to drop them. | Courier hands over a parcel |
| **SNS** | Fan-out. One event, many subscribers (our queue, our email alert, a future Lambda). Push-based. | Announcement over a loudspeaker |
| **SQS** | Durable buffer. Holds events until *we* are ready. Our app pulls. Retries + dead-letter. | The mailbox at our door |
| **Our poller** | Reads the queue, matches events to `email_messages`, writes history. | We open the mailbox |

At our volume (200/day in sandbox, low thousands in early production) the poller is a
simple background loop or a systemd timer — no Celery, no Redis. We already have an
outbox worker with this exact shape.

---

## 4. SNS vs SQS vs EventBridge — actually pick one

| | SNS | SQS | EventBridge |
|---|---|---|---|
| Model | Push to subscribers | Pull by consumer | Push to rules → targets |
| Best at | fan-out to several consumers | buffering, retry, decoupling | filtering/routing on event content |
| If our server is down | message is retried, then dropped (unless it forwards to SQS) | message waits in the queue, safe | retried, then DLQ |
| Free tier | 1M publishes/month | 1M requests/month | AWS-service events free; custom events billed |
| Paid rate | ~$0.50/M publishes | ~$0.40/M requests (send + receive + delete each count) | $1.00/M custom events |
| Built-in DLQ | No | Yes | Yes |

**SNS alone is the classic mistake**: SNS is fire-and-forget. If our endpoint
returns 500 at 3am, or the app is redeploying, those events are retried a few times
and then **permanently lost**. We would silently have gaps in delivery history.

**Recommendation: SES → SNS → SQS (encrypted) → poller.** SNS gives us room to add
subscribers later (e.g. an ops alert email on complaints) without touching SES; SQS
gives us durability and a dead-letter queue for free. EventBridge is the right choice
only if we later need content-based routing ("complaints only, hard bounces only") at
a scale where SNS filters feel limiting.

### Rejected alternatives

- **SNS → HTTPS endpoint directly.** Tempting (no queue, no poller) but: no buffering,
  no DLQ, needs public ingress + TLS + SNS signature verification, and it couples our
  uptime to event delivery. Not worth it at this stage.
- **EventBridge → API destination.** Same coupling, plus an extra service to learn.
- **Firehose → S3 → Athena.** Good for analytics, wrong for a per-message status field.
- **CloudWatch metrics only.** Gives aggregate counters, not per-message events. Useless
  for "where is my email".

---

## 5. The event payload (what SQS actually delivers)

When SES publishes to SNS and SNS forwards to SQS, the SQS body is an **SNS envelope**,
and the SES event sits inside as a JSON *string*:

```json
{
  "Type": "Notification",
  "MessageId": "…sns…",
  "TopicArn": "arn:aws:sns:ap-south-1:…:mailflow-events",
  "Message": "{\"eventType\":\"Delivery\",\"mail\":{…},\"delivery\":{…}}"
}
```

So the poller must: read `Body` → `json.loads` → if `Type == "Notification"` then
`json.loads(payload["Message"])` → that is the SES event. (Also handle
`Type == "SubscriptionConfirmation"` by calling `ConfirmSubscription` — only relevant
if we ever point SNS at an HTTPS endpoint. With SQS, the subscription is confirmed via
IAM/policy, not via HTTP.)

An SES event, trimmed:

```json
{
  "eventType": "Bounce",
  "mail": {
    "timestamp": "2026-11-07T09:15:00.000Z",
    "messageId": "01000193-…",
    "source": "noreply@testingmail2btd.net",
    "destination": ["user@example.com"],
    "tags": { "ses:configuration-set": ["mailflow-transactional"] }
  },
  "bounce": {
    "bounceType": "Permanent",
    "bounceSubType": "General",
    "bouncedRecipients": [{ "emailAddress": "user@example.com", "status": "5.1.1" }]
  }
}
```

The important fields:

| Field | Use |
|---|---|
| `eventType` | `Send`, `Delivery`, `Bounce`, `Complaint`, `Reject`, `DeliveryDelay`, `Open`, `Click`, `RenderingFailure` |
| `mail.messageId` | **This is the join key** — matches `email_messages.provider_message_id` |
| `mail.destination[]` | per-recipient status |
| `bounce.bounceType` | `Permanent` (hard) vs `Transient` (soft) |
| `complaint` | abuse report, must be handled fast or SES throttles us |
| `mail.tags` | custom key/values we set at send time — our escape hatch |

### Two gotchas worth designing for now

1. **One send, many recipients.** `send_email` with 5 recipients returns **one**
   `MessageId`, and bounce events reference only the bounced address. Storing status on
   the message row is therefore lossy. Cleanest fix: a separate
   `email_recipients`-style table, or JSON column `recipient_status`.
2. **Ordering is not guaranteed.** `Send` may arrive after `Delivery`, and standard SQS
   can duplicate. The poller must be **idempotent** (key on SNS `MessageId`) and must
   apply events as a monotonic state machine, not as "last write wins on arrival order":

   ```
   queued → sending → sent → delivered
                    ↘ bounced (Permanent, terminal)
                    ↘ complained (terminal)
                    ↘ delayed → (later) delivered or bounced
                    ↘ rejected / rendering_failed (terminal)
   ```

   Terminal states never regress, and a higher-ranked state never returns to a
   lower-ranked one.

---

## 6. Wiring it up (console / CLI checklist)

1. **Configuration set** — `mailflow-transactional` in `ap-south-1`.
   We already pass `SES_CONFIGURATION_SET` into `send_email`, but the name must exist or
   sends fail. Create it *before* flipping `MAIL_PROVIDER=ses` in production.
2. **Event destination** on that configuration set → SNS topic `mailflow-events`,
   matching event types: `SEND, DELIVERY, BOUNCE, COMPLAINT, REJECT, DELIVERY_DELAY`.
   Add `OPEN, CLICK` only if we accept the extra work (see §11).
3. **SNS topic** + **SQS queue** `mailflow-events-queue`, subscription protocol `sqs`,
   raw message delivery **off** (keep the SNS envelope; it carries the dedupe id).
4. **Queue policy** allowing `sns.amazonaws.com` to `sqs:SendMessage`, plus
   `RedrivePolicy` → DLQ `mailflow-events-dlq` after 5 receives.
5. **IAM policy for the app** (separate from the sender user, or same user):
   `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` on that queue ARN.
   No SNS permissions needed at runtime — SNS pushes into SQS on its own.
6. **Best-effort tags** — extend `OutboundEmail` with `tags: dict[str,str]`
   (`organization_id`, `email_id`) and pass them as `Tags` to `send_email`. Then even a
   missing DB match can be recovered from `mail.tags`.

> The AWS API for this is `sesv2 CreateConfigurationSetEventDestination` /
> `sns Subscribe` / `sqs CreateQueue`. Our provider currently uses the older `ses`
> (v1) client, which is fine for sending; event destination setup can be done in the
> console once, not in code.

---

## 7. Database changes (migration `0005`)

```
email_messages
  + delivered_at        timestamptz  null
  + bounced_at          timestamptz  null
  + complained_at       timestamptz  null
  + bounce_type         varchar(20)  null      -- Permanent | Transient
  + bounce_reason       text         null
  + recipient_status    jsonb        null      -- {"user@example.com": "delivered"}

delivery_events              -- append-only audit trail, tenant-scoped
  id                uuid pk
  organization_id   uuid  fk → organizations(id)
  email_id          uuid  fk → email_messages(id)  null
  provider_message_id varchar(255) index
  event_type        varchar(30)
  recipient         varchar(320) null
  payload           jsonb
  provider_event_at timestamptz      -- mail.timestamp
  received_at       timestamptz default now()
  unique (provider_event_id)          -- SNS MessageId → idempotency
```

`delivery_events` mirrors the existing `outbox_events` philosophy: durable rows, plain
SQL, no external broker for anything user-visible.

---

## 8. API surface for the user's dashboard

Additive, tenant-scoped via the existing API key / session dependencies:

```
GET /v1/emails/{id}                 → include delivery fields (already returns the row)
GET /v1/emails/{id}/events          → timeline: accepted, delivered, bounce, complaint
GET /v1/emails?status=bounced       → filtering by new statuses
GET /v1/stats?from=…&to=…           → counts per status per day (for charts)
```

`GET /v1/stats` should be a single `GROUP BY date_trunc('day'), status` query over
`email_messages` scoped by `organization_id`. No new infrastructure.

Frontend: a status badge on the email row + a timeline block on the detail page. No
realtime needed — the dashboard re-fetches on open, and the numbers lag SES by seconds
at most.

---

## 9. The poller (Phase 7 worker #2)

Shape mirrors `app/services/outbox.py`:

```python
# app/services/delivery_events.py  (sketch)
def poll_once(sqs, queue_url: str, factory, limit: int = 10) -> int:
    resp = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=limit,
        WaitTimeSeconds=20,              # long poll: cheap, low latency
        AttributeNames=["SentTimestamp"],
    )
    for raw in resp.get("Messages", []):
        if apply_event(factory, raw["Body"]):        # idempotent, transactional
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=raw["ReceiptHandle"])
        # else: leave it → SQS redelivers → eventually DLQ
    return len(resp.get("Messages", []))
```

Rules:
- **Delete only after commit.** A crash between commit and delete causes a duplicate
  delivery, which the unique `provider_event_id` absorbs.
- **Never `raise` past the loop** — a malformed message would block the queue head.
  Log, delete, count it.
- **Long poll (20s)**, not short poll. Empty short polls are billed too.
- Run as a separate process (`python -m app.services.delivery_events`) so a queue hiccup
  never slows the outbox sender.

---

## 10. Two code bugs this design exposes (fix in the same phase)

1. `app/services/outbox.py` hardcodes `message.provider = "fake"` on success. With SES
   live, rows are mislabelled. `SubmissionResult` should carry `provider_name`.
2. `email_messages.status` is set to `sent` meaning *accepted*. Add a docstring/comment
   now, and rename the meaning in the UI copy to "accepted" until delivery events land,
   so we never tell a customer "delivered" when we only mean "handed over".

---

## 11. Sandbox, and open/click tracking

- **Sandbox** (current state) sends only to verified recipients. Events still flow
  normally for those, so the whole pipeline can be tested today. The SES **mailbox
  simulator** (`success@simulator.amazonses.com`, `bounce@…`, `complaint@…`) generates
  real `Delivery`/`Bounce`/`Complaint` events on demand — the cheapest end-to-end test.
- **Open/Click** events need a **custom tracking domain** (a CNAME under our domain,
  plus an ACM certificate in the same region for click tracking). That is a separate
  piece of work and of dubious value: pixels inflate open rates and trigger privacy
  blockers. Recommend deferring; ship Delivery/Bounce/Complaint first.

---

## 12. Cost (our volumes, ap-south-1)

| Item | Rate | At 10k emails/month |
|---|---|---|
| SES sending | $0.10/1K (à la carte) | $1.00 |
| SES event publishing → SNS | free | $0 |
| SNS → SQS deliveries | within free tier (1M) | $0 |
| SQS requests (send+receive+delete ≈ 3/event) | 1M free/month | $0 |
| **Total added** | | **≈ $0** |

Even at 1M emails/month the event pipeline is a few dollars; sending dominates.

---

## 13. Suggested sequencing

| Phase | Deliverable | Notes |
|---|---|---|
| 7a | Config set + SNS + SQS + IAM (console/CLI, documented) | no app change; test with mailbox simulator |
| 7b | migration `0005`, `delivery_events` + status columns | |
| 7c | poller + event state machine + tests (mocked SQS) | idempotency is the main test |
| 7d | API: `/events`, `/stats`, filters | |
| 7e | frontend badges + timeline | first UI work in the project |
| 8 | production access request (leave sandbox) | manual, reviewed by AWS |

Each phase is independently shippable and does not break Phase 6.

---

## 14. What we deliberately still do *not* build

- No Redis, no Celery, no websockets.
- No S3 archiving of message bodies.
- No bounce *handling* automation (auto-suppression, auto-unsubscribe) beyond
  recording state — SES already maintains a suppression list, and our
  `delivery_events` trail is enough to decide later.
- No multi-region event mesh.
