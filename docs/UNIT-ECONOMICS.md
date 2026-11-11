# Unit Economics — asli cost per 1,000 emails

Date: Nov 2026. Owner's assumption: **$0.10 SES + $0.05 infra = $0.15 per 1,000**.
Ye document us assumption ko test karta hai. Verdict: **variable part sahi hai, fixed
part ka math galat hai** — aur us galti se tumhare top tiers loss mein ja sakte hain.

---

## 1. Pehle basic correction: fixed vs variable

| Cost | Type | Amount | Per-email badhta hai? |
|---|---|---|---|
| **SES sending** | **variable** | $0.10 / 1,000 | ✅ haan, linear |
| **SNS** (event publishing) | variable (mostly free) | 1M publishes/mo free, phir $0.50/M | ✅ |
| **SQS** (event queue) | variable (mostly free) | 1M requests/mo free, phir $0.40/M (~4 req/event) | ✅ |
| **VPS** | **FIXED** | ~$20/mo (₹1,500-1,700) | ❌ **nahi** |
| **Domain + SSL** | fixed | ~$1/mo | ❌ |
| **Neon Postgres** | fixed (free tier) | $0 → $19/mo at scale | ❌ |
| **SES dedicated IP** | fixed, optional | $15-25/mo | ❌ |

### Isliye "$0.05 per 1,000 infra" ek fixed assumption hai jo **sirf ek volume par** sach hai

```
VPS $20/month ÷ 1,000 emails  = $20.00 per 1,000   ← 1,000 emails bhejo to
VPS $20/month ÷ 100,000       = $0.20 per 1,000
VPS $20/month ÷ 340,000       = $0.059 per 1,000
VPS $20/month ÷ 1,000,000     = $0.020 per 1,000
```

**$0.05/1K tabhi sach hai jab platform par mahine ke ~3,40,000 emails ja rahe hon.**
Us se kam par tumhara cost **zyada** hai, zyada par **kam**.

---

## 2. Asli all-in cost per 1,000 — volume ke hisaab se

Formula: `cost/1K = $0.10 (SES) + ($20 VPS ÷ total_emails_in_thousands) + events`

| Total emails/month | SES | VPS share | SNS/SQS | **Total cost/1K** | Tumhara $0.15? |
|---|---|---|---|---|---|
| 10,000 | $1.00 | $2.00 | $0 | **$3.00** | ❌ 20x zyada |
| 50,000 | $5.00 | $0.40 | $0 | **$0.50** | ❌ 3.3x |
| 100,000 | $10.00 | $0.20 | $0 | **$0.30** | ❌ 2x |
| 250,000 | $25.00 | $0.08 | $0.01 | **$0.19** | ❌ 1.3x |
| **340,000** | $34.00 | $0.059 | $0.01 | **$0.169** | ⚠️ ~match |
| **400,000** | $40.00 | $0.050 | $0.01 | **$0.160** | ✅ match |
| 500,000 | $50.00 | $0.040 | $0.02 | **$0.15** | ✅ exact |
| 1,000,000 | $100.00 | $0.020 | $0.03 | **$0.13** | ✅ better |
| 3,380,000 | $338.00 | $0.006 | $0.02 | **$0.109** | ✅ 40% better |

**Nateeja:** tumhara $0.15/1K **safe but conservative** hai — jab volume 400k+/month
ho jaye. Us se pehle tum **zyada** kharch kar rahe ho, aur wo gap chhota nahi hai.

---

## 3. ⚠️ Sabse bada khatra: kam volume par top tiers **loss** mein jaate hain

Ye table dekho. Yahi wo baat hai jo koi pricing blog nahi batata.

### Platform volume = 100,000 emails/month (cost/1K = $0.30)

| Plan | Price | Emails | Cost | Profit | GM |
|---|---|---|---|---|---|
| $5 | 5,000 | $1.50 | $3.50 | 70% |
| $10 | 15,000 | $4.50 | $5.50 | 55% |
| $15 | 40,000 | $12.00 | $3.00 | 20% |
| $20 | 60,000 | $18.00 | $2.00 | **10%** |
| $25 | 75,000 | $22.50 | $2.50 | **10%** |
| $30 | 90,000 | $27.00 | $3.00 | **10%** |
| $40 | 120,000 | $36.00 | $4.00 | **10%** |
| **$50** | **150,000** | **$45.00** | **$5.00** | **10%** |

Ab ek hi customer ne 150k liya (baaki koi nahi):

| $50 | 150,000 | **$45.00** | $5.00 | 10% |
|---|---|---|---|---|
| **$40** | 120,000 | **$36.00** | $4.00 | 10% |

