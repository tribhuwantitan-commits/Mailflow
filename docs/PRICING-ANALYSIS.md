# Pricing Plan Analysis — Mailflow (owner's draft)

Date: **November 2026**. Ye analysis hai, decision nahi. Numbers sab **derived** hain
tumhare diye gaye prices se + SES à la carte $0.10/1K cost assumption se.

---

## 1. Tumhara plan — jaisa likha hai

**Email sending**

| Tier | Price | Emails | Gate |
|---|---|---|---|
| Free | $0 | 50/day (1,500/mo) | **verified domain** |
| Verified | $0 | 100/day (3,000/mo) | **card verification, $1-2 charge** |
| Paid 1 | $5 | 5,000 | **all features (reverse trial)** |
| Paid 2 | $10 | 15,000 | — |
| Paid 3 | $15 | 40,000 | — |
| Paid 4 | $20 | 60,000 | — |
| Paid 5 | $25 | 75,000 | — |
| Paid 6 | $30 | 90,000 | — |
| Paid 7 | $40 | 120,000 | — |
| Paid 8 | $50 | 150,000 | — |

Overage: $0.45/1K → $0.35/1K (higher plans)
Dedicated IP: $25/mo + $0.25/1K
Marketing: dedicated IP $20 + $0.45/1K, separate account, antispam + auto-pause
Auto temp-mail blocking: toggleable feature
MCP: $4.99 → $19.99
Agent (aapke server par, aapke API se): $9.99 → $29.99
Assumed paid conversion: **3%**

---

## 2. Scorecard — kya accha hai, kya risky

| # | Cheez | Verdict | Kyun |
|---|---|---|---|
| 1 | Domain verification free tier ka gate | ✅ **bahut accha** | abuse 80-90% khatam, sirf serious users aate hain, aur DKIM reputation bhi tumhari |
| 2 | Card verification se 100/day | ✅ accha | ye classic "real user" signal hai; charge ₹2 refundable rakho |
| 3 | $5 entry with all features | ✅ **accha** | reverse trial psychology — user ko poora product dikhta hai, volume par pay karta hai |
| 4 | $1.00/1K entry → $0.333/1K top | ✅ **strong** | Resend se sasta, Postmark se **4x sasta** |
| 5 | 8 paid tiers | ⚠️ **zyada** | 8 tiers confuse karte hain; 5-6 kaafi hain |
| 6 | Marketing alag account + auto-pause | ✅ **excellent** | yahi wo cheez hai jo tumhe bachayegi |
| 7 | Auto temp-mail blocking | ✅ **differentiator** | SES/Resend mein nahi hai, aur cost ~$0 |
| 8 | MCP alag subscription | ❌ **risky** | MCP distribution channel hai, product nahi |
| 9 | Agent $9.99 se | ❌ **loss risk** | LLM token cost tumhari hai, revenue fixed hai |
| 10 | $15-$50 tiers mein same $/1K | ⚠️ gap | $15 ke baad koi per-email benefit nahi |

---

## 3. Margin math — har tier ka

SES cost = $0.10/1K (à la carte). Infra (VPS, Neon) fixed hai, per-email cost nahi.

| Price | Emails | $/1K | SES cost | Gross profit | **GM %** |
|---|---|---|---|---|---|
| $5 | 5,000 | **$1.000** | $0.50 | $4.50 | **90%** |
| $10 | 15,000 | **$0.667** | $1.50 | $8.50 | **85%** |
| $15 | 40,000 | **$0.375** | $4.00 | $11.00 | **73%** |
| $20 | 60,000 | **$0.333** | $6.00 | $14.00 | **70%** |
| $25 | 75,000 | **$0.333** | $7.50 | $17.50 | 70% |
| $30 | 90,000 | **$0.333** | $9.00 | $21.00 | 70% |
| $40 | 120,000 | **$0.333** | $12.00 | $28.00 | 70% |
| $50 | 150,000 | **$0.333** | $15.00 | $35.00 | 70% |

**Verdict: margins healthy hain, 70-90%.** Klaviyo 75%, Resend ~75% — tum usi range mein ho.
Ye mere pichhle message wale "Scenario A (12% margin)" se **bahut behtar** hai, kyunki tumne
entry par $1.00/1K charge kiya hai, $0.12/1K nahi.

### Ek architectural observation

