# Infrastructure — kya chahiye, kahan se milega, kitna lagega

Ye doc **poori list** hai: har cheez ka naam, kaam, kahan se milega, kitna lagega, aur
**kab** chahiye. Beginner ke liye likha hai — har cheez pehle "ye kya hai" se shuru hoti hai.

> **Ek line mein:** aapko 5 cheezein chahiye — **VPS** (computer), **PostgreSQL**
> (database), **SES** (email bhejne wala), **SNS+SQS** (delivery ki khabar), **DNS**
> (domain ki settings). Baaki sab optional hai.

---

## 0. Abhi ka table — kya hai, kya chahiye

| # | Cheez | Hai? | Abhi chahiye? | Kitna |
|---|---|---|---|---|
| 1 | Code + Python | ✅ | ✅ | free |
| 2 | Domain `testingmail2btd.net` | ✅ | ✅ | already |
| 3 | AWS account | ✅ | ✅ | free |
| 4 | **SES** | ✅ | ✅ (sandbox) | ~$0.10/1K |
| 5 | **SNS** | ❌ | ❌ Phase 7c | ~$0 (free tier) |
| 6 | **SQS** | ❌ | ❌ Phase 7c | ~$0 (free tier) |
| 7 | **PostgreSQL** | ⬜ | ⬜ API chalane ke liye | Neon free |
| 8 | **VPS / VM** | ✅ (aapka Windows RDP) | ✅ | already |
| 9 | IAM access key | ✅ | ✅ | free |
| 10 | Verified recipient (Gmail) | ❌ | ✅ sandbox test ke liye | free |

**Abhi ka kaam:** sirf #4 (SES) + #10 (Gmail verify). Baaki baad mein.

---

## 1. VPS / VM — "computer jahan app chalega"

### Ye kya hai

Ek **computer jo internet par 24x7 chalta hai**. Aap ismein remote desktop (RDP) se
login karke apna app chala sakte ho. Aapka laptop band ho jaye to bhi app chalta rahega.

VM = VPS = "Virtual Private Server" = "cloud computer". Sab ek hi cheez ke naam hain.

### Aapke paas already hai

Aapka **Windows Server (RDP)** — yahi aapka VPS hai. ✅ **Kuch kharidna nahi hai.**

### App VPS par kaise chalega

```
Windows Server (aapka RDP)
  ├── Python + .venv
  ├── uvicorn  (FastAPI app, port 8000)
  └── outbox worker (emails bhejne wala loop)
         │
         ├──→ Neon PostgreSQL  (internet par, database)
         └──→ AWS SES         (internet par, email)
```

### ⚠️ Teen cheezein jo VPS par karni padti hain

| Kaam | Kyun | Kaise |
|---|---|---|
| **Firewall** port 8000 kholo | bahar se app tak pahunchne ke liye | Windows Defender Firewall → Inbound Rules → New Rule → Port 8000 |
| **App ko restart par chalu karo** | server reboot ho to app band na rahe | Task Scheduler → "At startup" |
| **TLS (https)** | emails/API plain http par nahi | Cloudflare free (Phase 8 ka kaam) |

Windows Server par ye sab **manual** hai (Linux par systemd se automatic). Isliye
Task Scheduler wala step **zaroori** hai, warna reboot ke baad app band milta hai.

### Specs kitne chahiye

| Users | RAM | Disk | Note |
|---|---|---|---|
| 0-100 | 2 GB | 20 GB | aapka current server kaafi hai |
| 100-1,000 | 4 GB | 40 GB | |
| 1,000+ | 8 GB | 80 GB | tab Linux par jaana sasta hoga |

### ⚠️ Ye **nahi** chahiye (dobara mat poochho)

| ❌ Nahi | Kyun nahi |
|---|---|
| **EC2** | aapke paas VPS already hai; EC2 paisa waste |
| **RDS** | Neon already hai; RDS $15+/mo |
| **ALB** | $16/mo, ek app ke liye bekaar |
| **Route 53** | domain ka DNS free/cheap jagah manage hota hai |
| **Lambda** | FastAPI app ke liye nahi bana |

