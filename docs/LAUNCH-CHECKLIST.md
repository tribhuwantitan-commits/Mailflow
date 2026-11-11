# Launch Checklist — production access, AWS Activate, aur pehla paisa

Status: **planning document.** Kuch bhi yahan "ho gaya" nahi hai. Har item par
tick tab lagayein jab actually ho jaye.

Do applications hain, aur dono ki **apni timing** hai:

| Application | Kab apply | Blocking requirement |
|---|---|---|
| **SES production access** (sandbox se bahar) | code ready hone ke baad, website live hone se pehle bhi chal sakta hai | bounce/complaint handling **actually** bana ho |
| **AWS Activate Founders** ($1,000) | **website live hone ke baad** | live website + company email (own domain) + paid-tier AWS account |

---

## 1. SES production access

### 1.1 Pehle ye samajh lo: aapka case "mushkil" category ka hai

AWS Trust & Safety ke liye sabse aasan case hai: *"ek company apne customers ko
transactional email bhejti hai"*.

Aapka case hai: *"main ek platform hoon, mere customers mere through email bhejte
hain."* Ye **bulk-email-platform** category hai, jo spam infrastructure jaisa lagta
hai. Isliye rejection rate zyada hai — r/aws aur AWS re:Post par log 2-2 baar reject
ho chuke hain, sahi documentation ke baad bhi.

Iska matlab: form mein **jhooth nahi**, par **specifics** chahiye. Neeche draft diya
hai. Aur request **chhoti** maango — 50,000/day maangne se accha 5,000/day maango
(approval ke baad quota automatically badhta hai).

### 1.2 Prerequisites (ye na ho to reject pakka)

| # | Item | Aaj ki halat | Phase |
|---|---|---|---|
| 1 | Domain `testingmail2btd.net` verified, **Easy DKIM SUCCESS** | 🟡 domain verified, DKIM status confirm karna hai | — |
| 2 | SPF record + **DMARC** record publish | ❌ | — (DNS, 10 min) |
| 3 | Configuration set with `ReputationMetricsEnabled` | ❌ | 7c |
| 4 | SNS topic + event destination for `BOUNCE`, `COMPLAINT` | ❌ | 7c |
| 5 | Events consume karne wala code (suppression list update) | ❌ | 7c |
| 6 | Suppression list; send se pehle check hota ho | ❌ | 7c |
| 7 | `List-Unsubscribe` + `List-Unsubscribe-Post` header | ❌ | 7c |
| 8 | Per-tenant daily quota enforcement | ❌ | 7b |
| 9 | Per-customer domain verification (customer apna domain) | ❌ | 7a |
| 10 | Website live: product page + **Terms of Service** + **Acceptable Use Policy** + **Privacy Policy** | ❌ | launch |
| 11 | Bounce < 5%, complaint < 0.1% **measurable** hua ho (dashboard) | ❌ | 9 |

> **Sabse important:** AWS form mein poochhta hai "how do you handle bounces and
> complaints" aur wo **verify** karta hai. Skeleton pe likh dene se kaam nahi chalta.
> Isliye **7b + 7c pehle**, phir application. Yehi asli order hai.

### 1.3 Kahan se apply

SES console → **Account dashboard** → "Sending limits" → **Request production access**.
(Business Support plan ki zaroorat **nahi** hai.)

### 1.4 Form answers (draft — copy karke apne hisaab se badlein)

**Mail type:** `Transactional`

**Website URL:** `https://<aapka-product-domain>` — *live* honi chahiye, aur us page par
saaf likha ho ki product kya karta hai. Placeholder/"coming soon" page reject ho jata hai.

**Use case description:**