**$15 ke baad $/1K bilkul flat hai ($0.333).** Matlab $30, $40, $50 tiers
**volume ke alawa kuch nahi dete**. Customer ko $20 se $50 par jaane ka koi
per-email fayda nahi — sirf zyada included volume.

Isse do cheezein hoti hain:
- ✅ Simple rakhna easy (Postmark aisa hi hai)
- ❌ $25/$30/$40/$50 kabhi nahi bikenge — log $20 lo aur overage do, ya $50 lo.
  Beech ke tiers **dead inventory** ban jayenge.

**Fix ka option:** beech ke tiers ko **non-volume benefits** do (seats, retention,
SLA, support, inbound, validation) — warna unhe hata do.

---

## 4. Comparison — popular sites se

### Per-1,000 price (kam = sasta)

| Provider | Entry $/1K | At 60,000 emails | Position |
|---|---|---|---|
| **Amazon SES** | **$0.10** | $6 | cheapest, DIY |
| Elastic Email | $0.09 | ~$6 | cheapest, DIY |
| **ZeptoMail (Zoho)** | **$0.25** | $15 | India, transactional-only |
| **Mailflow (tumhara) $20 tier** | **$0.333** | **$20** | ← yahan |
| Brevo | ~$0.35 | ~$25 | all-in-one |
| **Resend Pro** | **$0.40** | $24 ($20+overage) | closest competitor |
| SendGrid Essentials | ~$0.40 | $35+ | — |
| Mailjet | ~$0.35-0.50 | $35 | — |
| Mailgun Foundation | $0.70 | $42 | — |
| **Postmark** | **$1.50** | $90 | premium deliverability |
| Mailchimp Transactional | ~$1.50 | $80+ | — |

### Same price point par kitna milta hai

| Provider | $20 mein | Tumhare $20 mein |
|---|---|---|
| **Resend** | 50,000 | **60,000 (+20%)** |
| **Mailgun** | 25,000 | **60,000 (+140%)** |
| **Postmark** | ~13,000 | **60,000 (+360%)** |
| **SendGrid** | ~50,000 | **60,000** |
| **ZeptoMail** | 80,000 | 60,000 (−25%) |
| **SES** | 200,000 | 60,000 (−70%) |

**Tumhari position:** Resend/Postmark/SendGrid/Mailgun se **sasta**, SES/ZeptoMail se
**mehnga**. Yahi sahi slot hai — "SES se sasta nahi, par SES ka dard bhi nahi".

### Comparison — MCP/Agent ke saath (koi bhi ye nahi bech raha)

| Provider | MCP | Agent | Temp-mail block | Marketing isolation |
|---|---|---|---|---|
| Resend | free (official MCP) | — | ❌ | streams |
| Postmark | ❌ | — | ❌ | streams |
| Brevo | ❌ | partial | ❌ | ❌ |
| Klaviyo | — | ✓ (AI agent, included) | ❌ | ✓ |
| SES | ❌ | — | ❌ | Tenants (paid) |
| **Mailflow (plan)** | **$4.99-19.99** | **$9.99-29.99** | **✓** | **✓ separate account** |

---

## 5. Funnel math — 3% conversion

### Assumption set

```
1,000 signups/month
  ├─ domain verified:        35%  → 350
  ├─ first successful send:  80%  → 280   (of verified)
  └─ paid:                    3%  → 30    (of signups)
```

⚠️ **Pehla sawal:** 3% **kis cheez ka**? Signups ka ya activated users ka?
- 3% of signups = **30 paid** (optimistic)
- 3% of activated (350) = **10.5 paid** (realistic)

Neeche dono dikha raha hoon, kyunki ye 3x farq hai.

### Case A — 3% of signups (30 paid/month)

| Item | Value |
|---|---|
| Blended ARPU* | **$19.30** |
| Revenue | **$579** |
| SES cost (free tier: 600k emails @ 40% utilization) | −$60 |
| SES cost (paid: 30 × 35k avg) | −$105 |
| VPS + infra | −$50 |
| Support (25 hrs @ $4/hr India) | −$100 |
| **Contribution** | **+$264/mo** |
| Gross margin (before support) | **63%** |

\* ARPU mix: $5 (40%), $10 (25%), $15 (15%), $20 (8%), $25 (5%), $30 (3%), $40 (2%), $50 (2%)
+ add-ons (20% take dedicated IP $25, 10% take MCP $9.99, 5% take agent $19.99)

