# Marketing plan — pehle 700 customer kahan se aayenge

Do bucket hain: **$400 infra** (8 mahine) aur **$1,200 email** (email mein kabhi khatam
nahi hoga). Aapke paas **paisa nahi hai marketing ke liye**. To yahi sach hai:

> **$0 budget marketing = 6 mahine, roz 1-2 ghante, 3 channel.**
> Isse 300-800 signups aate hain. 3% conversion par **9-24 paid**.
> Jo 8-mahine ka plan hai, usme **fit ho jata hai**.

Paid ads, influencers, SEO content farm — **in par ek rupya mat lagao.** Wo pre-revenue
par sirf paisa khaate hain.

---

## 0. Pehle: product ki positioning tay karo

Marketing se pehle ek line chahiye. Bina uske har jagah "email API" likhoge aur koi
respond nahi karega.

| | |
|---|---|
| **Kaun** | Indian SaaS/dev shops, 1-20 log |
| **Dard** | SendGrid/Mailgun ka bill dollar mein, card chahiye, support US timezone, aur deliverability ka koi bharosa nahi |
| **Aap** | ₹799 se shuru, UPI se pay, Indian support, apna domain verify, SES ke through world-class deliverability |
| **Ek line** | *"Transactional email API for Indian SaaS — ₹799/month, UPI, no dollar card."* |

**Ye teen cheezein aapke paas hain jo Resend/Postmark ke paas nahi:**
1. **INR pricing + UPI** (unke paas card-only, dollar)
2. **GST invoice** (Indian company ko chahiye, unke paas nahi)
3. **IST support** (aap reply kar sakte ho, wo 24 ghante lagate hain)

**Ye teen cheezein unke paas hain jo aapke paas nahi (abhi):**
1. Brand trust
2. Docs/guides
3. Uptime history

Isliye **#1 se lead karo**, #3 se trust banao.

---

## 1. Channel 1 — Developer communities (sabse zyada ROI)

Aapka customer wahan already hai aur wahan **paisa nahi lagta**.

### Kahan

| Jagah | Kaise | Effort |
|---|---|---|
| **r/developersIndia** | Helpful answers, phir ek post | 2-3 ghante/saptah |
| **r/SaaS**, r/indiehackers | Build-in-public posts | 1-2 ghante |
| **Hacker News** (Show HN) | Ek baar, achhe se | 4 ghante, ek baar |
| **IndieHackers.com** | Milestone posts | 1 ghanta |
| **Discord/Slack** — Indian dev servers | Genuinely help karo | 2 ghante |
| **Twitter/X #buildinpublic** | Roz 1 tweet | 10 min/din |

### Rule jo todna mat

> **Har post ka 90% madad hona chahiye, 10% product.**
>
> "Maine email API banaya, try karo" = **0 signups + ban.**
> "SendGrid se migrate karte waqt DKIM par 3 ghante gaye, ye checklist bachayegi [link]" = **signups.**

### 8 hafte ka content calendar

| Hafta | Kya post karo | Kahan |
|---|---|---|
| 1 | "Email deliverability checklist for Indian SaaS (SPF/DKIM/DMARC)" | r/developersIndia |
| 2 | "SendGrid vs Mailgun vs SES: INR comparison table" | blog + Reddit |
| 3 | "Maine apna email API banaya — 6 mahine ka cost breakdown" | IndieHackers |
| 4 | "Bulk email bhejte waqt bounce rate 5% cross — kya kare" | r/SaaS |
| 5 | **Show HN: MailFlow — INR-priced transactional email API** | HN |
| 6 | "Why we self-host the queue instead of Redis" (technical) | r/programming |
| 7 | Free tool: **SPF/DKIM/DMARC checker** | apni site |
| 8 | "Pehle 10 customers se kya seekha" | IndieHackers |

**Hafta 7 wala tool sabse zyada traffic deta hai** — free utility, koi signup nahi,
aur wo log **aapke domain par** aate hain.

---

## 2. Channel 2 — Direct outreach (sabse zyada conversion)

Reddit se **signups** aate hain. **Paid customers** direct outreach se aate hain.

### Kaun target kare

| Signal | Kahan dhundho | Kyun |
|---|---|---|
| Indian SaaS with email features | Product Hunt India, local directories | Unko already email chahiye |
| GitHub repos with `sendgrid`/`nodemailer`/`resend` in code | GitHub search | Wo **abhi** pay kar rahe hain |
| Job posts: "sendgrid", "email deliverability" | LinkedIn, Naukri | Active dard |
| Indie hackers with launched products | IndieHackers, X | Decision maker khud hai |

### GitHub search — ye sabse smart move hai

```
language:python sendgrid
language:javascript @sendgrid/mail
"resend" filename:package.json
language:typescript mailgun
```

**Ye log already email bhej rahe hain, already paisa de rahe hain.** Ek personalised
email ka conversion 10-20x hota hai cold list se.