```
MailFlow is a transactional email API for small SaaS products and internal tools.
Customers integrate over a REST API and send application-generated email such as
password resets, email verification links, order and invoice receipts, and
account notifications.

We do not allow marketing campaigns, purchased lists, or cold outreach. Our
Acceptable Use Policy (linked in the footer of our site) prohibits them, and
customers must confirm opt-in consent during onboarding.

Each customer must verify ownership of their sending domain. We create a
per-customer SES identity (Easy DKIM) and only permit a From address whose
domain the customer has proven control over. Customers cannot send from a domain
they do not own, and cannot send from our domain.

Volume: currently 0-200 messages/day in testing with our own accounts. Expected
1,000-2,000 messages/day within 3 months of launch, and we are requesting a
starting quota of 5,000 messages/day with room to grow. We are happy to start
lower if that helps review.

Email content is transactional only. Every message is one-to-one, triggered by an
event in the customer's application, and recipients are the customer's own users
who were already using their product.
```

**How do you handle bounces and complaints?** (ye paragraph **strong** hona chahiye)

```
We subscribe to SES event publishing on our configuration set. A SNS topic
receives SEND, DELIVERY, BOUNCE, COMPLAINT, REJECT and DELIVERY_DELAY events and
forwards them to an SQS queue, which our worker consumes.

Hard bounces (bounceType=Permanent) and complaints are written to a per-tenant
suppression list immediately, and that list is checked before every send, so the
address is never contacted again. Soft/transient bounces are retried by SES and
recorded; we do not retry after SES gives up.

We also enable the account-level SES suppression list as a backstop, and our
configuration set has ReputationMetricsEnabled=true.

Each tenant has its own bounce and complaint rate. If a tenant crosses 5% bounce
or 0.1% complaint over a rolling window, our system automatically pauses sending
for that tenant and notifies the account owner. A tenant whose rate stays above
threshold is suspended. This protects the shared sending reputation of the
account and limits the blast radius of a single misbehaving customer.

We monitor our account-level bounce and complaint rates in our own dashboard,
which we built from the same event stream (not from console screenshots).
```

**Acknowledgement:** opt-in only, no purchased lists, will handle bounces/complaints —
tick karein.

### 1.5 Rejection ke top 3 karan (aur bachav)

1. **Vague use case** — "we send emails" likhna. → upar ka specific draft use karein.
2. **Bounce/complaint handling ka proof nahi** — SNS/SQS pipeline banaya hona chahiye,
   aur form mein uske naam likhne chahiye.
3. **Website missing / thin** — sirf "coming soon" page. → ToS + AUP + Privacy + ek
   clear product page chahiye.

Reject ho jaye to **reopen karein** aur poochhein "what concern led to denial, what
additional information can we provide" — ye legit rasta hai.

### 1.6 Approval ke baad

- Default: 50,000/day, 14 msg/sec. **Turant 50k use mat karo.**
- Pehle hafte 200-500/day, phir dheere badhao (warm-up).
- Bounce < 5%, complaint < 0.1% — complaint 0.2%+ par account review mein aa jata hai.
- Aapka per-tenant quota (50/day free) isse **alag** hai — wo aapke code mein hai.

---

## 2. AWS Activate Founders ($1,000)

### 2.1 Eligibility (2026)

| Requirement | Aapka status |
|---|---|
| Self-funded / bootstrapped, no VC affiliation | ✅ |
| < 10 employees, < $1M revenue, < 10 years old | ✅ |
| **Live website** describing the product | ❌ — launch tak wait |
| **Company email on your own domain** (not Gmail) | ⚠️ — `@testingmail2btd.net` par mailbox banana hoga |
| AWS account on **paid tier** (not free-tier-only) | ⚠️ — pehla bill aa jane do |
| No prior Activate credits | ✅ |

Apply: `aws.amazon.com/activate` → **Founders** → company profile → submit.
Decision often instant, kabhi 1-3 business days.

**Credits milte hain:** up to $1,000 + $350 Developer Support credits.
**Validity:** sources 1 saal aur 2 saal dono bolte hain — approval page par jo likha ho
wahi maanein. **Expiry se pehle spend na karne ka koi fayda nahi, kyunki unused
credits expire ho jate hain.**

### 2.2 Rejection ke karan

- Gmail/Yahoo address se apply karna (company domain se karo)
- Website live nahi / product clear nahi
- AWS account free tier par hi hai
- Wahi company name / tax ID se dobara apply (AWS de-duplicate karta hai)
- Dev agency/consultancy lag raha ho, product company nahi