### Case B — 3% of activated (10.5 paid/month)

| Item | Value |
|---|---|
| Revenue | **$203** |
| SES (free 600k) | −$60 |
| SES (paid 10.5 × 35k) | −$37 |
| Infra | −$50 |
| Support | −$60 |
| **Contribution** | **−$4/mo** ← break-even se neeche |

**Sabak: 3% of signups (Case A) par business chalta hai. 3% of activated (Case B) par
nahi chalta.** Isliye 1,000 signups/month se kam par plan economically nahi chalta.

### Kitne signups chahiye break-even ke liye

| Fixed cost | Break-even (Case A, 63% GM) |
|---|---|
| ₹4,000 (~$48)/month | **~4 paid customers** |
| + 1 full-time support ($400) | **~38 paid customers** |
| + marketing spend $500 | **~80 paid customers** |

At 3% conversion: **80 paid = 2,670 signups/month**. Ye tumhara asli target hai.

### Free tier ka ceiling — ye number yaad rakho

```
1,000 free users × 50/day × 30 days = 1,500,000 emails/month
SES cost = $150/month  (₹13,200)
Revenue from those 1,000 = $0
```

**Free tier tumhara sabse bada kharcha hai, aur wo linear badhta hai.**
Mitigation (section 9 mein detail):
- inactivity par quota ghatao (30 din no send → 10/day)
- 50/day sirf verified-domain users ko, warna 20/day
- disposable-email block default on

---

## 6. Plan ke 5 asli flaws + fix

### Flaw 1 — Free tier activation tootega (sabse bada)

**Problem:** free tier ke liye **domain + DNS** chahiye. Naye user ka pehla experience
"DNS records daalo" hai. Real activation rate: **25-40%**. Matlab 1,000 signups →
600 users kabhi pehla email bhej hi nahi payenge.

Resend isse "onboarding@resend.dev" se solve karta hai — bina domain apne hi email par
bhej ke product dekh lo.

**Fix:**
| Mode | Requirement | Limit |
|---|---|---|
| **Sandbox** | koi nahi | 20/day, **sirf apne verified email par** |
| **Domain** | DKIM verify | 50/day, kisi ko bhi |
| **Card** | ₹2 auth | 100/day |

Sandbox mode se activation 35% → **70%** ho jayega, aur abuse nahi badhega (sirf khud ko bhej sakte hain).

### Flaw 2 — Agent plan loss karega

**Problem:** agent **tumhare server par**, **tumhare API** se chalega. LLM token cost
**tumhari** hai, revenue **fixed** hai.

```
$9.99 plan, customer 500 agent runs/month
  Tokens: 500 runs × 20k token = 10M tokens
  Cost: 10M × $0.30/1M (cheap model)  = $3.00   → 70% GM ✅
  Cost: 10M × $3.00/1M (premium model) = $30.00  → LOSS ❌
```

Ek heavy user 2,000 runs karega → premium model par **$120/month loss**.

**Fix (mandatory):**
- **Token quota per tier** (section 7 mein numbers)
- **Cheap model default** (`gpt-4o-mini` / `claude-haiku` class), premium model sirf top tier
- **Hard cutoff** at quota (throttle, not bill shock)
- **Per-user rate limit**: 20 runs/hour
- Cost visibility: har run ka token count log karo, dashboard mein "you used 62% of tokens"

### Flaw 3 — MCP ko alag subscription bechna

**Problem:** MCP (Model Context Protocol) ek **open standard** hai aur official MCP servers
**free** hote hain. `resend-mcp` free hai. Log tumhara $4.99/month kyun denge jab free
alternative hai?

**Sach:** MCP **distribution channel** hai, product nahi. Iska kaam user ko tumhare
product tak laana hai — monetize karna nahi.

**Fix (recommended):**
- MCP **free** rakho, **paid plans ke saath bundled** (jaisa har provider karta hai)
- Jo actually paisa laata hai: **hosted agent** + **usage** — wahi alag beche
- Agar MCP bechna hi hai: usme **hosted value** daalo (managed OAuth, saved workflows,
  team sharing, audit log) — tab $4.99 justified hai

### Flaw 4 — 8 tiers, aur beech mein dead space

