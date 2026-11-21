# Where to test: three surfaces, and what each one actually proves

Ye doc ek hi sawaal ka jawab hai: **"baar baar RDP kholna-band karna" ke bina kaam
kaise ho?** Teen jagah test ki ja sakti hain. Kaam ko teen bilkul alag hisson mein
baantna padta hai, kyunki har surface kuch alag saabit karta hai.

Sabse pehle ek baat jo sab kuch tay karti hai:

> **Android, Windows RDP, altare.gg aur labs.2z2.top — chaaron par jo bhi chalta hai,
> wo aapka aapna device ya aapka aapna server hai.**

Matlab jo bhi wahaan test hoga, wo **sirf smoke test** hoga — "chal raha hai ya nahi".
Asli test suite **canonical Linux par** chalti hai: Python 3.11, ruff, pytest, Postgres.
Wahaan chaar surfaces mein se koi rikha khaali nahi.

Ek line mein: **yahaan dekho ki chal raha hai, wahaan saabit karo ki sahi hai.**

---

## 1. GitHub Actions — naya, aur sabse zaroori

`.github/workflows/ci.yml` har push par ruff aur poori pytest chala deta hai.

| Item | Value |
|---|---|
| Kya chalta hai | `ruff check`, `ruff format --check`, `pytest -q` (157 passed, 1 skipped) |
| Kitna time | ~2–3 min |
| Kahan dekhna | GitHub → **Actions** tab → latest run |
| Kya chahiye | kuch nahi. RDP nahi, venv nahi, command nahi |
| Kya prove hota hai | code sahi hai — lint clean, tests green |
| Kya prove **nahi** hota | deploy hua ya nahi. Green tick ka matlab "ye code theek hai", "server par ja chuka hai" nahi |

**Kyun ye sabse bada farak hai:** aapke workflow mein har code change ke baad RDP
kholna padta tha — venv activate karo, `pytest` chalao, output padho. Das minute ka
kaam, aur 9 minute intezaar. Isliye steps skip hone lage. Ab push karo aur browser se
verdict padh lo. Server sirf tab chhuo jab wahan **kuch karna** ho.

> **Honest limit:** ye workflow pehli baar tab hi chalega jab `main` par pahunchega.
> `pull_request` event par bhi chalta hai — par ek naye repo par Actions pehli baar
> chalane se pehle GitHub aapse confirmation maang sakta hai (Settings → Actions).
> Agar run na dikhe: **Actions** tab → "I understand my workflows, go ahead and
> enable them".

### Ye run fail ho to

| Dikhe | Matlab | Fix |
|---|---|---|
| `ruff check` fail | line 100 se lambi, ya unused import | local: `ruff check app tests --fix` |
| `ruff format --check` fail | formatting alag hai | local: `ruff format app tests` |
| `pytest` fail | asli bug | local same test chalao, ya log bhejo |
| `Install` fail | dependency resolve nahi | `pyproject.toml` dekho |
| kuch bhi nahi dikha | Actions off hai | upar wala "enable" step |

---

## 2. GitHub Codespaces / github.dev — RDP ke bina code kholna

| | github.dev | Codespaces |
|---|---|---|
| Kaise | repo kholo, `.` dabao | Code → Codespaces → Create |
| Kya milta hai | sirf editor, browser mein | poora Ubuntu container + Python + terminal |
| Tests chala sakte? | ❌ nahi | ✅ haan |
| Kharch | ₹0, unlimited | free quota (personal account: ~60 h/month) |
| Login chahiye | GitHub (aapke laptop se, ek baar) | wahi |

**Kab kaam aata hai:** OpenCode agent ko poora repo edit karwana ho, par RDP band ho.
Codespaces mein VS Code khul jaata hai, terminal bhi, aur `pytest` bhi chalti hai.
Aapke laptop ka browser kaafi hai.

> **RDP par mat try karna.** Codespaces VS Code Web par chalta hai — uske liye GitHub
> login chahiye, aur wahi RDP ka data-centre IP block karta hai. Codespaces aapke
> laptop par hai, server par nahi.

---

## 3. Android — app ke roop mein chalao, sirf smoke test ke liye

Server chalti haalat mein Android browser se `http://<server-ip>:8000/dashboard`
khul sakta hai. Par ye **screen chhoti hai, aur port khula hai** — do dikkatein.

**Vikalp: Termux + PWA.** Termux (F-Droid se, Play Store wala purana hai) mein Python
aur uv install ho jaata hai, aur poora API phone par chal sakta hai. `localhost:8000`
phone ke andar hi rehta hai — **internet par kuch khula nahi.**

