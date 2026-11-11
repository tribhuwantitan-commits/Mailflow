# Per-domain verification — kahan hota hai, aur "SES Tenants" kya hai

Ye do **alag** cheezein hain. Inhe mix karna hi confusion ki jad hai.

| | Domain verification (DKIM) | SES **Tenants** |
|---|---|---|
| Kaam | Customer ka domain SES mein register + verify karna | SES ke andar per-customer isolated container |
| Kahan hota hai | **Aapke platform par** (aapke backend se SES API calls) | AWS ke andar (aapke account mein) |
| Customer ko AWS account chahiye? | ❌ nahi | ❌ nahi |
| Kya ye zaroori hai? | ✅ **haan** — bina iske customer apne domain se nahi bhej sakta | ❌ optional (magar ISV ke liye recommended) |
| Cost | free | ~$0.005/tenant/month + $0.005/1,000 emails |
| Limit | 10,000 identities per Region (badhaya ja sakta hai) | 10,000 tenants (300,000 tak auto-approval) |

**Ek line mein:** domain verification aapke platform ka feature hai. SES Tenants ek AWS
ka *optional* feature hai jo reputation isolate karta hai. Dono ek saath chal sakte hain,
magar ek doosre ke bina bhi kaam karte hain.

**Aur sabse ahem:** customer ko **apna AWS account lena hi nahi hai**. Aapka AWS account
hai, aapke credentials se SES calls hoti hain, bill aapko aata hai (aur wahi aapka
business model hai — aap usage charge karte ho).

---

## 1. Domain verification — aapke platform par (Phase 7a)

### Flow

```
Customer (aapki dashboard/API par)
   │  POST /v1/domains  {"domain": "mail.theirdomain.com"}
   ▼
Aapka backend ──► SES CreateEmailIdentity(Domain)   [aapke AWS credentials]
   │                 └─ return: 3 DKIM CNAME tokens
   ├─ domains table: status = pending, tokens saved
   ▼
Customer ko dikhaya: "ye 3 CNAME apne DNS mein daalo"
   │   mf1._domainkey.mail.theirdomain.com  CNAME  mf1.dkim....
   │   mf2._domainkey...                   CNAME  mf2.dkim....
   │   mf3._domainkey...                   CNAME  mf3.dkim....
   ▼
verify worker (har 5 min) ──► SES GetEmailIdentity
   │                            DkimAttributes.Status == "SUCCESS" ?
   ├─ haan → status = verified, verified_at = now()
   └─ nahi → retry (24-72 ghante tak, DKIM propagation)
   ▼
Ab POST /v1/emails mein "from": "noreply@mail.theirdomain.com" allowed
```

Customer ko sirf **3 CNAME** daalne hain. Na AWS console, na credentials, na SDK.

### API

```
POST   /v1/domains                       {"domain": "..."} → 201 + DKIM records
GET    /v1/domains                       list + status
GET    /v1/domains/{id}                  detail + tokens + last error
POST   /v1/domains/{id}/verify           manual re-check (button)
DELETE /v1/domains/{id}                  revoke (SES DeleteEmailIdentity bhi)
```

### Table (migration `0005`)

```sql
CREATE TABLE domains (
    id              uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain          varchar(253) NOT NULL,
    ses_identity    varchar(253) NOT NULL,   -- same as domain
    dkim_tokens     jsonb NOT NULL,          -- 3 tokens for display
    dkim_status     varchar(16) NOT NULL DEFAULT 'PENDING',
                    -- PENDING | SUCCESS | FAILED | TEMPORARY_FAILURE
    status          varchar(16) NOT NULL DEFAULT 'pending',
                    -- pending | verified | failed | revoked
    verified_at     timestamptz,
    last_checked_at timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (domain)                          -- ek domain, ek hi tenant ka
);
CREATE INDEX ix_domains_org ON domains (organization_id);
```

`UNIQUE (domain)` zaroori hai: warna do tenants ek hi domain claim kar sakte hain
aur ek doosre ke naam se bhej sakte hain.

### Send-time enforcement (yahi asli suraksha hai)

`POST /v1/emails` mein, provider tak jaane se pehle:

```python
sender_domain = payload.sender.split("@")[1].lower()
# 1) us org ka verified domain hona chahiye
# 2) payload.sender usi domain (ya uske subdomain) ka hona chahiye
# warna: 403 sender_domain_not_verified
```