Aur agar **ek hi customer** $50 ka plan le aur platform volume 150k ho:

```
Revenue:      $50.00
SES:          $15.00
VPS (poora):  $20.00   ← ek customer par pura fixed cost
             --------
Profit:       $15.00   → 30%  (aur support/payment fees ke baad ~10%)
```

**Khatra:** pehla hi customer $50/150k plan le → wo tumhara **pura VPS** kha jayega.
Ye 30% margin support aur payment fees ke baad **zero** ho jata hai.

### Recommendation: launch par top tier cap karo

| Volume (platform-wide) | Safe to sell up to |
|---|---|
| < 100k emails/mo | **$10 plan (15,000)** max |
| 100k - 250k | **$20 plan (60,000)** |
| 250k - 500k | **$35 plan (130,000)** |
| 500k+ | $60 / $100 tiers |

Ya phir: top tiers ko **cost-plus** price karo current volume par:

```
floor_price = (emails / 1000) × (0.10 + infra_per_1K) × 1.30
```

At 100k volume (infra $0.20/1K): 150,000 emails ka floor = 150 × $0.30 × 1.3 = **$58.50**
→ isliye $50 ka 150k plan **floor se neeche** hai. Aaj mat becho.

---

## 4. ⚠️ Doosra bada khatra: Essentials vs à la carte

Tumne $0.10/1K maana hai — ye **à la carte** rate hai. Magar **naye accounts
21 July 2026 se Essentials par default** hote hain, jahan rate **$0.16/1K** hai.

Tumne plan cancel karne ki baat kahi thi, par confirm nahi hua. Agar Essentials chal raha hai:

| | À la carte | Essentials |
|---|---|---|
| SES per 1K | $0.10 | **$0.16** |
| Tumhara cost/1K (500k volume) | $0.15 | **$0.21** |
| $20 plan (60k) GM | 68% | **37%** |
| $50 plan (150k) GM | 68% | **45%** |
| 3.38M emails/month par extra bill | — | **+$203/month** |

**Confirm karo:** SES console → Pricing plan → à la carte. `python -m app.scripts.check_ses`
bhi quota batata hai, magar plan name console mein hi dikhta hai.

---

## 5. Costs jo tumne count nahi kiye

| Cost | Rate | $5 plan par | $20 plan par |
|---|---|---|---|
| **Payment gateway** (Razorpay 2% / Stripe 2.9%+$0.30) | 2-3% + fixed | **$0.10-0.45 (2-9%)** | $0.40-0.88 (2-4%) |
| **GST 18%** (Indian customers) | revenue ka 18% | **$0.90** | $3.60 |
| **Support** (15% ticket rate, 20 min, $4/hr) | ~$0.20-1.30/customer | $0.20 (4%) | $0.40 (2%) |
| **Attachment bandwidth** ($0.12/GB) | 100KB invoice × 1,000 = $0.012 | negligible | negligible |
| **Email validation** (marketing only) | $0.004/address | — | — |
| **Neon paid tier** (at scale) | $19/mo | fixed | fixed |
| **LLM tokens** (agent) | $0.30-3.00/1M | — | — |
| **Refunds/chargebacks** | 1-2% | $0.05 | $0.20 |

### Sabse bada chhupa hua: GST

Agar tum $5 **GST-inclusive** charge karte ho (jo India mein normal hai):

```
Customer pays:      $5.00
GST (18%):         -$0.76   ← sarkar ka, tumhara nahi
Payment fee (2%):  -$0.10
SES (5,000):       -$0.50
Support:           -$0.20
                  --------
Actual profit:      $3.44   → 69% of gross, 81% of net revenue
```

Aur agar customer **international** hai (USD, no GST): $5 → $4.90 after payment, $4.20 profit.

**Isliye pricing page par saaf likho:** "prices exclude GST" ya "inclusive of GST".
Warna tumhara 90% GM **69%** ban jayega bina pata chale.

### Payment gateway ka fixed part khatarnaak hai

Stripe: 2.9% + **$0.30**. $5 plan par:
```
$0.30 fixed ÷ $5 = 6% + 2.9% = 8.9% fee
```
Matlab $5 par tum **$0.45** gateway ko de rahe ho — pura SES cost se zyada!

**Fix:** Razorpay/UPI (India, ~2% no fixed) use karo INR ke liye, ya
**$5 plan ko annual-only** karo ($50/year → fixed fee 0.6% ho jata hai).

---

## 6. Poora P&L — realistic scenarios