| Item | Reality check |
|---|---|
| Termux + Python 3.11 + deps | ~5–10 min, ~300 MB |
| SQLite DB (Postgres nahi) | demo ke liye theek, production nahi |
| 8 GB phone, 4 GB free | chal jaayega, par Postgres + worker ke saath tight |
| PWA (Chrome → "Add to Home screen") | icon, fullscreen, offline shell — app jaisa |
| Battery | Termux band karne par server band. Wakelock chahiye |

**Android kya prove karta hai:** UI mobile par toota nahi, quick demo, "kisi ko
dikhana". **Kya prove nahi karta:** load, Postgres, real SES, deliverability. Uske
liye phone galat jagah hai — 8 GB server bhi kaafi nahi, phone to bilkul nahi.

---

## 4. altare.gg — nahi. (Ye pehle tay ho chuka hai)

| Wajah | Detail |
|---|---|
| RAM overcommitted | aapke saath doosre tenants, RAM share hoti hai |
| Container, poora OS nahi | systemd nahi, Task Scheduler jaisa kuch nahi |
| Shared IP | aapki SES/domain reputation doosron ke saath mix |
| Teesra party AWS secrets rakhta | aapke credentials unke paas |
| AUP risk | email platform ka block ho sakta hai |

Ye pehle discuss ho chuka aur **permanently band** hai. Isliye main ise dobara
propose nahi kar raha — sirf record ke liye likh raha hoon taaki baad mein phir se
na khula jaaye.

---

## 5. labs.2z2.top — sunne mein theek, par pehle 4 sawaal

Ye aapka apna panel lagta hai. Agar hai, to ye **sabse accha option** ho sakta hai —
RDP ka poora jhanjhat khatam. Par deploy karne se pehle ye chaar cheezein pata karni
hongi, kyunki inme se koi bhi galat ho to baad mein data migration karni padegi:

| Sawaal | Kyun poochhna hai | Achha jawab |
|---|---|---|
| **Poora OS hai ya container?** | systemd nahi to service auto-start nahi hoga; yahi RDP wali dikkat dobara aayegi | poora Linux (Ubuntu 22.04/24.04), SSH milta ho |
| **Kitni RAM/disk?** | Postgres + API + 2 workers ko ~1 GB chahiye | **2 GB minimum**, 4 GB aaram |
| **Public IPv4 dedicated hai?** | shared IP = SES reputation doosron ke saath | dedicated IPv4 |
| **Kahan host hai? / kon chalata hai?** | AWS credentials aur customer email data us box par jayega | bharosa ho, ya apna hi box ho |

In chaaron ke jawab mil jaayen, to **yahi best raasta hai** — Windows ki zaroorat hi
nahi rahegi, aur `no Windows licence premium` wala aapka faisla bhi khud ba khud poora
ho jaayega.

> **Ek discipline:** agar ye box demo ban jaaye, to ise **canonical mat banao**. Code
> GitHub par rahega; box par sirf chalti hui copy. Warna wahi "server par kiye edits
> kisi repo mein nahi hain" wala trap khul jaata hai (`docs/OFFLINE-TRANSFER.md` §1).

---

## 6. Jo sirf server par ho sakta hai (aur isliye RDP ka koi vikalp nahi)

Ye chaar cheezein kisi bhi doosre surface par test nahi ho sakti. Inke liye server
chahiye — par ye **ek hi baar** ka kaam hai, roz ka nahi:

| Kaam | Kyun server par |
|---|---|
| Postgres par migrations (`alembic upgrade head`) | asli database chahiye |
| `send_test --to success@simulator.amazonses.com` | SES credentials server par hain |
| SES event → SNS → SQS → poller | asli AWS queue chahiye |
| Restart-proof (Task Scheduler / systemd) | OS-level, sirf server par |

**Isliye plan ye hai:** code ki 95% mehnat GitHub Actions aur Codespaces par. Server
par sirf ye chaar cheezein, ek baar, dhyan se.

---

## 7. Practical sequence — kis din kya

| # | Kahan | Kaam | RDP chahiye? |
|---|---|---|---|
| 1 | laptop | code push | ❌ |
| 2 | GitHub Actions | green tick dekho | ❌ |
| 3 | laptop / Codespaces | OpenCode se changes | ❌ |
| 4 | RDP | code update + `alembic upgrade head` | ✅ 5 min |
| 5 | RDP | API restart, `/health/ready` | ✅ 2 min |
| 6 | laptop | SES sandbox, domain verify | ❌ |
| 7 | RDP | `send_test` → simulator | ✅ 3 min |
| 8 | Android | demo dikhao | ❌ |

Din bhar ka kaam laptop par. RDP par **mahine mein 2–3 baar**, 10 minute.

---

## 8. Ek line ka jawab

**Tests GitHub Actions par, code Codespaces par, deploy RDP par, demo Android par.**

altare.gg — nahi. labs.2z2.top — poochho pehle, mile to RDP chhod do.