---

## 2. PostgreSQL — "database"

### Ye kya hai

Database = **permanent yaad-dasht**. Users, organisations, API keys, bheje hue emails,
retry counters — sab yahan rehta hai. App band ho jaye to bhi data bacha rehta hai.

Aapka code `PostgreSQL` hi maangta hai (`app/database.py`) — MySQL/SQLite nahi chalega
(production mein).

### Kahan se

| Option | Cost | Kya chuno |
|---|---|---|
| **Neon** | **free (1 GB)** | ✅ **yahi use karo** — aapke paas already hai |
| Supabase | free (500 MB) | theek, magar Neon behtar |
| Railway / Render | $5/mo | zaroorat nahi |
| Apne VPS par install | free | ❌ **mat karo** — backup/upgrade manual |

**Recommendation: Neon free tier.** Aapke paas already hai.

### Neon se kya lena hai — sirf **ek string**

Neon dashboard → project → **Connect** → connection string:

```
postgresql://neondb_owner:PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

Usme **`postgresql://` ko `postgresql+psycopg://` kar do** (kyunki aapka code `psycopg`
driver use karta hai), aur `.env` mein daal do:

```
DATABASE_URL=postgresql+psycopg://neondb_owner:PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

### ⚠️ Neon ka ek gotcha — **pooled vs unpooled**

Neon do endpoint deta hai:
- **Pooled** (`...-pooler...`) — bahut connections ke liye, **magar** `search_path` reject karta hai
- **Unpooled** — seedha connection

**Aapka app chhota hai** → **unpooled** use karo. (Ye pehle bhi phansa tha — dobara mat
poochho.)

### Table kaise banenge

Database khaali milega. Tables banane ke liye:

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
```

Ye `alembic/versions/` ke 4 migrations chalata hai → `users`, `organizations`,
`api_keys`, `emails`, `delivery_events` sab ban jate hain.

### Kitna data

| Users | DB size | Neon free (1 GB) mein |
|---|---|---|
| 1,000 | ~50 MB | ✅ bahut jagah |
| 10,000 | ~500 MB | ✅ |
| 50,000 | 2.5 GB | ❌ paid ($19/mo) |

**Email bodies** DB mein store hote hain — agar volume badhe to sirf metadata rakhna
aur body S3 mein daalna better hoga. Abhi tension nahi.

---

## 3. Amazon SES — "email bhejne wala"

### Ye kya hai

SES = **Simple Email Service**. Aapka app SES ko bolta hai "ye email bhej do", SES
asli delivery karta hai. Bina SES ke aapko khud SMTP server chalana padta — jismein
Gmail/Outlook block kar dete hain.

### Kahan se

AWS console → search **`SES`** → region **Asia Pacific (Mumbai) `ap-south-1`**

### Kyun Mumbai

Domain **jis region mein verify kiya, usi region se bhejna padta hai**. Aapka domain
Mumbai mein verified hai. Isliye `.env` mein `AWS_REGION=ap-south-1`.

Agar Gmail mein email nahi aayi to sabse pehle **yehi** check karo.

### Kya-kya lena hai

| # | Cheez | Kahan | Kaam | Abhi chahiye |
|---|---|---|---|---|
| 1 | **Domain identity** (Easy DKIM) | Identities → Create identity → Domain | "main is domain se bhej sakta hoon" | ✅ hai |
| 2 | **IAM user + access key** | IAM → Users | app ko permission | ✅ hai |
| 3 | **Pricing plan: à la carte** | SES → Pricing plan | $0.10/1K (Essentials $0.16 nahi) | ⬜ check karo |
| 4 | **Verified recipient** (Gmail) | Identities → Email address | sandbox mein bhejne ke liye | ❌ **abhi** |
| 5 | **Configuration set** | Configuration sets | open/click/bounce track | ❌ Phase 7c |
| 6 | **Production access** | Account dashboard | 200/day se zyada | ❌ launch se pehle |