Fixed cost: VPS $20 + domain $1 = **$21/month**
Variable: $0.10/1K + events + support
Payment + GST: 18% GST (inclusive) + 2% gateway

### 100 paid customers + 900 free users

Assumption: blended ARPU **$19.30**, avg 28,400 emails/customer/month (tumhare tier mix par)

| Line | Amount |
|---|---|
| **Gross revenue** (100 × $19.30) | **$1,930** |
| GST 18% (if inclusive) | −$294 |
| Payment gateway 2% | −$39 |
| **Net revenue** | **$1,597** |
| SES (2.84M paid emails) | −$284 |
| SES (free tier: 900 × 1,500 × 40% util = 540k) | −$54 |
| SNS + SQS | −$6 |
| VPS + domain | −$21 |
| Neon | $0 (free tier) |
| Support (15 tickets) | −$20 |
| **Contribution** | **+$1,212/month (₹1.07 lakh)** |
| Margin on gross revenue | **63%** |
| **Cost per 1,000 emails (actual)** | **$0.107** |

**Tumhara $0.15 assumption vs actual $0.107 → 40% conservative. Safe.**

### 500 paid customers + 4,000 free users

| Line | Amount |
|---|---|
| Gross revenue (500 × $19.30) | **$9,650** |
| GST + gateway (20.4%) | −$1,969 |
| **Net revenue** | **$7,681** |
| SES paid (14.2M emails) | −$1,420 |
| SES free (4,000 × 600 = 2.4M) | −$240 |
| SNS + SQS (16.6M events) | −$60 |
| VPS (bigger: $40) | −$40 |
| Neon Launch | −$19 |
| Support (1 person, part-time + tooling) | −$600 |
| **Contribution** | **+$5,302/month (₹4.7 lakh)** |
| Margin | **55%** |
| **Cost per 1,000** | **$0.107** |

### 2,000 paid + 15,000 free users

| Line | Amount |
|---|---|
| Gross revenue | **$38,600** |
| GST + gateway | −$7,874 |
| **Net revenue** | **$30,726** |
| SES paid (56.8M) | −$5,680 |
| SES free (15,000 × 600 = 9M) | −$900 |
| SNS + SQS (66M events) | −$240 |
| VPS ($150, multiple boxes) | −$150 |
| Neon Scale | −$69 |
| Support (3 people) | −$1,800 |
| **Contribution** | **+$21,887/month (₹19.4 lakh)** |
| Margin | **57%** |
| **Cost per 1,000** | **$0.116** |

**Dhyan do:** 2,000 customers par bhi cost/1K $0.116 hai, $0.05 nahi. Kyunki free tier
aur support dono badhte hain. $0.15 ka assumption **hamesha safe** rehta hai.

---

## 7. Break-even — tumhara asli number

| Fixed monthly cost | Break-even paid customers (ARPU $19.30, 63% contribution) |
|---|---|
| ₹1,700 VPS + domain (~$21) | **2 customers** |
| + $100 support tooling/time | **10 customers** |
| + full-time support ($400) | **34 customers** |
| + marketing $500 | **74 customers** |
| + founder salary $1,000 | **150 customers** |

At 3% conversion: **150 paid = 5,000 signups**. Ye tumhara 12-18 month target hai.

---

## 8. Ek line ka verdict

> **Tumhara $0.15/1K conservative aur safe hai — jab volume 400k+/month ho.**
> Magar do cheezein:
> **(1) Volume 100k se kam par asli cost $0.30/1K hai — top tiers ($40/$50) launch par
> mat becho, warna loss hoga.**
> **(2) GST + payment gateway 20% nikaal dete hain — isliye $5 plan Stripe par
> nahi, Razorpay/UPI par becho (ya annual-only).**
> **Aur confirm karo ki SES à la carte par ho, Essentials par nahi ($0.16 vs $0.10).**

---

## 9. Quick checklist — 5 cheezein aaj hi confirm karo

| # | Cheez | Kaise | Kyun |
|---|---|---|---|
| 1 | **SES à la carte?** | Console → Pricing plan → "Cancel plan" agar Essentials | $0.10 vs $0.16 = margin ka 40% |
| 2 | **Payment gateway fee** | Razorpay India 2% vs Stripe 2.9%+$0.30 | $5 plan par 9% vs 2% |
| 3 | **GST inclusive ya exclusive** | Pricing page par likho | 18% ka farq |
| 4 | **Launch par top tier cap** | $10 max jab tak 100k/mo na ho | loss se bacho |
| 5 | **Free tier ka ceiling** | dormancy reclaim + sandbox gate | $150/mo → $60/mo |