### Outreach template (chodna mat, personalise karo)

```
Subject: aapka SendGrid bill (ek chhota suggestion)

Hi <naam>,

<aapke product> dekha — <specific cheez> achha laga.

Aap <sendgrid/resend/mailgun> use kar rahe ho, monthly ~$<X>.
Maine MailFlow banaya hai — same API shape, INR pricing, UPI,
GST invoice, SES ke through delivery (same infrastructure
jo Amazon khud use karta hai).

₹799/month mein 30,000 emails. Migration 10 minute ka hai —
API key badlo, domain verify karo, done.

Agar useful lage to free tier (1,000/month) hai, card nahi chahiye.
Agar nahi, koi baat nahi — bas ye ek line padh lo ki aap
SPF/DKIM set kar liye ho, kai log bhool jaate hain.

<naam>
```

**Kyun ye kaam karta hai:** aap unhe kuch **free advice** de rahe ho (DKIM check),
specific ho, aur **price Hindi/INR mein** hai jo unke CFO ko samajh aata hai.

**Volume:** roz 10, hafte mein 50. **2-4% reply**, 1-2% conversion.
8 hafte = 400 outreach → **4-8 paid customers.**

---

## 3. Channel 3 — Free tools (compound karte hain)

Ye ek baar banao, saalon traffic dete hain.

| Tool | Effort | Kyun kaam karta hai |
|---|---|---|
| **SPF/DKIM/DMARC checker** | 1 din | Log roz search karte hain, aur wo **aapke domain par** aate hain |
| **Bounce rate calculator** | 2 ghante | "Mera bounce rate 3% hai, theek hai?" |
| **SES vs SendGrid vs Resend cost calculator** | 4 ghante | Purchase decision ke waqt |
| **Email HTML tester** | 2 din | Bada, magar bahut traffic |

**Sabse pehla: DMARC checker.** Wo ek keyword hai jise har Indian dev ek baar Google
karta hai, aur 90% tools English/US-centric hain.

**Har tool par ek line:** *"Ye tool MailFlow banata hai — ₹799/month email API."*
Koi popup nahi, koi email capture nahi. **Sirf ek line.**

---

## 4. Kya **nahi** karna

| ❌ | Kyun |
|---|---|
| **Paid ads** (Google/Meta) | ₹20-50 per click, 2% conversion = ₹2,500 per customer. Aapka plan ₹799 hai. |
| **Influencer marketing** | $100-500, ek din ka spike, zero retention |
| **Cold email to 10,000 people** | Aap **email company** ho. Spam karke reputation barbaad karna sabse bura move. |
| **SEO blog farm** | 6-12 mahine lagte hain, tab tak credits khatam |
| **"Growth hacking"** | Pre-revenue par ye distraction hai |
| **Product Hunt launch abhi** | PH se traffic aata hai, conversion 0.5%. Pehle 20 customers manually laao, phir PH. |

> **Cold email sabse bada trap hai.** Aap email deliverability bech rahe ho — agar aap
> khud spam bhejoge to aapki apni reputation jayegi. **Kभी nahi.**

---

## 5. 8-hafte ka plan — hafte mein 6-8 ghante

| Hafta | Focus | Target |
|---|---|---|
| 1 | Positioning + landing page + docs | Live |
| 2 | DMARC checker tool + Reddit post 1 | 20 signups |
| 3 | GitHub search + 25 outreach | 2 replies |
| 4 | Blog: SES vs SendGrid INR + Reddit post 2 | 30 signups |
| 5 | 50 outreach + Show HN | 50 signups |
| 6 | Case study: pehla customer | 1 testimonial |
| 7 | Reddit post 3 + 25 outreach | 30 signups |
| 8 | "Pehle 10 customers" post + pricing review | — |

**Cumulative target: 150-300 signups, 5-10 paid.**

> Ye 3% conversion se **kam** hai — kyunki shuru mein conversion hamesha kam hoti hai
> (product chhota hai, trust nahi hai). **Month 4-6 mein conversion 3% ho jati hai.**

---

## 6. ICP — kis ko sabse pehle target karo

**Sabse achha customer:**

| Signal | Kyun |
|---|---|
| Indian SaaS, 2-20 log | Decision fast, price sensitive |
| Already email bhej rahe hain (SendGrid/Resend/Mailgun) | **Dard already hai**, aap solve kar rahe ho |
| 30K-150K emails/month | **Aapka Growth/Scale plan** fit hota hai |
| Founder khud technical hai | Wo khud integrate kar lega, aapko docs chahiye bas |

**Sabse bura customer (abhi mat lo):**

| Signal | Kyun |
|---|---|
| Enterprise (500+ log) | Sales cycle 6 mahine, trust nahi hai |
| Marketing bulk (1 lakh+ per blast) | Deliverability risk, aapka guard rails nahi |
| Free-only user with 50/day | Cost $0.15/mo, revenue $0. **1,000 tak theek, phir oopar dekhna** |