---

## 3. "4-6 mahine survive" — ye hisaab galat hai

Aapka assumption: $1,000 credits = 4-6 mahine ka kharcha. Ye **tabhi** sach hai jab
aap **AWS par Windows Server + RDS** chalao. Dekho:

| Setup | Monthly | $1,000 se kitne mahine |
|---|---|---|
| Windows EC2 m5.large + RDS Postgres + ALB | ~$160-190 | **5-6** |
| Windows EC2 t3.medium + RDS db.t4g.micro | ~$95-110 | **9-10** |
| Linux t3.small + Neon free Postgres | ~$16 | 60+ (magar credits expire) |
| **Sirf SES** (app kahin aur chalao) | **~$1-10** | **~100 mahine ka SES** |

Yani: **$1,000 credits 4-6 mahine mein sirf isliye khatam honge kyunki Windows Server
AWS par chal raha hai.** Windows license AWS par 2-3x mehnga padta hai Linux se.

### 3.1 Isliye sifarish

Aapke paas already Windows Server (RDP) hai — **app wahi chalao**. AWS par sirf:

- **SES** (sending) — $0.10/1,000 emails
- **S3** (baad mein, archiving) — pennies
- **SNS + SQS** (events) — free tier ke andar
- **Neon** (Postgres) — free tier, jo aapke paas already hai

Isse aapka **asli monthly kharcha ~$1-5** ho jata hai, aur $1,000 credits *poora*
insurance ban jate hain — jab traffic aaye, ya jab AWS par shift karna ho, tab kaam
aayenge. Credits expiring hain, to unhe jalaana nahi hai; unhe *option* ki tarah
rakhna hai.

**Aur ek baat:** Windows Server par FastAPI + PostgreSQL chalana technically chalega,
par 8-10 customers ke baad process/connection management, TLS, backup, restart pe
bharosa — sab manual. Din aane par Linux VPS (~₹500-1,500/mo) sasta aur kam dard
hoga. Abhi ke liye jo hai wahi theek hai, bas AWS par shift karne ki jaldi mat karo.

---

## 4. Timeline (suggested)

| Week | Kaam | Deliverable |
|---|---|---|
| 1 | Phase 6.5: SES live test (`check_ses`, `send_test`) | asli email jaata hai |
| 2-3 | Phase 7a: per-customer domain verification + per-tenant `Source` | customer apna domain verify karta hai |
| 3-4 | Phase 7b: quota enforcement (recipients par, daily reset) | 50/day limit actually lagta hai |
| 4-5 | Phase 7c: SNS/SQS events + suppression + auto-pause + List-Unsubscribe | bounce/complaint **actually** handle hota hai |
| 5 | Website live: product page + ToS + AUP + Privacy + company mailbox | Activate + SES dono unblock |
| 6 | **SES production access apply** | 5,000/day request |
| 6 | **AWS Activate Founders apply** | $1,000 |
| 7-8 | Phase 9: dashboard (delivery_events, stats API, UI) | Resend-jaisa data |
| 9 | Phase 10: card verification / plans | 100/day tier |
| launch | Paid plans | — |

Production access **dashboard se pehle** apply ho raha hai — ye jaan-boojhkar hai:
AWS ko bounce/complaint *handling* chahiye, *dashboard* nahi. Handling 7c mein ban
jayega.

---

## 5. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Ek free tenant spam bhejta hai | **poora SES account pause** — sab customers ka mail band | per-tenant quota + auto-pause at 5%/0.1% + verified-domain-only |
| Production access reject | launch rukta hai | 7b/7c pehle; specific form; modest quota ask |
| Credits jaldi khatam | AWS bill | AWS par sirf SES; app apne server par |
| Activate reject (no website) | $1,000 nahi milta | website live hone ke baad hi apply |
| Sandbox 200/day = sabka combined cap | 4 free customers aur khatam | production access launch se pehle |
| Card verification se abuse | chargebacks | ₹2 auth + velocity limits (Phase 10) |
