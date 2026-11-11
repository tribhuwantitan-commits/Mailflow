# Email Service Providers — benchmark: pricing, revenue, customers, unit economics

Research date: **November 2026**. Ye document sirf benchmark hai — koi decision nahi.

## 0. Data honesty — pehle ye padho

| Source type | Kitna bharosa | Kaun |
|---|---|---|
| **SEC 10-K / 8-K** | ✅ exact | Klaviyo (NYSE: KVYO) — revenue, gross profit, net loss, customers |
| **Company press release** | ✅ bharosa karo | Brevo (>€200M ARR, 600k customers), ActiveCampaign ($250M+ ARR, 180k) |
| **Public pricing page** | ✅ exact | sabke plan prices |
| **Third-party estimate** | ⚠️ rough | GetLatka, ZoomInfo, CB Insights — inme 10x farq dekhne ko milta hai, ignore karo |

⚠️ **Example of bad data:** GetLatka Brevo ka revenue **$21.9M** batata hai, ZoomInfo **$189.7M**,
Brevo ka apna press release **$230M**. Ek hi company, teen numbers. Isliye neeche har figure
par source likha hai. **Private companies ka profit koi publicly nahi batata** — jo bhi
"profit" number kisi blog par mile, wo estimate hai.

---

## 1. Ek nazar mein — sab providers

| Provider | Type | Revenue (annual) | Customers | ARPU/month | Profit | Pricing model |
|---|---|---|---|---|---|---|
| **Klaviyo** (listed) | Marketing automation + email/SMS/WhatsApp | **$1,234M** (2025, +32%) | **193,000** paying | **~$533** | GAAP net **loss $31.8M**; non-GAAP operating **+$169M** (14%) | by active profiles |
| **Brevo** (private) | All-in-one CRM, email+SMS+WA | **~$230M** ARR (2025) | **600,000** | **~$32** | **profitable**, "double-digit EBITDA margin" | by email volume + contacts |
| **Mailchimp** (Intuit) | Marketing email + automation | **$800M** (2020 pre-acq) → Intuit segment | 800,000 **paid** (2021); 13M total users | ~$80-100 historically | Intuit segment mein mixed | by contacts + sends |
| **ActiveCampaign** (private) | Marketing automation + CRM | **$250M+** ARR | **180,000+** | **~$115** | profitable (not disclosed) | by contacts |
| **SendGrid** (Twilio) | Transactional + marketing API | ~$400M+ at acquisition (2019) | 80,000+ (2019) | ~$400 | inside Twilio segment | by volume |
| **Mailgun** (Sinch) | Transactional API, dev-first | not broken out | — | — | inside Sinch | by volume |
| **Postmark** (ActiveCampaign) | **Transactional only**, deliverability-first | not broken out | — | — | "profitable" (independent era) | flat + overage |
| **Resend** (private, VC) | Transactional API, dev-first | est. **$5-15M** ⚠️ | est. 10-20k ⚠️ | ~$25-50 ⚠️ | **likely loss-making** (VC-funded) | plan + overage |
| **Mailjet** (Sinch) | Marketing + transactional, EU | not broken out | — | — | inside Sinch | volume |
| **ZeptoMail** (Zoho) | **Transactional only**, India | not broken out | — | low | Zoho group profitable | prepaid credits |
| **Mailtrap** (private) | Testing + sending | not broken out | — | — | small, self-funded | volume |
| **Amazon SES** | **Infrastructure** (not an ESP) | part of AWS | — | — | — | $0.10/1K |

**Sabse ahem insight:** Klaviyo ka ARPU **$533/month** hai aur Brevo ka **$32/month**.
Donon email bhejte hain. Farq ye hai: Klaviyo **marketing automation platform** bechta hai,
Brevo **sasta email tool** bechta hai. Aapko yahi chunna hai.

---

## 2. Klaviyo — ekmatra verified P&L

Kyunki ye listed company hai, iske numbers sabse zyada sikhate hain.

| Metric | 2023 | 2024 | 2025 |
|---|---|---|---|
| Revenue | $698.1M | $937.5M | **$1,234.0M** |
| Cost of revenue | — | $221.3M | **$312.5M** |
| **Gross profit** | — | $716.2M | **$921.5M** |
| **Gross margin** | — | 76% | **75%** |
| Operating income (non-GAAP) | — | $112.5M | **$169.2M** (13.7%) |
| **Net income (GAAP)** | **−$308.2M** | **−$46.1M** | **−$31.8M** |
| Customers | — | 167,000 | **193,000** |
| Employees | — | — | 2,368 |
| NRR (net revenue retention) | — | — | **110%** |
| Free cash flow | — | — | **$200M** |