**Problem:** $15, $20, $25, $30, $40, $50 — sab $0.333/1K par. Customer $20 se $30 par
jaane ka reason nahi dhoond payega.

**Fix:** 6 tiers, aur beech wale tiers ko **non-volume** benefits do:

| | $5 | $10 | $20 | $35 | $60 | $100 |
|---|---|---|---|---|---|---|
| Emails | 5,000 | 15,000 | 60,000 | 130,000 | 250,000 | 500,000 |
| $/1K | $1.00 | $0.667 | $0.333 | $0.269 | $0.240 | $0.200 |
| Reason to upgrade | — | volume | volume | SLA + seats | priority + IP | dedicated + SSO |

Kam tiers = **kam confusion**, zyada conversion.

### Flaw 5 — $1-2 card charge India mein friction hai

**Problem:** ₹2 charge ke liye 3D-Secure/OTP chahiye. Bahut Indian users ke paas credit
card nahi (debit card/UPI hai). Aur recurring mandate ke liye RBI e-mandate chahiye.

**Fix:**
- Razorpay/UPI autopay support karo (₹2 refundable, ya ₹1)
- Debit card + UPI dono allow karo
- Charge **refund** karo turant (visible in dashboard: "₹2 refunded")
- Alternative: **no card** but 100/day ke liye **email verify + 30 din purana account**

---

## 7. Missing middleware — jo tumne "bich ka plan bana dena" kaha

### MCP tiers

| Plan | Price | Included | Limits |
|---|---|---|---|
| **MCP Basic** | **$4.99** | 1 workspace, 20 tools, std tools | 1,000 tool calls/mo, 1 user |
| **MCP Pro** | **$9.99** | 3 workspaces, all tools, OAuth | 5,000 calls/mo, 3 users, 30-day logs |
| **MCP Team** | **$14.99** | 10 workspaces, team sharing | 20,000 calls/mo, 10 users, 90-day logs, audit |
| **MCP Advanced** | **$19.99** | unlimited workspaces, custom tools | 100,000 calls/mo, 25 users, 365-day logs, priority support |

**Cost:** tool call ≈ $0.0001 (compute only, no LLM). 100k calls = $10. Fine.

### Agent tiers (ye asli cost center hai)

| Plan | Price | Runs/mo | **Token quota** | Model | Rate limit |
|---|---|---|---|---|---|
| Agent Starter | $9.99 | 200 | **300k tokens** | cheap (mini/haiku) | 10/hr |
| Agent Pro | $14.99 | 500 | **1M tokens** | cheap | 20/hr |
| Agent Growth | $19.99 | 1,000 | **2.5M tokens** | cheap + standard | 30/hr |
| Agent Scale | $24.99 | 2,000 | **6M tokens** | + premium allowed | 50/hr |
| Agent Max | $29.99 | 4,000 | **15M tokens** | + premium | 100/hr |

**Cost check (cheap model $0.30/1M):**

| Plan | Token quota | Cost | Revenue | GM |
|---|---|---|---|---|
| $9.99 | 300k | $0.09 | $9.99 | 99% |
| $14.99 | 1M | $0.30 | $14.99 | 98% |
| $19.99 | 2.5M | $0.75 | $19.99 | 96% |
| $24.99 | 6M | $1.80 | $24.99 | 93% |
| $29.99 | 15M | $4.50 | $29.99 | 85% |

**Premium model ($3/1M) par same quota:**
| $29.99 | 15M | **$45.00** | $29.99 | **−50% LOSS** |

**Rule: premium model **kabhi** default nahi. Top tier par bhi "premium available"
matlab quota **5x chhota** (15M → 3M).

### Marketing add-on

| Item | Price | Cost | GM |
|---|---|---|---|
| Dedicated IP | $20/mo | $15 (managed) | 25% |
| Per 1,000 emails | $0.45 | $0.08 (IP) + $0.10 (send) = $0.18 | **60%** |
| 100k emails/month | $20 + $45 = **$65** | $15 + $18 = $33 | **49%** |

Marketing margin transactional se **kam** (49% vs 70%) — kyunki IP + validation ka cost hai.
Ye theek hai; isko "premium add-on" hi rakho, discount mat do.

---

## 8. Features per tier — poora matrix

**Philosophy (tumhara intent):** $5 par **saare features unlocked** (reverse trial feel),
higher tiers **limits + support + SLA** badhate hain, aur volume.