### Sandbox kya hai

Naya SES account **sandbox** mein hota hai:
- **200 emails / 24 hours** (poore account ka total, per customer nahi)
- **Sirf verified recipients** ko bhej sakte ho
- **1 email/second** rate

Isliye Gmail verify karna padta hai — warna `MessageRejected: Email address is not verified`.

**Production access chhodne ke liye:** bounce/complaint handling banaya hona chahiye
(Phase 7c). Isliye abhi nahi.

### Kitna kharcha

| Volume | Bill |
|---|---|
| 1,000/mo | **$0.10** |
| 100,000/mo | **$10** |
| 500,000/mo | **$50** |

À la carte par $0.10 per 1,000. **SNS/SQS par kuch nahi lagta** (free tier).

### 📌 Aaj karna hai

SES console → **Pricing plan** → agar "Essentials" dikhe to **Cancel plan** dabao
(à la carte apne aap lag jayegi). Warna har 1,000 par $0.16 dena padega.

---

## 4. Amazon SNS — "khabar bhejne wala"

### Ye kya hai

SNS = **Simple Notification Service**. Jab SES email bhejta hai, to **kya hua** uski
khabar SNS par aati hai:

```
SES → "ye email deliver hui"     → SNS
SES → "ye bounce ho gayi"        → SNS
SES → "user ne spam mark kiya"   → SNS
```

Aapka app in khabron ke bina **nahi jaanta** ki email pahunchi ya nahi. `send_test`
par jo `accepted: provider_message_id=...` dikhta hai — wo **"SES ne le liya"** hai,
**"delivery hui" nahi**.

### Abhi kyun chahiye nahi

Aaj ka test sirf ye dekhna hai ki SES **bhej paata hai ya nahi**. Simulator aur Gmail
se wo pata chal jayega. Bounce/complaint ka pura pipeline **Phase 7c** hai.

### Kahan se

AWS console → **SNS** → Topics → Create topic

| Setting | Value |
|---|---|
| Type | **Standard** (FIFO nahi) |
| Name | `mailflow-ses-events` |
| Region | **ap-south-1** ← same as SES |

Phir SES → Configuration set → **Event destination** → SNS topic chuno.

### Kitna kharcha

| | Free tier |
|---|---|
| Notifications | **1,000,000 / month free** |
| HTTP deliveries | 100,000 / month free |

Aapki volume mein **$0.00**.

---

## 5. Amazon SQS — "khabar ki queue"

### Ye kya hai

SQS = **Simple Queue Service**. Ek **line (queue)** jismein SNS khabar daalta hai,
aur aapka worker ek-ek uthata hai.

**Kyun seedha SNS se nahi?** — Kyunki SNS "push" karta hai: agar aapka app 10 second
band tha, wo khabar **kho jayegi**. SQS khabar **rakh leta hai** — app wapas aaye to
utha lega. Isliye beech mein queue.

```
SES ──→ SNS ──→ SQS ──→ aapka worker ──→ database (suppression list, dashboard)
```

### Kahan se

AWS console → **SQS** → Create queue

| Setting | Value |
|---|---|
| Type | **Standard** |
| Name | `mailflow-ses-events` |
| Visibility timeout | 30 seconds |
| Message retention | **4 days** (default) |
| Region | ap-south-1 |

Phir SNS topic → **Subscriptions** → Create subscription → Protocol **SQS** → queue chuno.

⚠️ **Queue policy** mein SNS ko `sqs:SendMessage` ki permission deni padti hai — warna
messages aayenge hi nahi. (Phase 7c mein code ke saath karenge.)

### Kitna kharcha

| | Free tier |
|---|---|
| Requests | **1,000,000 / month free** |
| Baad mein | $0.40 per million |

