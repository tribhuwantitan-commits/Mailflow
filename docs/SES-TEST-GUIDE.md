# SES Phase 6 test — IAM, identities, aur zaroori corrections

Ye doc **jo aaj karna hai** uske liye hai: ASLI SES email bhejna. ~20 minute.

---

## 0. Do corrections pehle

### ❌ "IAM role" tumhare setup mein kaam nahi karega

IAM **role** tab kaam aata hai jab code **AWS ke andar** chale (EC2, Lambda, ECS) —
wahan credentials khud inject hote hain. Tumhara app **apne VPS** par chalega, AWS ke
bahar. Wahan role ka koi rasta nahi hai.

Tumhe chahiye: **IAM user + access key** (jo `.env` mein jaayega).

| Tumne kaha | Sahi hai |
|---|---|
| "IAM role banaunga" | **IAM user** banao, programmatic access ke saath |

(Agar kal Lambda/EC2 par shift karo, tab role better hai — credentials rotate nahi karne
padte. Aaj nahi.)

### ⚠️ "Kitna email verify karu" — definition clear karo

SES mein do alag cheezein hain:

| | Kya hai | Kitne chahiye |
|---|---|---|
| **Identity** (verification) | "main is domain/address se bhej sakta hoon" | **1 identity** = poora domain. `testingmail2btd.net` verify hai to `noreply@`, `support@`, `billing@` — **sab** chalega, alag verify nahi karne |
| **Recipient** (sandbox) | "is address ko bhej sakta hoon" | sandbox mein **1** (apna Gmail) — simulator ke liye 0 |

**Isliye:**
- **Domain identity: 1** (`testingmail2btd.net`) — ✅ already hai
- **Email address identity: 0** — zaroorat nahi, domain hi kaafi hai
- **Recipient address verify: 1** (sirf sandbox ke liye, apna personal Gmail)

10,000 identities ki limit ka koi tension nahi — tum 1 use kar rahe ho.

---

## 1. IAM user banao (5 min)

Console → **IAM** → Users → **Create user**

| Field | Value |
|---|---|
| User name | `mailflow-ses-sender` |
| Access type | ✅ **Programmatic access only** (console access ❌) |

**Do policies:**

**a) `AmazonSESFullAccess`** (AWS managed) — testing ke liye, magar over-permissive hai
(wo template/inbound/AI sab manage kar sakta hai).

**b) `deploy/iam/mailflow-ses-send-policy.json`** — minimal. Isme sirf:
`SendEmail`, `SendRawEmail`, `GetSendQuota`, `GetSendStatistics`, `ListIdentities`,
`GetIdentityVerificationAttributes`.

**Recommendation:** testing ke liye `AmazonSESFullAccess` use karo, **production mein
minimal policy** par shift ho jao. Ya directly minimal use karo — `check_ses` script
ko inhi 6 permission ki zaroorat hai.

> Agar `ses:DescribeConfigurationSet` bhi add karna ho (Phase 7c mein lagega), abhi
> daal do.

**Access key** banate hi `.env` mein daalo.

### ⚠️ MFA + root account

Root account par MFA lagao (agar nahi hai), aur **root ka access key kabhi mat banao**.
Sirf `mailflow-ses-sender` user ka key use karo.

---

## 2. `.env` bharo

`backend/.env` (`.env.example` se copy):

```bash
MAIL_PROVIDER=ses
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=AKIA................
AWS_SECRET_ACCESS_KEY=................................
SES_FROM_EMAIL=noreply@testingmail2btd.net
SES_CONFIGURATION_SET=
```

`SES_CONFIGURATION_SET` **khaali chhodo** — wo Phase 7c ka kaam hai (warna `not found` error aayega).

`.env` gitignore mein hai? Check karo: `git check-ignore backend/.env`

---

## 3. Verify karo — koi email nahi jayega

```bash
cd backend
python -m app.scripts.check_ses
```

Jo check hoga: credentials valid, **domain usi region (Mumbai) mein verified**, config
set (khaali, to warn), quota, sandbox status, DNS.

**Achha output aisa dikhega:**
```
[OK  ] AWS_REGION: ap-south-1
[OK  ] identity.domain: testingmail2btd.net verified (covers noreply@...)
[OK  ] quota.24h: 0 / 200 sent in last 24h
[OK  ] quota.rate: 1 emails/second
[WARN] sandbox: looks like SANDBOX (max 200/24h, 1/s)
[WARN] SES_CONFIGURATION_SET: (empty) — no open/click/bounce events
failures: 0   warnings: 2
```

`[FAIL] identity` aaya to matlab domain **kisi doosre region** mein verified hai.
Mumbai console mein jao aur dhyan se dekho.

---

## 4. Pehla send — simulator (asli inbox par nahi)