### Yahan se 4 sabak

1. **Gross margin 75%.** Har $1 revenue par $0.25 COGS. Email infrastructure COGS mein
   sabse bada hissa **nahi** hai — support, (aws), SMS/WhatsApp carrier fees hain. Email
   send karna $0.10/1K hai; usme 75% margin chhoda ja sakta hai.
2. **2023 mein $308M loss, 2025 mein $32M loss.** 10 saal, VC funding, tab jakar
   break-even ke kareeb. **Ye business slow-compounding hai, rocket nahi.**
3. **NRR 110%** — purane customers ka spend har saal 10% badhta hai. Email business
   ka asli engine yahi hai: naye customer se zyada purane customer ka grow karna.
4. **Employees 2,368, revenue $1.2B** → **$521k revenue per employee.** Ye ratio
   software company ka hai, services company ka nahi. Support cost per customer $533
   ARPU par affordable hai. **$32 ARPU par support cost hi kha jayega.**

---

## 3. Public pricing — sabka, side by side

### Transactional / API providers

| Provider | Free tier | Entry paid | Effective per 1K | 100k/month cost |
|---|---|---|---|---|
| **Amazon SES** | credits only | $0.10/1K à la carte | **$0.10** | **~$10** |
| **Elastic Email** | — | $0.09/1K | $0.09 | ~$9 |
| **ZeptoMail (Zoho)** | 10k free credit | $2.50 per 10k credit | **$0.25** | ~$25 |
| **Mailgun (Flex)** | 100/day | $1.00/1K | $1.00 | ~$75-90 |
| **Resend** | 3,000/mo (100/day) | $20/mo (50k) | **$0.40** ($0.90 overage) | **$35-90** |
| **SendGrid** | none (retired 2025) | $19.95/mo | ~$0.40-0.90 | ~$90 |
| **Postmark** | 100/mo | $15/mo (10k) | **$1.50** | ~$126-180 |
| **Mailjet** | 200/day | $17/mo | ~$0.35-0.50 | ~$105 |
| **Brevo** | 300/day | $9/mo | ~$0.35 | ~$65-80 |

### Marketing / platform providers

| Provider | Free tier | Entry | Model | 10k contacts/month |
|---|---|---|---|---|
| **Mailchimp** | 500 contacts, 1,000 sends | ~$13/mo | contacts + sends | ~$100-135 |
| **Klaviyo** | 250 contacts, 500 sends | ~$20/mo | **active profiles** | ~$150-200 |
| **ActiveCampaign** | no free plan (trial) | $15/mo (1k contacts) | contacts | ~$79-149 |
| **Brevo** | 300 emails/day | $9/mo | volume | ~$25-45 |
| **Resend marketing** | 1,000 contacts | $40/mo (5k) | contacts | ~$80 |
| **MailerLite** | 1,000 subs | $10/mo | subscribers | ~$40-60 |

**Note:** marketing pricing **contacts par** hota hai, emails par nahi. 10,000 contacts
ko mahine mein 1 email bhejo ya 10 — price same. Isliye marketing ka gross margin
transactional se **zyada** hota hai (kam sends, zyada paisa) — jab tak log unsubscribe
na karein.

---

## 4. Resend — aapka sabse seedha competitor (aur uska economics)

Resend transactional-first developer API hai, React Email ke saath. Aap jaisa hi product,
acha funded.

| Plan | Price | Emails | $/1K |
|---|---|---|---|
| Free | $0 | 3,000 (100/day cap) | — |
| Pro | $20 | 50,000 | $0.40 |
| Pro | $35 | 100,000 | $0.35 |
| Scale | $90 | 100,000 | $0.90 |
| Scale | $350 | 500,000 | $0.70 |
| Scale | $1,150 | 2,500,000 | $0.46 |

**Resend ka unit economics (mere calculate):**

```
Pro $20 plan, 50,000 emails
  Revenue:                    $20.00
  SES cost (50k × $0.10/1K):  -$5.00
  Gross profit:               $15.00   → 75% gross margin
```

Bilkul Klaviyo jitna gross margin. **Email bhejne par 75% margin milta hai** — ye
industry-standard hai, aur yahi aapke liye bhi possible hai.

**Magar** Resend ka **overage $0.90/1K** hai — matlab 60,000 emails bhejne par
$20 + $9 = $29 (effective $0.48/1K). Ye deliberately aggressive hai: log ko next tier
par upgrade karne ke liye majboor karta hai. Ye **pricing psychology** hai, cost nahi.