| Feature | Free (sandbox) | Free (domain) | Card tier | $5 | $10 | $20 | $35 | $60 | $100 |
|---|---|---|---|---|---|---|---|---|---|
| **Emails/month** | 600 | 1,500 | 3,000 | 5,000 | 15,000 | 60,000 | 130,000 | 250,000 | 500,000 |
| Daily cap | 20 | 50 | 100 | — | — | — | — | — | — |
| **Domains** | 0 | 1 | 1 | 1 | 3 | 10 | 20 | 35 | 50 |
| **Team seats** | 1 | 1 | 1 | 2 | 3 | 10 | 20 | 35 | Unlimited |
| **Log retention** | 1 day | 3 days | 7 days | 7 days | 14 days | 30 days | 90 days | 180 days | 365 days |
| **API rate limit** | 2 rps | 2 rps | 5 rps | 5 rps | 10 rps | 20 rps | 40 rps | 60 rps | 100 rps |
| **Webhooks** | 1 | 1 | 1 | 2 | 5 | 10 | 20 | 35 | 50 |
| **Templates** | 3 | 5 | 10 | 25 | 50 | 100 | 250 | 500 | Unlimited |
| REST API + SMTP | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Idempotency keys | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Suppression list** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Auto-pause (bounce/complaint)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Auto temp-mail blocking** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Delivery events (webhook) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Latency analytics** | basic | basic | p50/p95 | p50/p95 | + per-ISP | + per-domain | + export | + API | + SLA report |
| Open/click tracking | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Email validation** | 100/mo | 200/mo | 500/mo | 1,000/mo | 3,000/mo | 10,000/mo | 25,000/mo | 50,000/mo | 100,000/mo |
| **Inbound email** | — | — | — | 100/mo | 500/mo | 2,000/mo | 5,000/mo | 10,000/mo | 25,000/mo |
| **Marketing stream** | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Dedicated IP** | — | — | — | add-on $25 | add-on | add-on | **included** | **included** | **included** |
| Custom MAIL FROM | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Audit logs | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| **SSO / SAML** | — | — | — | — | — | — | ✓ | ✓ | ✓ |
| Sub-accounts (teams) | — | — | — | — | — | — | 3 | 10 | Unlimited |
| **Support** | docs | docs | email | email | email | email 24h | priority 12h | priority 6h | dedicated + Slack |
| **SLA** | — | — | — | — | — | 99.5% | 99.5% | 99.9% | 99.95% |
| Status page + incident email | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **MCP access** | ✓ free | ✓ free | ✓ | **MCP Basic** | **MCP Pro** | **MCP Team** | **MCP Advanced** | Advanced | Advanced |
| **Agent** | — | — | — | add-on | add-on | add-on | add-on | add-on | **included Starter** |

### Reverse trial kaisa lagega (14 din)

```
Day 0:  signup → sandbox mode → 600 emails, sab features unlocked
Day 1:  "You're on Pro trial — 60,000 emails, all features"
Day 7:  email: "7 days left. You've sent 1,240 emails."
Day 13: email: "Trial ends in 1 day. Pick a plan."
Day 14: → free tier (domain: 50/day) agar plan nahi liya
```

⚠️ **Reverse trial ka trap:** free tier par girne ke baad user ka mail **band nahi hona chahiye**,
sirf limit kam hona chahiye. Nahi to churn 100% hoga. Aur onboarding mein
"tumhara data 30 din tak safe hai" likho.

---

## 9. Free tier ko sustainable banana

50/day × 1,000 users = **1.5M emails/month = $150**. Ye tumhara sabse bada cost line hoga.

| Control | Kaise | Bachat |
|---|---|---|
| **Dormancy reclaim** | 30 din koi send nahi → 10/day | 40-50% |
| **Sandbox for new users** | pehle 7 din sirf apne email par | 20% |
| **Skill-based unlock** | 50/day sirf jab DKIM verified + 1 domain | abuse 80% |
| **Temp-mail block default on** | bounce kam → SES cost kam + reputation | 5-10% |
| **Quota per recipient** | ek recipient ko 10 emails/day max | OTP bombing rok |

Realistic: 1,000 users ka free-tier cost **$150 → $60-75/month**.

---

## 10. Revised recommendation (numbers ke saath)

### Pricing — 6 tiers, not 8