Aapki volume mein **$0.00**.

### ⚠️ Ek zaroori setting

Queue banate waqt **"Encryption"** ko default (SSE-SQS) rakho — free hai aur AWS
production access ke waqt achha lagta hai.

---

## 6. DNS — "domain ki settings"

### Ye kya hai

DNS = wo jagah jahan likha hota hai "is domain ka email kaun bhejega". Bina DNS ke
Gmail aapke email ko spam daalta hai.

### Kahan se

Jahan aapne `testingmail2btd.net` kharida (GoDaddy / Namecheap / Cloudflare / Hostinger)
— wahi DNS manage karta hai. **Naya kuch kharidna nahi.**

### Kya records chahiye

| Record | Kaam | Kab |
|---|---|---|
| **DKIM** (3 CNAME) | "email sach mein is domain se aaya" | ✅ SES ne khud diye |
| **SPF** (1 TXT) | "ye IPs is domain se bhej sakte hain" | ⬜ add karo |
| **DMARC** (1 TXT) | "DKIM/SPF fail ho to kya karo" | ⬜ add karo |
| **MX** | incoming email | ❌ abhi nahi |

### SES se records kaise milenge

SES → Identities → `testingmail2btd.net` → **Authentication** tab → DKIM records
dikhenge (3 CNAME). Wo DNS provider mein paste karne hote hain.

**SPF** (TXT record, name = `@`):
```
v=spf1 include:amazonses.com ~all
```

**DMARC** (TXT record, name = `_dmarc`):
```
v=DMARC1; p=none; rua=mailto:dmarc@testingmail2btd.net
```

`p=none` se shuru karo (monitor only). Baad mein `p=quarantine` kar sakte ho.

### Kitna kharcha

**$0** — domain already hai, DNS free hai.

### ⚠️ Ye launch se pehle zaroori

SPF + DMARC **SES production access** ke liye prerequisites hain. 10 minute ka kaam hai,
magar bina inke AWS reject kar deta hai.

---

## 7. Cloudflare — "https aur protection" (optional, Phase 8)

### Ye kya hai

Aapka app `http://1.2.3.4:8000` par chalega — ye **insecure** hai. Cloudflare free
plan se `https://api.aapkadomain.com` bana sakte ho, bina certificate kharidne.

| Kaam | Cloudflare free |
|---|---|
| SSL/HTTPS | ✅ |
| DDoS protection | ✅ |
| DNS | ✅ (domain transfer kar sakte ho) |
| WAF | ✅ basic |

**Abhi nahi chahiye** — pehle app chale, phir HTTPS.

---

## 8. Sab ka bill — realistic

### Testing phase (aaj)

| Cheez | Monthly |
|---|---|
| VPS (aapka RDP) | **already hai** |
| Neon PostgreSQL | **$0** (free 1 GB) |
| SES sandbox (<200/day) | **$0.10-0.60** |
| SNS + SQS | **$0** |
| DNS | **$0** |
| **Total** | **~$1-2/mo** |

### Launch ke baad (1,000 customers, 3% paid)

| Cheez | Monthly |
|---|---|
| VPS | already |
| Neon | $0 (ya $19 agar 1GB cross) |
| SES (600k emails free tier ke) | **$60** |
| SNS + SQS | **$0** |
| **Total** | **~$60-80/mo** |

Revenue $579 (30 paid × $19.30) → **profitable**.

---

## 8b. Production monthly cost — stage by stage

Ye poora bill hai. Har stage par: kitne customers, kitne emails, kya kharcha.

**Assumptions (UNIT-ECONOMICS.md se):**
- Paid customer average **28,400 emails/month** (ARPU $19.30 ka tier mix)
- Free user average **600 emails/month** (1,500 quota × 40% utilization)
- SES **$0.10/1K** (à la carte — Essentials ho to $0.16)
- VPS price badhta hai jab load badhe (2 GB → 4 GB → multiple boxes)

