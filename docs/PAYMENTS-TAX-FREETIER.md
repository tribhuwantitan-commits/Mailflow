# Payments, GST, aur free tier — concrete answers

Date: Nov 2026. Ye doc tumhare 5 sawalon ke jawab hai, numbers ke saath.

---

## 1. À la carte — ✅ confirm, aur ek zaroori step

`$0.10/1K` tabhi milega jab account **à la carte** par ho. Naya account (jo 21 July 2026
ke baad bana hai) default **Essentials ($0.16/1K)** par hota hai.

**Aaj hi karo:** SES console → **Pricing plan** → agar "Essentials" dikhe → **Cancel plan**.
Agar tumne Essentials khud choose nahi kiya tha to cancellation **turant** effective hogi.

Verify karne ka tareeka (baad mein bill se bhi pata chalega):

| Check | Kaise |
|---|---|
| Plan name | Console → Pricing plan → "Plan" field khaali / à la carte |
| Cost per 1,000 | CloudWatch → SES **Sent** vs Billing → SES charge (1,000 emails = $0.10) |
| Quota | `python -m app.scripts.check_ses` (200/day = sandbox, alag baat hai) |

⚠️ Note: à la carte par **Virtual Deliverability Manager** included nahi hai (wo $0.07/1K
alag). Tumhe VDM nahi chahiye — theek hai. Magar dashboard ke liye events (SNS/SQS)
**free** hain, un par koi asar nahi.

---

## 2. Payment gateway — Indian + international, sabse sasta

### Published rates (Nov 2026)

| Gateway | UPI (domestic) | Domestic cards | International cards | Setup/monthly |
|---|---|---|---|---|
| **Razorpay** | **0%** (RBI mandate) | 2% + GST | 3% + GST (+forex) | ₹0 |
| **Cashfree** | as per law (usually 0%) | **1.95%** + GST | **2.99%** (Amex 2.95%) | ₹0 |
| **PayU** | — | ~2% | 3% | ₹0 |
| **Stripe India** | — | 2% (India-issued) | 3% | **invite-only** |
| **Paddle / Lemon Squeezy** (MoR) | — | **5% + $0.50** | same +1.5% | $0 |

Plus: **18% GST gateway fee par bhi lagta hai** (fee ka GST, service ka nahi).

### Sabse sasta combination (meri recommendation)

| Customer | Gateway | Effective fee |
|---|---|---|
| **Indian, UPI se** | Razorpay / Cashfree UPI | **0%** ← sasta nahi ho sakta |
| **Indian, card se** | **Cashfree 1.95%** | 1.95% + GST ≈ **2.30%** |
| **International (USD)** | Razorpay 3% **ya** Cashfree 2.99% | ≈ **3.5%** (with GST+forex) |
| **Global, VAT nahi handle karna** | Paddle/LS 5% + $0.50 | ~7-15% (chhoti sale par) |

**Razorpay + Cashfree dono** rakho (dono free setup, dono UPI): UPI 0%, cards Cashfree
se, international Razorpay se. Ek hi gateway chahiye to **Razorpay** (UPI 0% + 130
currencies), magar card par Cashfree 0.05% sasta hai — volume par farq padega.

### ⚠️ $5 plan par fixed fee ka trap

```
MoR (Paddle/LS): 5% + $0.50 on $5  = $0.75  → 15% fee ❌
Razorpay intl:   3% + GST on $5    = $0.18  → 3.5% fee ✅
Razorpay UPI:    0% on ₹430        = ₹0     → 0% fee ✅✅
```

**Isliye:** $5 plan **UPI/card par hi** becho, MoR par nahi. MoR sirf tab lo jab
tumhe EU/UK/AU ka VAT file karna hi na ho (aur tab minimum plan $20+ rakho, warna
`$0.50` fixed fee kha jayega).

### Internation ke liye ek extra requirement (GST export proof)