---

## 7. Conversion ko 3% se 6% kaise kare

Benchmark kehta hai: **activation theek ho to conversion 4.1x badhta hai.**

### Activation = pehla email successfully delivered

Aapka #1 metric **signups nahi, "first delivered email" hai.**

| Step | Aaj ka friction | Fix |
|---|---|---|
| Signup | ? | Email + password, bas. **Card nahi.** |
| Domain verify | 3 CNAME DNS mein daalne padte hain | Copy-paste box, har record ke saath "Copy" button |
| API key | ? | Signup ke baad **turant** dikhao |
| Pehla send | SDK/curl | **"Send your first email" button** dashboard mein — raw curl copy karke |
| Delivery confirm | Dashboard dekho | Onboarding checklist: 4 items, tick hote jayein |

**Sabse bada lever:** domain verify ke baad **ek test email button** jo turant bheje.
Agar user 5 minute mein delivered email dekh leta hai, wo convert karta hai.

### Pricing page par

| Kya | Kyun |
|---|---|
| **INR + USD dono** | Indian buyer INR dekhta hai |
| **"No credit card"** bada likho | Signup friction hatata hai |
| **Per-1,000 comparison** table | Resend $0.40, Postmark $1.50, **aap $0.30** |
| **GST invoice** ka zikr | Indian company ke liye deal-breaker/closer |

---

## 8. Free tier 50/day — marketing tool ya cost centre?

Aapne 50/day + 1,000/month rakha. **Sahi hai**, magar ek condition:

> **Free tier tab tak accha hai jab tak wo word-of-mouth la raha ho.**

| Mahine | Free tenants | Free cost/mo | Verdict |
|---|---|---|---|
| 1-3 | < 100 | $15 | ✅ marketing |
| 4-6 | 300-500 | $45-75 | ✅ agar conversion 3% hai |
| **7+** | **700+** | **$105** | ⚠️ **20/day kar do** |

**Rule: jab free tenants 500 cross karein aur paid < 15 ho, free quota 20/day karo.**
Wo ek hi change conversion 2x karta hai **aur** cost 60% girata hai.

**Aur ek cheez:** free users ko **email karo** jab wo 80% quota use karein:

```
Subject: aap apne free plan ke 80% par ho

Aap is mahine 800/1,000 emails bhej chuke ho.
Starter plan ₹799/month mein 30,000 — 30x zyada.

Agar aap abhi upgrade karo to pehla mahina ₹399 (50% off).
```

**Ye email sabse zyada convert karta hai.** Wo already product use kar rahe hain.

---

## 9. Numbers — realistic

| | 3 mahine | 6 mahine | 8 mahine |
|---|---|---|---|
| Signups | 50-80 | 200-350 | **400-700** |
| Paid (3%) | 1-2 | 6-10 | **12-21** |
| MRR | $9-19 | $60-130 | **$150-350** |
| Chan. 1 (Reddit/HN) | 60% | 50% | 45% |
| Chan. 2 (outreach) | 20% | 30% | 35% |
| Chan. 3 (tools/SEO) | 20% | 20% | 20% |

Ye pehle wale month-by-month scenario se **thoda neeche** hai — kyunki wahan maine 700
tenants liye the. **Realistic beginner case: 400-700.**

**Aapke $1,600 credits us case mein bhi kaafi hain** (worst case $560 burn dekha tha).

---

## 10. Pehle 7 din

| Din | Kaam | Time |
|---|---|---|
| 1 | Landing page — ek heading, 3 bullets, pricing table, "Start free" | 3 ghante |
| 2 | Docs: quickstart (curl + Node), 1 page | 4 ghante |
| 3 | DMARC/SPF checker tool | 6 ghante |
| 4 | Reddit account warm-up (comments only, 0 promo) | 30 min |
| 5 | GitHub search — 100 repos list banao | 2 ghante |
| 6 | Pehla Reddit post (checklist, no promo) | 2 ghante |
| 7 | 10 personalised outreach | 2 ghante |

**Din 8 par aapke paas 3-5 signups honge.** Bas.

---

## 11. Ek page

| | |
|---|---|
| **Budget** | ₹0 |
| **Time** | 6-8 ghante/saptah, 6 mahine |
| **Positioning** | "Indian SaaS ke liye email API — ₹799, UPI, GST invoice" |
| **Channel 1** | Reddit/HN/IndieHackers — **90% madad, 10% product** |
| **Channel 2** | GitHub + cold outreach — **10/day, personalised** |
| **Channel 3** | Free tools (DMARC checker) — **compound** |
| **#1 metric** | **"first delivered email"**, signups nahi |
| **Free tier** | 50/day theek — **500 cross + paid <15 ho to 20/day** |
| **Kabhi nahi** | paid ads, cold email blast, influencer, SEO farm |
| **8-mahine realistic** | 400-700 signups, 12-21 paid, $150-350 MRR |