| Stage | Free | Paid | Emails/mo | SES | SNS+SQS | Neon | VPS | Domain | Support | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|
| **0. Aaj (test)** | 0 | 0 | ~500 | $0.05 | $0 | $0 | $20 | $1 | $0 | **$21** |
| **1. Pehla paying customer** | 10 | 1 | 34k | $3 | $0 | $0 | $20 | $1 | $0 | **$24** |
| **2. Chhota** | 100 | 5 | 202k | $20 | $0 | $0 | $20 | $1 | $0 | **$41** |
| **3. Traction** | 500 | 25 | 1.0M | $101 | $2 | $0 | $20 | $1 | $50 | **$174** |
| **4. Growing** | 1,000 | 50 | 2.0M | $202 | $1 | $0 | $20 | $1 | $50 | **$274** |
| **5. Serious** | 4,000 | 500 | 16.6M | $1,660 | $60 | $19 | $40 | $1 | $600 | **$2,380** |
| **6. Scale** | 15,000 | 2,000 | 65.8M | $6,580 | $240 | $69 | $150 | $1 | $1,800 | **$8,839** |

### Us kharcha ke saamne revenue

| Stage | Gross revenue | GST+gateway (−20.4%) | Cost | **Contribution** | Margin |
|---|---|---|---|---|---|
| 0 | $0 | $0 | $21 | **−$21** | — |
| 1 | $19 | −$4 | $24 | **−$9** | — |
| 2 | $97 | −$20 | $41 | **+$36** | 37% |
| 3 | $483 | −$99 | $174 | **+$210** | 43% |
| 4 | $965 | −$197 | $274 | **+$494** | 51% |
| 5 | $9,650 | −$1,969 | $2,380 | **+$5,301** | 55% |
| 6 | $38,600 | −$7,874 | $8,839 | **+$21,887** | 57% |

### Teen baatein jo is table se nikalti hain

1. **Break-even sirf 2 paid customers par** hai (VPS $20 + domain $1 = $21 fixed). Stage 2
   (5 paid) par tum profit mein ho.
2. **Stage 1 par chhota loss** (−$9) hai — ye normal hai, kyunki VPS poora tum bhar rahe ho
   aur ek customer se sirf $19 aata hai. 2 customers par break-even.
3. **Cost ka 75-90% SES hai** bade volume par. VPS ka hissa girta jata hai. Isliye SES
   rate ($0.10 vs $0.16, à la carte vs Essentials) **sabse bada** lever hai.

### Jo table mein nahi hai (optional / later)

| Cheez | Kab | Monthly |
|---|---|---|
| **SES dedicated IP** | 250k+ emails/day, ya deliverability issue | **+$25** |
| **Neon paid** (1 GB cross) | ~10,000+ users | +$19 |
| **Cloudflare Pro** | optional | +$20 |
| **Sentry / error tracking** | 500+ customers | +$26 |
| **Marketing** (ads, content) | launch ke baad | tumhara call |
| **LLM tokens** (Agent feature) | jab agent ship karo | variable, per-plan quota |

### ⚠️ Sabse sasta production setup — exact

| Cheez | Kya | Monthly |
|---|---|---|
| VPS | aapka existing Windows Server | **already paid** |
| Neon | free tier | **$0** |
| SES | à la carte, 4,000 emails/mo | **$0.40** |
| SNS + SQS | free tier | **$0** |
| Domain | already | **$0** |
| **AWS ka extra bill** | | **~$0.50-2** |
| **Total incremental** | | **₹50-170/mo** |

Matlab: **production par jaane ka asli kharcha lagbhag kuch nahi hai.** Paisa tab
lagta hai jab emails badhte hain — aur wo kharcha revenue ke saath badhta hai.

### ⚠️ Do chhupi hui fees

| Fee | Kitna | Kab |
|---|---|---|
| **Forex markup** AWS bill par (Indian card) | **3-3.5%** | har mahine; INR billing enable karo to bach jayega |
| **GST on AWS** (Indian billing address) | **18%** | AWS India invoice par; ye input credit mil jata hai agar tum GST-registered ho |