International payment aane par bank se **FIRC / eFIRA** lena padega (foreign inward
remittance certificate). Ye GST export prove karne ke liye chahiye (section 3).
Razorpay/Cashfree ke export accounts ye dete hain — normal current account se bhi milta hai.

---

## 3. GST — tumhara ₹20 lakh wala point **sahi** hai (ek correction ke saath)

### Threshold — sahi number

| Cheez | Threshold |
|---|---|
| **Services** (tumhara SaaS) | **₹20 lakh** aggregate turnover |
| Special category states | ₹10 lakh |
| **Goods** | ₹40 lakh |
| ⚠️ Tumne "12 lakh" bhi bola — **wo GST threshold nahi hai.** ₹12 lakh ek purana/confused number hai. **Services ke liye ₹20 lakh.** |

Turnover = **billings**, profit nahi. Export bhi count hota hai.

### Tumhare case mein 3 phases

| Phase | Turnover | GST | Kya karna hai |
|---|---|---|---|
| **1. Abhi** | ₹0 - 20L | **koi GST nahi** | register mat karo, GST charge mat karo, sirf income tax (ITR) |
| **2. 20L cross** | ₹20L+ | **Indian customers: 18%**, **foreign: 0% (zero-rated)** | 30 din mein register, **LUT file karo (April mein, har saal)** |
| **3. Registered + export** | — | foreign par 0%, ITC refund le sakte ho | GSTR-1 Table 6A, FIRC, RFD-01 |

### Sabse important: **Indian aur foreign customer ka GST alag hai**

```
Indian customer  → 18% GST (registered hone ke baad)
Foreign customer → 0% GST (zero-rated export, LUT ke saath)
```

Isliye **GST price mein include mat karo**. Do price rakho:

| Plan | India (INR, GST extra) | International (USD, ex-tax) |
|---|---|---|
| Starter | **₹499 + 18% GST = ₹589** | **$5.00** |
| Growth | **₹999 + GST = ₹1,179** | **$10.00** |
| Pro | **₹1,999 + GST = ₹2,359** | **$20.00** |
| Business | **₹3,499 + GST = ₹4,129** | **$35.00** |

(Agar tum GST-inclusive likhte ho to threshold cross hone par **18% tumhari jeb se**
jayega jab tak price na badhao — isliye "exclusive" hi likho, aur landing page par
likho "GST extra where applicable". Tumne kaha revenue 12L se kam rahega — us haal
mein GST hi nahi lagega, to ye issue aaj nahi hai. **Magar ₹20L cross hote hi ye
structure chahiye**, isliye abhi se exclusive likho.)

### Ek warning: 2 business, 2 different treatment

| Customer | Tum kya ho | Unka kya | GST |
|---|---|---|---|
| Indian company (registered) | supplier | buyer | 18% (unko ITC milega) |
| Indian individual | supplier | consumer | 18% (koi ITC nahi) |
| Foreign company | exporter | — | 0% (LUT) |
| Foreign individual | exporter | — | 0% (LUT) |

Foreign **individual** ko bhi export mana jata hai — LUT chahiye. Aur agar tum LUT
file nahi karte, to export par IGST + 18% interest lag sakta hai. **Har April mein
LUT renew** karna hota hai (RFD-11).

---

## 4. Jo tumne nahi samjha — "GST + gateway 20% kha jaate hain"

Chhota example. Tumhara **$5 plan**, Indian customer, aur tum GST **inclusive** likhte ho:

```
Customer pays:                  ₹499  (GST included)
GST 18% (sarkar ka):           −₹76
Gateway 2% (+GST on fee):      −₹12
SES (5,000 emails):            −₹44
Support:                       −₹30
                               -----
Tumhare paas bachta hai:        ₹337   → 68% (90% nahi)
```

Wahi sale agar tum **GST exclusive** likhte ho:

```
Customer pays:                  ₹499 + ₹90 GST = ₹589
GST (sarkar ko pass):          −₹90
Gateway 2%:                    −₹12
SES:                           −₹44
Support:                       −₹30
                               -----
Tumhare paas:                   ₹413   → 83%
```

**Farq ₹76 per sale.** 100 customers = **₹7,600/month** — jo tumhara pura VPS +
support kharid leta hai.

### Aur agar customer **foreign** hai

```
Customer pays:                  $5.00
GST:                            $0  (zero-rated export)
Gateway 3%:                    −$0.18
SES (5,000):                   −$0.50
Support:                       −$0.20
                               -----
Tumhare paas:                   $4.12  → 82% ✅
```

**Sabak:** foreign customer par GST ka **koi** asar nahi. Indian customer par 18% —
aur wo customer ko dikhna chahiye, tumhari jeb se nahi jana chahiye.

### Income tax (GST nahi)

| Regime | Kab fayda | Effective |
|---|---|---|
| **44ADA** (presumptive, professional) | services, ₹50L tak | 50% deemed income → ₹20L revenue par ₹10L taxable |
| **44AD** (presumptive, business) | ₹2-3 crore (with digital receipts) | 6-8% deemed |
| Normal (books) | expenses zyada | — |

⚠️ Ye tax advice nahi hai — CA se confirm karo. Magar **GST aur income tax do alag
cheezein hain** — GST ₹20L par lagta hai, income tax pehle rupee se (basic exemption
limit tak nil).

---

## 5. Free tier — sab dete hain, magar **kitna** dete hain wo dekho

Tumhara dar sahi hai: "free nahi dunga to customer kahan se aayega". Magar tumhara
plan **competitors se zyada udaar** hai.

### Competitors ka free tier (Nov 2026)

| Provider | Free tier | Domain chahiye? | Card chahiye? |
|---|---|---|---|
| **Resend** | 3,000/mo (100/day) | 1 domain verify | ❌ |
| **Postmark** | **100/mo** (dev only) | — | ❌ |
| **Mailgun** | 100/day (~3,000/mo) | ✅ | ❌ |
| **Brevo** | 300/day (~9,000/mo) | ❌ | ❌ |
| **Mailjet** | 200/day | ❌ | ❌ |
| **SendGrid** | **none** (retired 2025) | — | — |
| **Amazon SES** | **none** (credits only) | — | — |
| **ZeptoMail** | 10,000 one-time, **6 months** expire | ✅ | ❌ |
| **Mailchimp** | 500 contacts, 1,000 sends | ❌ | ❌ |

### Tumhara plan vs Resend

| | Tumhara | Resend |
|---|---|---|
| Verified domain | **50/day = 1,500/mo** | 100/day = 3,000/mo |
| Card verified | **100/day = 3,000/mo** | (no such tier) |
| Koi gate nahi | ❌ | 100/day |

**Tumhari free tier Resend se chhoti hai** (1,500 vs 3,000) — aur **domain verify
mangti hai**, Resend bhi mangta hai. To tum **zyada udaar nahi** ho. Achhi khabar.

### Magar ek asli problem hai: **activation**, generosity nahi

Tumhare free tier par pehla step = "domain verify karo". Naye user ka 60-70% wahin
chala jayega. Aur jo activate nahi hua, wo **kabhi** pay nahi karega.

**Fix (Resend ka trick):**

| Mode | Requirement | Limit | Kaam |
|---|---|---|---|
| **Sandbox** | koi nahi (signup only) | **20/day, sirf apne verified email par** | user product dekh leta hai |
| **Domain** | DKIM verify | 50/day, kisi ko bhi | real sending |
| **Card** | ₹2 auth | 100/day | serious user |

Sandbox mode mein customer **khud ko** hi bhej sakta hai — iska abuse surface **zero**
hai (spam karne ka koi rasta nahi), magar activation 35% → **70%** ho jata hai.

