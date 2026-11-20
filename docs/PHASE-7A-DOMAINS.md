# Phase 7a — per-customer domain verification

Status: **implemented.** Tests: **122 passed, 1 skipped** (PostgreSQL still unvalidated).

---

## 1. Problem jo theek hua

Pehle `app/providers/ses.py` hardcode karta tha:

```python
Source=self.settings.ses_from_email      # hamesha aapka domain
```

Matlab: **har customer aapke `testingmail2btd.net` se bhejta**. Teen problem:

| Problem | Nateeja |
|---|---|
| Customer apna brand nahi dikha sakta | `noreply@myapp.com` nahi, `@testingmail2btd.net` dikhta |
| **DKIM fail** | tumhare domain ki signing, customer ke domain ke naam par — Gmail spam |
| Koi bhi kisi ka bhi domain likh sakta | `ceo@bank.com` se email — impersonation |

Ab: **har tenant pehle apna domain verify karta hai, phir wahi domain `Source` banta hai.**

---

## 2. Naya flow

```
1. Customer signup                     → plan = free
2. POST /v1/organizations/{id}/domains → SES identity banta hai (Easy DKIM)
                                         → 3 CNAME records wapas milte hain
3. Customer DNS mein CNAME daalta hai
4. POST .../domains/{id}/check          → SES se status padha, verified
5. POST /v1/emails                      → Source = customer ka domain ✅
```

**Step 5 se pehle koi send nahi.** Verification ke bina → `403 sender_domain_not_verified`.

---

## 3. Naye endpoints

| Method | Path | Kaam |
|---|---|---|
| `GET` | `/v1/organizations/{id}/domains` | list (member bhi dekh sakta) |
| `POST` | `/v1/organizations/{id}/domains` | add + SES identity (**owner only**) |
| `POST` | `/v1/organizations/{id}/domains/{domain_id}/check` | re-check SES |
| `DELETE` | `/v1/organizations/{id}/domains/{domain_id}` | remove (**owner only**) |

### Add karne par

```json
POST /v1/organizations/<id>/domains
{"domain": "acme.com"}
```

```json
201 Created
{
  "id": "...",
  "domain": "acme.com",
  "status": "pending",
  "dns_records": [
    {"type": "CNAME", "name": "tok1._domainkey.acme.com", "value": "tok1.dkim.amazonses.com"},
    {"type": "CNAME", "name": "tok2._domainkey.acme.com", "value": "tok2.dkim.amazonses.com"},
    {"type": "CNAME", "name": "tok3._domainkey.acme.com", "value": "tok3.dkim.amazonses.com"}
  ],
  "verified_at": null
}
```

`dns_records` **seedha copy-paste** karne layak hai — har DNS UI (GoDaddy, Cloudflare,
Namecheap) isi shape ko accept karta hai.

### Send refused

```json
403 Forbidden
{"error": {"code": "sender_domain_not_verified",
           "message": "The domain acme.com is not verified for this organization.
                       Add and verify it under Sending domains before sending from it."}}
```

---

## 4. Public mail providers — pehle hi refuse

`gmail.com`, `yahoo.com`, `outlook.com`, `proton.me`, `rediffmail.com` — inka DNS
customer control nahi karta, to verify **ho hi nahi sakta**. Isliye registration par
saaf message:

```json
400 Bad Request
{"error": {"code": "domain_not_verifiable",
           "message": "gmail.com is a public mail provider, so its DNS cannot be
                       verified. Verify a domain you own and send from that instead."}}
```

Ye product decision hai, bug nahi — user ko **kya karna hai** batata hai, sirf "invalid" nahi.

---

## 5. Ek domain = ek tenant

```
UNIQUE (domain)              ← global
UNIQUE (organization_id, domain)
```

**Kyun global unique:** SES identities account-wide hoti hain. Do tenants ek hi domain
claim karein to ek doosre ke naam se bhej sakega. Isliye doosra claim **SES ko chhue
bina** `409 domain_taken` milta hai.

Test `test_same_domain_cannot_be_claimed_by_two_tenants` yahi verify karta hai:
`verifier.registered == ["brand.example"]` — sirf ek baar.

---

## 6. Subdomain implicit nahi

`acme.com` verify karne se **`mail.acme.com` verify nahi hota.** SES bhi yahi maanta hai
(identity exact match). Isliye:

| Verified | Send from | Result |
|---|---|---|
| `acme.com` | `noreply@acme.com` | ✅ |
| `acme.com` | `noreply@mail.acme.com` | ❌ 403 |

Agar customer ko subdomain chahiye, wo **alag se add** karega. Test
`test_subdomain_of_verified_apex_is_not_implicitly_verified` cover karta hai.

---

## 7. Send gate — quota se pehle

`submit_email` ka order ab:

```
1. API key check
2. idempotency lookup          → replay yahan ruk jata hai
3. sender domain check         → 403, QUOTA NAHI KHAYI
4. quota reserve               → 429
5. INSERT email + outbox
6. COMMIT
```