```bash
python -m app.scripts.send_test --to success@simulator.amazonses.com
```

Expected:
```
accepted: provider_message_id=01000193-...
This is an acceptance receipt only — not proof of delivery.
Simulator address: SES counted it, nothing was delivered anywhere.
```

### Simulator addresses (sandbox testing ke liye)

| Address | Kya karta hai |
|---|---|
| `success@simulator.amazonses.com` | accept + deliver (kuch nahi jaata) |
| `bounce@simulator.amazonses.com` | **hard bounce** generate karta hai |
| `complaint@simulator.amazonses.com` | **spam complaint** generate karta hai |
| `suppressionlist@simulator.amazonses.com` | suppression hit |
| `otp@simulator.amazonses.com` | OTP-style |

**Ye Phase 7c ke liye sona hai** — bounce/complaint pipeline bina kisi asli inbox ko
chhue test ho jayega.

---

## 5. Asli inbox test

Sandbox mein sirf **verified recipient** ko jaata hai. To apna Gmail verify karo:

SES console → **Mumbai** → Identities → **Create identity** → **Email address** →
apna Gmail → verification mail aayega → link click.

**Kitne verify karo?** Sirf **1** — testing ke liye kaafi. Har verified address ek
identity hai (limit 10,000, par irrelevant).

Phir:
```bash
python -m app.scripts.send_test --to tumhara@gmail.com
```

Gmail mein mail aaye → **Phase 6 ka core test pass**. 🎉

---

## 6. End-to-end test (API + outbox + DB)

Ab poora stack:

```bash
# terminal 1
python -m uvicorn app.main:app --port 8000

# terminal 2
python -m app.services.outbox --status
python -m app.services.outbox        # ek tick
```

`--status` par pending 0 hona chahiye. Phir API se email bhejo (register → login →
org → api-key → POST /v1/emails), aur outbox worker chalao.

Verify: `GET /v1/emails/{id}` par
- `"provider": "ses"` ← (ye bug fix commit `1ed6cac` mein hai)
- `"provider_message_id": "01000193-..."`
- `"status": "sent"`

⚠️ **`status: "sent"` ka matlab "accepted by SES" hai, "delivered nahi".**
Delivered/bounced ka pata Phase 7c ke events se chalega.

**Outbox worker ko loop mein chalana:** `python -m app.services.outbox` ek tick karta
hai. Windows Task Scheduler ya cron se har 5-10 second chalao, ya `while` loop likho
(production mein proper supervisor chahiye — Phase 7 mein).

---

## 7. Kya-kya test karo (checklist)

| # | Test | Kaise | Pass ka criteria |
|---|---|---|---|
| 1 | Credentials | `check_ses` | `failures: 0` |
| 2 | Region match | `check_ses` | identity domain verified `ap-south-1` |
| 3 | Simulator send | `send_test --to success@...` | MessageId mila |
| 4 | Real inbox | `send_test --to gmail` | mail inbox mein |
| 5 | HTML + text | API se `html_body` + `text_body` | dono dikhe |
| 6 | Idempotency | same `Idempotency-Key` 2x | ek hi email |
| 7 | Error handling | **galat** access key | `PermanentProviderError`, worker retry nahi |
| 8 | Quota | `check_ses` | 200/24h dikhe |
| 9 | DB label | API detail | `provider: "ses"` |
| 10 | Bounce (optional) | `send_test --to bounce@simulator...` | accept, magar bounce aayega (Phase 7c mein dikhega) |

**Test 7 kaise:** `.env` mein secret key ka last character hata do → `send_test` →
`PERMANENT failure` aana chahiye (retry nahi).

---

## 8. Aur ek zaroori: bounce aur complaint rate **abhi se** track karo

Sandbox mein bhi AWS tumhara bounce/complaint rate dekhta hai. **Yaad rakho:**

| Metric | Limit |
|---|---|
| **Bounce rate** | < 5% (10%+ par pause) |
| **Complaint rate** | < 0.1% (0.2%+ par review) |

Sandbox mein volume kam hai to jaldi farq padta hai. **Galat addresses par test mat karo.**

---

## 9. Aaj ka realistic time budget

| Step | Time |
|---|---|
| IAM user + access key | 3 min |
| `.env` + `check_ses` | 2 min |
| Simulator send | 1 min |
| Gmail recipient verify | 2 min (+ mail wait) |
| Real send | 1 min |
| End-to-end API test | 10 min |
| **Total** | **~20 min** |

---

## 10. Agla step

Test pass hone par:
1. Access key ko **rotate** karne ka reminder lagao (90 din)
2. `AmazonSESFullAccess` ko minimal policy se replace karo (production)
3. **Phase 7c** (config set + SNS + SQS + suppression) — iske bina dashboard nahi banega
   aur iske bina production access bhi nahi milega