$21 ka bill par forex markup ~$0.70. Chhota, magar ignore mat karo — bade bills par
$8,839 × 3.5% = **$309/month**.

---

## 9. Kaam ka order — exact

### Aaj (Phase 6.5 — SES test)

| # | Kaam | Kahan | Time |
|---|---|---|---|
| 1 | Gmail recipient verify karo | SES → Identities → Email address | 2 min |
| 2 | `.env` mein 4 lines bharo | apna PC | 2 min |
| 3 | `check_ses --offline` | terminal | 1 min |
| 4 | `check_ses` | terminal | 1 min |
| 5 | `send_test --to success@simulator...` | terminal | 1 min |
| 6 | `send_test --to aapka@gmail.com` | terminal | 1 min |
| 7 | Pricing plan = à la carte confirm | SES → Pricing plan | 1 min |

**Kuch kharidna nahi, kuch banana nahi.** Sab already hai.

### Phase 7c (SNS/SQS pipeline)

| # | Kaam |
|---|---|
| 1 | SNS topic banao |
| 2 | SQS queue banao |
| 3 | SES configuration set banao |
| 4 | Event destination → SNS |
| 5 | SNS → SQS subscription |
| 6 | Queue policy (SNS ko send permission) |
| 7 | Code: worker jo SQS padhe |
| 8 | Suppression list table + check |
| 9 | Auto-pause per tenant |

### Launch se pehle

| # | Kaam |
|---|---|
| 1 | SPF + DMARC DNS records |
| 2 | Website live (product page + ToS + AUP + Privacy) |
| 3 | Company email `@testingmail2btd.net` |
| 4 | SES production access apply (5,000/day maango) |
| 5 | AWS Activate apply ($1,000) |

---

## 10. Ek page ka summary

```
KYA CHAHIYE              KAHAN SE                 KITNA        KAB
--------------------------------------------------------------------------
VPS / VM                 aapka Windows RDP        already      ✅
Python 3.11+             python.org               free         ✅
Code                     GitHub ZIP               free         ✅
Domain                   already kharida          already      ✅
AWS account              aws.amazon.com           free         ✅
IAM access key           IAM → Users              free         ✅
SES (domain verified)    SES → Mumbai             $0.10/1K     ✅
Gmail recipient verify   SES → Identities         free         ABHI
à la carte plan          SES → Pricing plan       —            ABHI
PostgreSQL               Neon free tier           $0           Phase 6.5b
SNS topic                SNS console              $0           Phase 7c
SQS queue                SQS console              $0           Phase 7c
Configuration set        SES console              $0           Phase 7c
SPF + DMARC              DNS provider             $0           launch se pehle
Production access        SES → Account dashboard  free         launch se pehle
HTTPS                    Cloudflare free          $0           Phase 8
--------------------------------------------------------------------------
NAHI CHAHIYE:  EC2 · RDS · ALB · Route 53 · Lambda · Firebase · Redis
```

---

## 11. Har cheez ka error — quick lookup

| Error | Cheez | Fix |
|---|---|---|
| `MessageRejected: not verified` | SES | recipient Gmail verify karo |
| `[FAIL] identity` | SES region | Mumbai console mein domain check karo |
| `InvalidClientTokenId` | IAM key | key mein space/newline hai |
| `Connect timeout` | Neon | unpooled endpoint use karo |
| `search_path error` | Neon | **pooled** endpoint use kar rahe ho → unpooled |
| `relation does not exist` | DB | `alembic upgrade head` chalao |
| `Throttling: Maximum sending rate exceeded` | SES sandbox | 1 email/second — ruk ke bhejo |
| email inbox mein nahi, spam mein | DNS | SPF + DMARC add karo |
| app reboot ke baad band | VPS | Task Scheduler mein "At startup" |