| Plan | Price | Emails | $/1K | GM | Note |
|---|---|---|---|---|---|
| Free sandbox | $0 | 600/mo | — | — | activation |
| Free domain | $0 | 1,500/mo (50/day) | — | — | real users |
| Free card | $0 | 3,000/mo (100/day) | — | — | serious users |
| **Starter** | **$5** | 5,000 | $1.00 | 90% | all features |
| **Growth** | **$10** | 15,000 | $0.667 | 85% | — |
| **Pro** | **$20** | 60,000 | $0.333 | 70% | most popular |
| **Business** | **$35** | 130,000 | $0.269 | 63% | + SLA, SSO, IP |
| **Scale** | **$60** | 250,000 | $0.240 | 58% | + priority |
| **Enterprise** | **$100** | 500,000 | $0.200 | 50% | + dedicated |

Overage: $0.45 (Starter/Growth) → $0.35 (Pro+) → $0.30 (Business+) → $0.25 (Scale+)
Dedicated IP: $25 + $0.25/1K (as-is — ye sahi hai)
MCP: **bundled free** (ya $4.99 only for advanced hosted features)
Agent: $9.99 / $14.99 / $19.99 / $24.99 / $29.99 — **token quotas mandatory**
Marketing: $20 IP + $0.45/1K — as-is

### 12-month projection (Case A, 3% of signups)

| | M1 | M3 | M6 | M12 |
|---|---|---|---|---|
| Signups/mo | 100 | 400 | 1,000 | 2,500 |
| Paid customers (cumulative, 4% churn) | 3 | 11 | 27 | 68 |
| MRR | $58 | $212 | $521 | $1,312 |
| Free-tier SES cost | $6 | $24 | $60 | $150 |
| Contribution | ~$10 | ~$90 | ~$260 | ~$700 |

**Slow hai — aur ye normal hai.** Klaviyo ko 10 saal lage $1B revenue ke liye.
Email SaaS **compounding business** hai, viral nahi.

---

## 11. Top 3 karan jo is plan ko maar sakte hain

| # | Risk | Probability | Impact | Fix |
|---|---|---|---|---|
| 1 | **Agent token cost** (fixed price, variable cost) | **High** | Loss per customer, unlimited | token quota + cheap model + hard cutoff |
| 2 | **Free tier burn** at 2,000+ users | Medium | $300/mo, no revenue | dormancy reclaim + sandbox gate |
| 3 | **MCP zero sales** (free alternative available) | **High** | wasted effort | bundle it, sell the agent instead |

Aur ek chhota par important: **3% conversion** tabhi milega jab activation accha ho.
Activation ka biggest blocker **domain verification** hai — isliye sandbox mode
"nice to have" nahi, **must have** hai.

---

## 12. Features jo abhi tak missing hain (competitive gaps)

Ye sab tumhare plan mein nahi hain, magar competitors ke paas hain:

| Feature | Kaun deta hai | Priority |
|---|---|---|
| **Broadcast / campaign API** | Resend, Brevo, Mailchimp | P1 (marketing stream ke saath) |
| **Template editor (visual)** | Brevo, Mailchimp, Postmark | P2 |
| **Inbound email + parsing** | Postmark, Mailgun, SES | P1 (plan mein hai, magar implement nahi) |
| **React Email / SDK support** | Resend | **P0** — DX yahi hai |
| **CLI** | Resend | P1 |
| **Test mode / sandbox** (fake send) | Resend, Postmark | **P0** — tumhare sandbox mode ka implementation |
| **Message search** | Resend, Postmark | P1 |
| **Webhook retries + replay** | Postmark | P1 |
| **Bounce classification detail** | Postmark | P1 |
| **Custom tracking domain** | sab | P1 |
| **Sub-accounts / organizations** | Brevo, Klaviyo | P2 |
| **SMTP relay** | sab | **P0** — bahut purane apps isse aate hain |

**P0 = launch se pehle chahiye.** SMTP relay ke bina purane users nahi aayenge —
bahut libraries/plugins sirf SMTP samajhte hain.

---

## 13. Ek line ka verdict

> **Pricing ka structure accha hai (70-90% margin, Resend se sasta). Teen cheezein
> theek karo: (1) sandbox mode se activation bachao, (2) agent par token quota lagao
> warna loss hoga, (3) MCP ko free bundle karo — usse paisa nahi aayega, agent se aayega.**