**Step 3 step 4 se pehle kyun:** warna ek customer 50 baar `ceo@bank.com` bhej ke apna
daily quota khatam kar dega aur asli emails nahi bhej payega. Test
`test_refused_send_does_not_consume_quota` isko pin karta hai.

---

## 8. Verification adapter

`app/providers/ses_identities.py` — **`sesv2` client** (identity management), sending wale
`ses` (v1) se alag:

| Provider | Kaam |
|---|---|
| `app/providers/ses.py` | `send_email` — actual sending, outbox worker se |
| `app/providers/ses_identities.py` | `create_email_identity`, `get_email_identity`, `delete_email_identity` — interactive requests se |

**Kyun alag:** sending retry hoti hai (worker), identity calls **interactive** hain —
failure seedha customer ko dikhni chahiye, retry nahi. Failure tolerance bilkul different hai.

### `MAIL_PROVIDER=fake` par

`NoopDomainVerifier` — sab kuch instantly verified. Matlab: **development aur tests ko
AWS ki zaroorat nahi**, magar ownership check phir bhi chalta hai (domain row exist
karni chahiye).

---

## 9. Kyun pending row pehle, SES call baad mein

```python
db.add(row)          # status="pending"
db.flush()           # ← unique constraints yahan test hote hain
state = verifier.register(domain)   # phir SES
```

Ulta karne par: crash ke beech SES identity ban jati, **customer ko kuch nahi dikhta** —
orphan identity. Isse acha pending row ho jo dashboard par dikhe.

⚠️ Ek chhoti window bachi hai: `flush` ke baad SES call fail ho jaye to pending row
`last_error` ke saath reh jata hai. Customer `check` dabata hai, wo retry karta hai. Ye
acceptable hai — identity banane ka retry idempotent hai (`AlreadyExistsException` handle hai).

---

## 10. Migration

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
# 0006_domains (head)
```

| Table | Kya |
|---|---|
| `domains` | id, organization_id, domain, status, dkim_tokens, last_checked_at, last_error, verified_at |

Constraints: `uq_domains_global_domain`, `uq_domains_org_domain`, `ck_domains_status`,
`ck_domains_lowercase`, index `ix_domains_org_status`.

⚠️ **Purane tenants ka data:** koi tenant verified nahi hai, to upgrade ke baad
**sabhi sends 403 denge**. Production launch se pehle har tenant ko domain add karna
padega — ye **intended** hai (customer apna domain verify kare).

---

## 11. Kya nahi bana

| Cheez | Kyun nahi | Kab |
|---|---|---|
| **Auto-poll verification** | SES ~72 ghante tak verify karta hai; polling har 5 min = SES API calls | Phase 9 (background job) |
| **SPF/DMARC check** | SES sirf DKIM batata hai; SPF/DMARC DNS lookup humein karna padega | Phase 7c |
| **Wildcard domain** | SES wildcard identity support karta hai, magar UI complexity | later |
| **Per-domain sending stats** | dashboard chahiye pehle | Phase 9 |
| **`Source` per-message override** | abhi `message.sender` hi `Source` hai — service layer 7a ke saath wire hoga | **next commit** |

### ⚠️ Ek cheez abhi baaki hai

`app/providers/ses.py` abhi bhi `Source=self.settings.ses_from_email` use karta hai.
Ownership **gate** lag gaya hai (send refuse hota hai), magar jab allowed hai to
`Source` **`message.sender`** hona chahiye, `ses_from_email` nahi.

**Ye next commit mein hai** — provider change chhota hai, magar `ses.py` ke saare tests
touch karta hai, isliye alag rakha hai:

```python
Source=message.sender or self.settings.ses_from_email
```

Abhi tak safe hai kyunki koi real customer nahi, aur `MAIL_PROVIDER=fake` chalta hai.

---

## 12. Test coverage — 32 naye

| Group | Kya cover hua |
|---|---|
| Validation | normalize (scheme/www/case), public providers refused, email-vs-domain message, malformed |
| Lifecycle | register + DNS records, already-verified, duplicate tenant, duplicate org, check promotes, check marks failed, delete removes identity |
| Permissions | member read-only, cross-tenant 404 |
| Send gate | refused without domain, refused while pending, allowed after verify, other tenant still refused, **quota untouched by refusal**, subdomain not implicit |
| Unit | DB-backed `sender_domain_allowed` |

---

## 13. Checklist

| # | Kaam | Kaise |
|---|---|---|
| 1 | Migration | `alembic upgrade head` |
| 2 | Domain add karo | `POST /v1/organizations/{id}/domains` |
| 3 | CNAME publish karo | `dns_records` copy-paste |
| 4 | Check dabao | `POST .../{id}/check` |
| 5 | Send karo | ab `202` milega |
| 6 | `Source` fix karo | **next commit** |