Resend **loss-making** hone ki poori sambhavna hai (VC-funded, free tier 3,000/mo,
10 requests/sec free par). Revenue estimates ~$5-15M (⚠️ estimate). Matlab: **market
share kharidne ke liye paisa jala rahe hain.** Aap unse price war nahi kar sakte —
unke paas $XXM funding hai, aapke paas VPS.

---

## 5. Losses — ESP business kahan marta hai

Ye woh baatein hain jo koi landing page par nahi likhta.

| Loss driver | Kitna dard | Kaise bachna |
|---|---|---|
| **Churn 3-5%/month** SMB segment mein | 100 customers → 1 saal mein 40-50 bache (retention ke bina) | ARPU badhao, switching cost banao (templates, logs, domains) |
| **Free tier ka support** | 1 free user ka ticket = aapka 20 min; $0 revenue | free tier par **email-only support**, community docs |
| **Deliverability incident** | ek customer ka 20% bounce → **poora account pause** → sab customers churn | per-tenant isolation (SES Tenants), auto-pause, verified-domain-only |
| **Abuse** | free signup → spam → AWS ban | card verification, manual review, velocity limits |
| **Price war** | SES $0.10, ZeptoMail $0.25 — koi bhi $0.15 par aa sakta hai | price par mat laro; DX/latency/support par laro |
| **Refund/chargeback** | 2-5% transactions | card verification, clear ToS |
| **Cold email creep** | customers "marketing" bhejna shuru karein → reputation ruin | AUP enforcement + manual review |
| **Compliance** (DPDP, GDPR) | legal cost, audit | consent ledger, data residency clarity |

### Churn ka asli hisaab

```
100 customers, 4% monthly churn, 5% monthly new logo growth
  Month 12: ~101 customers  → barely flat
  Churn 2% + 8% growth → 190 customers
```
Email SaaS mein **churn control > acquisition**. Isliye "100/day free" jaisi schemes
se pehle churn ka jawab socho: customer 3 mahine baad kyun nahi jayega?

---

## 6. Aapke (Mailflow) liye numbers — realistic scenarios

Assumption: SES à la carte $0.10/1K, app aapke VPS par, Neon free tier, INR pricing.

### Scenario A — "Volume game" (Brevo route)

| | Value |
|---|---|
| Plan | ₹499/month, 50,000 emails (₹0.01/email ≈ $0.12/1K) |
| Revenue | ₹499 |
| SES cost (50k) | ₹440 (~$5) |
| **Gross profit** | **₹59 (12%)** ← bahut patla |
| 100 customers | ₹49,900 revenue, ₹44,000 SES, **₹5,900 gross** |

**Nateeja:** 12% margin par support cost nahi niklega. Ek ticket = pura mahine ka profit.
**Volume game bina funding nahi jeeta ja sakta.**

### Scenario B — "Value game" (Postmark/Resend route)

| | Value |
|---|---|
| Plan | ₹1,499/month, 25,000 emails (₹0.06/email ≈ $0.72/1K) |
| Revenue | ₹1,499 |
| SES cost (25k) | ₹220 |
| **Gross profit** | **₹1,279 (85%)** |
| 100 customers | ₹1,49,900 revenue, ₹22,000 SES, **₹1,27,900 gross** |

**Nateeja:** support cost nikal jayega, aur growth ke liye paisa bachega. Ye Postmark
ka model hai — $1.50/1K charge karo, deliverability aur support bech do.

### Scenario C — "Free tier trap" (kya nahi karna)

| | Value |
|---|---|
| 1,000 free users × 3,000 emails/mo | 3,000,000 emails |
| SES cost | **₹26,400/month (~$300)** |
| Revenue | **₹0** |
| Support (1% ticket rate × 10 min) | **~166 hours/month** = 1 full-time person |

**Yahi wo jagah hai jahan ESPs marte hain.** Free tier ka kharcha emails nahi —
**support** hai. Resend 3,000/mo free de sakta hai kyunki uske paas funding hai.

---

## 7. Aapka competitive position — honest assessment

| Aapke against | Wo jeette hain | Aap jeet sakte ho |
|---|---|---|
| **Resend** | DX (React Email), brand, funding, docs | INR billing + Indian support + latency se India |
| **ZeptoMail** | $0.25/1K (aapse sasta), Zoho ecosystem | developer API, better dashboard, latency metric |
| **Amazon SES** | $0.10/1K, unlimited scale | aap "SES ka dard" bech rahe ho (setup, warm-up, dashboard) |
| **Brevo/Mailchimp** | 600k/800k customers, brand | transactional-only focus, speed, no bloat |
| **Postmark** | deliverability reputation (16 saal) | India pricing (Postmark $1.50/1K = ₹125/1K) |