aur provider mein `Source` **per-message** jaana chahiye:
`SESEmailProvider.submit()` abhi `self.settings.ses_from_email` use karta hai (line 73).
Ise `message.sender` karna padega — **yahi wo ek-line change hai jiske bina per-customer
domain ka koi matlab nahi**.

### Best practice (optional, baad mein)

Custom **MAIL FROM** subdomain (`bounce.theirdomain.com`) — DMARC alignment aur
bounce routing behtar karta hai. SES mein "Custom MAIL FROM domain" kehta hai, 2 extra
MX/TXT records. Phase 7a mein zaroori nahi, 7c ke baad add kar sakte hain.

---

## 2. SES Tenants — kya hai, kab lena hai

### Ye kya karta hai

SES mein har **tenant** ek container hai jisme uske identities, configuration sets aur
**reputation metrics** alag rehte hain. Fayde:

- **Per-tenant reputation pause**: agar ek customer ka bounce rate 15% chala jaye, AWS
  (ya aap) **sirf us tenant** ko pause karta hai — baaki customers bhejte rehte hain.
- **Trust & Safety targeted action**: pehle AWS poora account pause kar deta tha;
  tenants hone par wo sirf kharab tenant ko band karta hai.
- **Tenant-level suppression list**: ek customer ka bounce doosre customer ke recipient
  ko suppress nahi karta (default account-level list mein aisa hota hai).

### Ye kya *nahi* karta

AWS docs saaf kehte hain: *"their combined sending activity still affects your overall
account reputation — tenants that develop poor sending practices could put your entire
account at risk."* Yani risk **kam** hota hai, **khatam nahi**. Aapko apna auto-pause
(Phase 7c) phir bhi chahiye.

Aur: tenant use karne ke liye **config set tenant se associated** hona chahiye, aur
`send_email` call mein tenant specify karna padta hai. Yani ye ek **architecture
commitment** hai, ek checkbox nahi.

### Cost

| | Rate | 100 customers | 1,000 customers |
|---|---|---|---|
| Per tenant/month | $0.005 | $0.50 | $5.00 |
| Per 1,000 emails | $0.005 | +5% on sending | +5% on sending |
| **Total ≈** | | **~$0.5-1/month** | **~$5-8/month** |

Sasta hai. Magar **testing phase mein fizool** hai — jab customers hi nahi hain.

### Recommendation

| Kab | Kya |
|---|---|
| **Ab (testing, sandbox)** | Tenants **nahi**. Sirf domain verification + per-tenant `Source`. |
| **Pehle 10-20 paying customers** | 7c ke saath apna auto-pause (bounce/complaint per tenant) — ye Tenants se pehle wala safety net. |
| **~20+ customers, ya pehli baar abuse** | **Tenants on karo.** Design abhi se ready rakho: `organizations.ses_tenant_name` nullable column, aur provider `TenantName` pass kare jab set ho. |

Isliye Phase 7a mein `organizations` table mein ek nullable `ses_tenant_name` daal dena
theek hai — 1 column, aaj kaam nahi karega, kal refactor nahi karna padega.

---

## 3. Domain verification ke gotchas (jo AWS docs mein bikhre hue hain)

1. **Identities per-Region hain.** `ap-south-1` mein verify kiya to `us-east-1` mein nahi.
   Aapka `AWS_REGION` fix rahe, aur customer ko wahi region dikhe.
2. **Domain verify karne se uske saare subdomains cover ho jate hain.** `example.com`
   verify hua to `a.example.com`, `mail.example.com`, `user@example.com` sab chalega.
   Isliye customer ko **root domain** ya jo subdomain wo bhejna chahta hai, wahi verify
   karana chahiye — aur UI mein saaf likhna chahiye.
3. **Email address aur domain alag identities hain.** `gmail.com` verify nahi kar sakte
   (aapke paas DNS nahi). Free-plan users ke liye aapko apna **subdomain** dena hoga
   (`customer1.mailflow.app`) — wo aapke control mein hai.
4. **DKIM propagation 24-72 ghante** le sakti hai (DNS TTL + SES polling). UI mein
   "usually a few minutes, up to 72 hours" likhna, warna support tickets aayenge.
5. **DeleteEmailIdentity** karne par us domain se sending turant band. Revoke flow mein
   ye call karna, warna SES mein orphan identities pade rahenge (10,000 limit).
6. **10,000 identities per Region.** Chhote SaaS ke liye kaafi, magar ye limit yaad
   rakhna — har customer ka domain = 1 identity.
