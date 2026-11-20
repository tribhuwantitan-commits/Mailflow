# Phase 9 — dashboard

Status: **implemented.** Tests: **157 passed, 1 skipped.**

---

## 1. Dashboard ka kaam kya hai

Teen sawaal, isi order mein:

1. **Email chal raha hai ya nahi?** — kisi ne ek bhi email deliver nahi kiya to baaki
   page bekaar hai
2. **Kitni quota bachi hai?** — daily **aur** monthly
3. **Delivery theek hai?** — bounce/complaint, wahi rate jo account pause karta hai

Page ka naam "analytics" nahi, **"get set up"** hai. Kyunki 90% naye tenant pehle
teen steps par atke rehte hain, aur unhe chart nahi — **agle kadam** chahiye.

---

## 2. Naya endpoint

```http
GET /v1/organizations/{id}/stats?window_days=30
Cookie: mailflow_access=...
```

```json
{
  "plan": "free",
  "activation": {
    "complete": true,
    "first_delivered_at": "2026-11-15T07:48:37Z",
    "steps": [
      {"key": "domain",    "label": "Verify a sending domain", "done": true},
      {"key": "api_key",   "label": "Create an API key",      "done": false},
      {"key": "send",      "label": "Send your first email",  "done": true},
      {"key": "delivered", "label": "See it delivered",       "done": true}
    ]
  },
  "limit":  {"daily_emails": 50, "monthly_emails": 1000},
  "used":   {"daily_emails": 12, "monthly_emails": 340},
  "remaining": {"daily_emails": 38, "monthly_emails": 660},
  "deliverability": {
    "sent": 340, "delivered": 325, "bounced": 12, "complained": 0, "suppressed": 3,
    "bounce_rate": 0.0356, "complaint_rate": 0.0, "judged": 337, "window_days": 30
  },
  "volume": [{"day": "2026-11-07", "emails": 14}, "..."]
}
```

Aur activity table:

```http
GET /v1/organizations/{id}/emails?limit=20
```

Bodies **jaan-boojh kar nahi** bheje jaate: list unhe dikhati nahi, wo row ka mehnga
hissa hain, aur 30 din baad delete ho jaate hain — to jo summary unhe kabhi carry hi
nahi karta, wo retention ke baad **toot nahi sakta**.

---

## 3. Page

`GET /dashboard` — ek HTML file, **koi build step nahi, koi CDN nahi**.

### Kyun string, template engine nahi

VPS par Node nahi, bundler nahi, aur deploy ke waqt ek template directory "missing"
ho sakti hai. Ek file jo module ke andar hai, **kabhi missing nahi hoti**.

### Kyun CDN nahi

`Content-Security-Policy: default-src 'none'` — sirf inline style/script aur `connect-src
'self'`. Ek CDN ka `<link>` lagate hi policy usko block kar degi, aur page bina styling
ka dikhega. Isliye ek bhi external request nahi.

### Screenshot / live preview

`docs/` ke bahar demo runner se chalta hai (repo mein nahi):

```
/tenant/dashboard  →  Today / This month / Bounce / Complaint
                      Get set up (4 step checklist)
                      Last 14 days (sparkline, zero-filled)
                      Recent email (status pills)
```

Dark mode `prefers-color-scheme` se automatic.

---

## 4. Teen design decisions

### (a) "First delivered email" activation metric hai, signup nahi

Benchmark: **activation theek ho to conversion 4.1x**. Isliye `first_delivered_at`
pehla field hai, aur checklist ka **aakhri step** "See it delivered" hai — "send"
nahi.

`first_delivered_at` do jagah se aata hai (`delivery_events.provider_event_at` aur
`email_messages.delivered_at`), aur **jo pehle ho** wo liya jaata hai. Race mein event
pehle aa sakta hai, aur dono mein se ek par bharosa karna galat number deta hai.

### (b) Daily **aur** monthly dono dikhte hain

Sirf daily dikhana customer ko do baar surprise deta hai. `50/day` bar green rehta hai
jab tak `1,000/month` khatam nahi ho jata — aur tab wo samajh hi nahi paata ki kyun.

### (c) Deliverability wahi rate hai jo pause karta hai

`bounce_rate = bounced / (delivered + bounced)`, `judged` saath dikhaya jaata hai.
Dashboard jo "sab theek hai" kehta hai jab worker account pause karne wala hai — wo
dashboard na hone se bura hai.

---

## 5. Security

| Cheez | Kaise |
|---|---|
| Auth | **Session cookie** — API key nahi. Browser page hai. |
| Tenant scope | `membership()` **har** query se pehle. Doosre org ka id → **404**. |
| Cache | `Cache-Control: no-store` — quota counter cache se nahi |
| XSS | CSS/JS inline, koi external source nahi, `default-src 'none'` |
| Body leak | List endpoint bodies bhejta hi nahi |
| MIME sniffing | `X-Content-Type-Options: nosniff` |

**9 tests** ye sab pin karte hain, including:
- `test_stats_are_tenant_scoped` — doosre tenant ka id 404
- `test_stats_require_a_session` — cookie ke bina 401
- `test_recent_emails_hides_bodies`

---

## 6. Kya **nahi** bana (jaan-boojh kar)

| Cheez | Kyun nahi | Kab |
|---|---|---|
| **Login form** | `/v1/auth/login` already hai; page usi cookie par chalta hai | jab landing page bane |
| **Signup page** | wahi | marketing ke saath |
| **Billing / upgrade button** | gateway decide nahi hua | jab Razorpay/Cashfree aaye |
| **Chart library** | 60 line ka sparkline kaafi hai; 200 KB JS nahi | kabhi nahi |
| **Date range picker** | `?window_days=` query param | — |
| **Email detail page** | `/v1/emails/{id}/events` API ready hai | next |
| **Team members** | API ready hai | next |
| **Admin/internal view** | customer-facing page pehle | baad |

---

## 7. Chalane ka tareeqa

Dashboard ko kuch naya setup nahi chahiye — wahi server, wahi cookie:

```bash
# API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Browser
https://api.aapkadomain.com/dashboard
```

⚠️ **Caddy/nginx** ke through serve karo, taaki cookie `Secure` rahe. Direct
`http://IP:8000` par cookie kaam karega magar `Secure` flag ke bina — sirf testing ke liye.

---

## 8. Aapka checklist

| # | Kaam | Time |
|---|---|---|
| 1 | `alembic upgrade head` (`0009_monthly_quota`) | 1 min |
| 2 | server restart | 1 min |
| 3 | `https://your-domain/dashboard` kholo | — |
| 4 | Tenant banao + domain verify + email bhejo | 5 min |
| 5 | Confirm karo ki 4 steps tick ho gaye | — |

**Step 5 hi asli test hai.** Wo 4 tick na ho to dashboard apna kaam nahi kar raha.