### Free tier ka asli cost — aur ise sasta kaise rakhein

```
1,000 free users × 1,500 emails × 40% utilization = 600,000 emails/month
SES cost = $60  (~₹5,300)
```
```
5,000 free users = 3,000,000 emails = $300/month  (~₹26,500)
```

5,000 free users par **$300/month** — ye tumhara sabse bada single cost banega.
Control (mitigation, free tier band karne ki zaroorat nahi):

| Control | Kya | Bachat |
|---|---|---|
| **Dormancy reclaim** | 30 din koi send nahi → 10/day | 40-50% |
| **Sandbox-first onboarding** | pehle 7 din 20/day, apne email par | 20% |
| **Per-recipient cap** | ek recipient ko 10/day | OTP bombing rok |
| **Temp-mail block default ON** | bounce kam → SES cost kam | 5-10% |
| **Domain cap** | free tier par 1 domain | abuse rok |
| **Card tier sirf 100/day** | 100/day ka misuse mehnga | — |

Realistic: 1,000 free users ka cost **$60 → $30-35/month**.

### Free tier dene ka faisla — economics

3% conversion par:

```
1,000 free users → 30 paid
30 paid × ARPU $19.30 = $579/month revenue
Free tier cost = -$60/month (ya -$30 optimized)
```
```
Conversion 2% → 20 paid → $386 revenue, cost $60  → still profitable
Conversion 1% → 10 paid → $193 revenue, cost $60  → still fine
```

**Free tier viable hai — jab tak conversion 1%+ ho aur activation kaam kare.**
Resend ke paas 3,000/mo free hai aur wo bhi funded hai; tumhare paas 1,500/mo hai.

### Meri recommendation — free tier **rakho**, magar aise

| | Free (sandbox) | Free (domain) | Free (card) |
|---|---|---|---|
| Emails/mo | 600 (20/day) | **1,500** (50/day) | **3,000** (100/day) |
| Kaun | signup | domain verified | card/UPI verified |
| Sending | sirf apne email par | kisi ko bhi | kisi ko bhi |
| Domain | 0 | 1 | 1 |
| Logs | 1 day | 3 din | 7 din |
| Expiry | — | — | — |
| Card | — | — | ₹2 refundable |

**Free tier kabhi expire nahi karna chahiye** — kyunki wo tumhara word-of-mouth engine
hai. Uski jagah **volume** control karo (1,500/mo = 18,000/year, enough for a side project,
SES cost = $1.80/year per user).

### Ek aakhri baat — free user ko **paise dene ka rasta** dikhao, har mahine

"Free forever" wale users ka ek hi kaam hai: **upgrade ka reason dekhna**.
Isliye free tier par bhi wo metrics dikhao jo unhe upgrade karne par majboor karein:

- "Aapne 1,430 / 1,500 emails use kiye — 96%"
- "3 emails aise hain jo boost ho sakte the" (nahi — ye marketing hai)
- Latency, delivery rate, bounce warnings
- "Custom domain + 100/day → ₹2 card verify"

**Email me har mahine** usage summary bhejo (aapki apni service se — dogfooding bhi ho jayega).

---

## 6. Final check-list

| # | Kaam | Status |
|---|---|---|
| 1 | SES **à la carte** confirm (Cancel plan agar Essentials) | ⏳ tumhara |
| 2 | **Razorpay** account (UPI 0%, cards 2%, intl 3%) | ⏳ |
| 3 | **Cashfree** account (cards 1.95%, intl 2.99%) — optional | ⏳ |
| 4 | Pricing **GST-exclusive** likho, "GST extra where applicable" | ⏳ design |
| 5 | ₹20L turnover par CA se GST + LUT (April) baat karo | ⏳ later |
| 6 | Free tier: sandbox 600 / domain 1,500 / card 3,000 | ⏳ plan |
| 7 | Dormancy reclaim + per-recipient cap implement | ⏳ Phase 7b |