**Aapka real niche:** India-based SaaS/dev teams, transactional-only, INR billing,
local support, aur **delivery latency** par focus. Ye chhota hai — magar defendable hai.

### Pricing benchmark jo aapke liye kaam karta hai

| Plan | Price | Emails | $/1K | Margin |
|---|---|---|---|---|
| Free | ₹0 | 500/month (sirf verified link) | — | onboarding |
| Starter | ₹499 | 10,000 | ~₹0.05 (≈$0.60/1K) | 83% |
| Growth | ₹1,499 | 40,000 | ~₹0.037 (≈$0.45/1K) | 78% |
| Scale | ₹3,999 | 150,000 | ~₹0.027 (≈$0.32/1K) | 69% |

Dhyan do: **jitna bada plan, utna kam margin** — ye normal hai. Magar jab tak 70%+
hai, theek hai. Scenario A (12%) mat karo.

---

## 8. Break-even — aapko kitne customers chahiye

Fixed cost (aapka setup):

| Item | Monthly |
|---|---|
| VPS | ₹1,500 |
| Domain + Neon | ₹500 (Neon free tier = ₹0) |
| Email validation API (baad mein) | ₹2,000 |
| **Total fixed** | **~₹4,000/month** |

| Plan mix | Break-even customers |
|---|---|
| ₹499 plan, 85% margin (₹424/customer) | **~10 customers** |
| ₹1,499 plan, 85% margin (₹1,279/customer) | **~4 customers** |
| Scenario A (₹59/customer) | **~68 customers** — aur support cost ke baad kabhi nahi |

**Yahi sabse bada sabak:** 10 customers ₹1,499 plan par = break-even. 68 customers
₹499 plan par = break-even se door. **Kam customers, zyada value.**

---

## 9. Sources

| Claim | Source |
|---|---|
| Klaviyo FY2025: revenue $1,234.0M, GM 75%, net loss $31.8M, 193k customers, NRR 110%, 2,368 employees | [Klaviyo 8-K/press release](https://www.businesswire.com/news/home/20260210069244/en/Klaviyo-Delivers-Outstanding-2025-Results-32-Revenue-Growth-Record-Fourth-Quarter-and-Raised-Fiscal-Year-2026-Outlook), [10-K summary](https://medicilist.com/company/klaviyo-inc-1835830) |
| Brevo: >€200M ARR, 600k customers, double-digit EBITDA margin, unicorn Dec 2025 | [Brevo/PR Newswire](https://www.prnewswire.com/news-releases/brevo-europes-leading-customer-engagement-platform-becomes-a-unicorn-following-a-new-500-million-funding-round-302632991.html) |
| Mailchimp: $800M CY2020 revenue, 800k paid customers, 13M total users, $12B Intuit acquisition | [Intuit investor call](https://investors.intuit.com/_assets/_64f3415e6601d7a94d9a083d8f6622dc/intuit/db/919/9561/file/Investor-Call-Script-9-13-21-PM.pdf) |
| ActiveCampaign: $250M+ ARR, 180k+ customers, $3B valuation, $360M raised | [Growth in Reverse](https://www.growthunhinged.com/p/gtm-strategies-active-campaign) |
| Resend pricing (free 3k, Pro $20/50k, overage $0.90/1K, Scale up to $1,150/2.5M) | [smtpedia](https://smtpedia.com/platforms/resend/pricing/), [superdupr](https://superdupr.com/blog/resend-pricing) |
| Postmark pricing ($15/10k, overage $1.80→$1.20/1K, ActiveCampaign-owned) | [saaspricepulse](https://www.saaspricepulse.com/tools/postmark), [devtoollab](https://devtoollab.com/blog/best-email-api-providers) |
| Mailgun pricing (Flex $1.00/1K, Foundation $35/50k) | [sequenzy](https://www.sequenzy.com/blog/best-pay-per-email-platforms) |
| ZeptoMail $2.50 per 10,000 credit (₹150), first credit free, 6-month validity | [reachkit](https://reachkit.ai/directory/tools/zeptomail) |
| SES $0.10/1K à la carte; Essentials $0.16 | [AWS SES pricing](https://aws.amazon.com/ses/pricing/) |
| SES/Elastic Email cheapest at scale; provider cost ladder | [sequenzy](https://www.sequenzy.com/blog/best-transactional-email-services) |

⚠️ **Estimates (not verified):** Resend revenue/customers, Mailchimp current revenue
($1.27B vs $180M estimates conflict), Brevo exact ARR ($200-232M range).
Private companies' profit figures are **never** public — treat any such number as a guess.
