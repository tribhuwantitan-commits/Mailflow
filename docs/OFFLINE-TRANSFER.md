# GitHub login nahi hota — offline transfer ka tareeka

Problem: RDP server ka IP **data-centre IP** hai. GitHub usse **signup bhi nahi karne
deta** aur login bhi block karta hai. Server temporary hai, to credential setup karna
bekaar hai.

Ye doc **do** cheezein deta hai: aaj kaam karne ka raasta, aur permanent fix jisme
GitHub login ki zaroorat **hi nahi padti**.

---

## 0. Pehle: ZIP aur git ka farq samajh lo

| | ZIP | `git pull` |
|---|---|---|
| Naya code aaye | **poora ZIP dobara** | ek command |
| Pata ki kaunsa version chal raha hai | filename se guess | `git log` |
| Bug aaye to purana version | ❌ | `git checkout <sha>` |
| Server par kuch badla to? | pata nahi chalega | `git status` batayega |
| Size | 411 KB | — |

**ZIP chalega, magar "kaunsa code chal raha hai" ka jawab deta rehna padega.**
Isliye har ZIP ke naam mein **commit** hota hai — jaise `MailFlow-dd03575-sources.zip`.
Aur runbook ka Step 2 usi se verify karta hai.

---

## 1. ⚠️ Sabse bada khatra — RSYNC server par `git` nahi

Server par koi git repo nahi hai. To:

| Aap kya sochoge | Asli baat |
|---|---|
| "File badal di, server par chalega" | ✅ chalega — par **git ko pata nahi** |
| "Bug fix kiya" | ❌ fix **sirf server par** hai, Arun ke paas nahi |
| Next ZIP aaya | Aapki server-side fix **chup-chaap mit jayegi** |

**Niyam:**

> **Server par sirf `.env` edit karo. Baaki kuch bhi nahi.**
>
> Kuch toota mile → Arena mein batao → fix → naya ZIP → dobara extract.

Naya ZIP nikala to:

```powershell
# Purani copy hata do, warna purani files chup-chaap reh jayengi
Remove-Item C:\apps\MailFlow -Recurse -Force
```

**`Expand-Archive` purani files delete nahi karta.** Isliye "purana code chal raha hai"
wala sabse confusing bug hota hai.

---

## 2. Aaj ka tareeka: ZIP

### ZIP kahan hai

Dropbox par, commit ke naam ke saath:

```
MailFlow-902dbd3-sources.zip    278 KB    128 files
sha256 f6f1b26a22849bdcd4f95f26620c0ad22a5883a086e7840f2c6af923f2f3def1
```

Link (Dropbox): file `MailFlow-902dbd3-sources.zip` — share link se download karo.

> Naya package banane ke liye: `./scripts/package.sh` (repo root se). Wo `git archive`
> se tree banata hai aur **usi waqt** `docs/VERSION.txt` likhta hai.

Ismein **sirf source** hai: `app/`, `tests/`, `alembic/`, `docs/`, `AGENTS.md`.
**Nahi** hai: `.venv`, `__pycache__`, `.env`, `mailflow.db`, koi bhi secret.

### RDP par extract

```powershell
New-Item -ItemType Directory -Force -Path C:\apps | Out-Null
cd C:\apps

# agar purani copy hai
if (Test-Path .\MailFlow) { Remove-Item .\MailFlow -Recurse -Force }

Expand-Archive -Path "$env:USERPROFILE\Downloads\MailFlow-902dbd3-sources.zip" -DestinationPath C:\apps
cd C:\apps\MailFlow
```

**Checkpoint** — version confirm karo:

```powershell
Get-Content .\docs\VERSION.txt
```

### ✅ `docs/VERSION.txt` — har package mein

Har ZIP mein ek chhoti file hoti hai jo batati hai **kya** hai:

```
commit: 902dbd3
branch: arena/67b5c744-mailflow
built:  2026-11-20
tests:  157 passed, 1 skipped
head:   0009_monthly_quota
source: package
```

> `source: package ... (contains uncommitted changes)` dikhe to package **sahi nahi hai** —
> dobara banao.

**Yahi aapka sabse zaroori checkpoint hai.** Agar `tests:` line `157 passed` nahi
kehti, to aap galat ZIP par ho.

---

## 3. Download ke 3 raaste

| Raasta | Kaise | Kab |
|---|---|---|
| **Dropbox link** | RDP ke browser mein link kholo | ✅ recommend |
| **RDP clipboard** | Laptop se copy, RDP mein paste (411 KB theek chalta hai) | chhota file |
| **Dropbox app** | RDP par Dropbox install (login chahiye) | baar baar chahiye to |

**Dropbox link RDP par khulega?** Data-centre IP par Dropbox aam taur par khulta hai
(GitHub se bahut zyada lenient). Agar wo bhi block ho, **clipboard** use karo — 411 KB
clipboard se aaram se jaata hai.

---

## 4. 🔧 Permanent fix: Deploy key — GitHub login hi nahi chahiye

Ye asli solution hai. Repo **private** rehta hai, aur server sirf **read** kar sakta hai.

### Kyun ye kaam karta hai

| | Username/password login | **Deploy key** |
|---|---|---|
| GitHub login | chahiye | **nahi chahiye** |
| Browser | chahiye | **nahi chahiye** |
| Data-centre IP block | hota hai | **affect nahi** |
| Kya access | account ka sab | **sirf ye ek repo, read-only** |

Ek **SSH key** server par banti hai. Uska public part GitHub par add hota hai (aap
laptop se, ek baar). Bas. Server par GitHub login kabhi nahi hota.

### Steps — aap laptop se (2 min)

GitHub → repo → **Settings** → **Deploy keys** → **Add deploy key**

- Title: `rdp-temp`
- Key: (neeche se)
- **Allow write access: ❌ unchecked** ← read-only

### Steps — RDP par (1 min)

```powershell
ssh-keygen -t ed25519 -C "rdp-temp" -f "$env:USERPROFILE\.ssh\mailflow" -N '""'
Get-Content "$env:USERPROFILE\.ssh\mailflow.pub"
```

Wo output copy karke GitHub ke Deploy key box mein paste karo.

### Phir clone (aaj se hamesha ke liye)

```powershell
$env:GIT_SSH_COMMAND = "ssh -i $env:USERPROFILE\.ssh\mailflow -o StrictHostKeyChecking=accept-new"
git clone git@github.com:tribhuwantitan-commits/Mailflow.git C:\apps\MailFlow
cd C:\apps\MailFlow
git checkout arena/67b5c744-mailflow
git log --oneline -1
```

Aur naya code aane par:

```powershell
cd C:\apps\MailFlow
git pull
```

**Checkpoint:** `git log --oneline -1` → commit sha. **Na login, na ZIP.**

> ⚠️ Ek hi key ko **do jagah** add mat karo (Deploy key + Account SSH key).
> GitHub error dega. Deploy key hi kaafi hai.

### Note: server temporary hai

Key server par rehti hai, GitHub par nahi — GitHub par sirf **public** part. Server
delete hone par key bhi chali jayegi. Naye server par **nayi key** banao aur purani
GitHub se hata do (Settings → Deploy keys → Delete).

---

## 5. ZIP vs Deploy key — kab kya

| Situation | Kya |
|---|---|
| Aaj, turant chalana hai | **ZIP** |
| RDP par OpenCode kaam karega, 2-3 baar naya code chahiye | **Deploy key** |
| Server par outbound SSH (port 22) block hai | **ZIP** hi |
| Ek exact snapshot reproduce karna hai | **ZIP** |

**Mera suggestion: aaj ZIP se chalao. Chal jaye to deploy key bana lo** — 3 minute ka
kaam hai aur uske baad ZIP ka jhanjhat khatam.

---

## 6. ✅ Har ZIP ke saath ye 6 check

Server par extract karne ke baad, **order mein**:

```powershell
cd C:\apps\MailFlow

# 1. Sahi version?
Get-Content .\docs\VERSION.txt

# 2. Koi secret ZIP mein aa gaya?
Get-ChildItem -Recurse -Force -Include .env,*.pem,*.key,cookies.txt | Select-Object FullName
#    (kuch nahi dikhna chahiye)

# 3. Purani files bachi?
Get-ChildItem -Recurse -Filter *.pyc | Measure-Object   # 0 hona chahiye

# 4. Deps install
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 5. Migration + tests
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m pytest -q
#    -> 157 passed, 1 skipped  (VERSION.txt se match karo)

# 6. Lint
.venv\Scripts\python.exe -m ruff check .
```

**Step 5 ka number VERSION.txt se match ho gaya = aap sahi code par ho.**

---

## 7. OpenCode ko kaise do (ZIP ke saath)

`AGENTS.md` aur `DEPLOY-RUNBOOK.md` **ZIP ke andar** hain, to agent ko kuch paste
karne ki zaroorat nahi:

```
C:\apps\MailFlow\AGENTS.md                 <- agent ke liye niyam
C:\apps\MailFlow\docs\DEPLOY-RUNBOOK.md    <- steps
C:\apps\MailFlow\docs\VERSION.txt          <- kaunsa version
```

Prompt:

```
C:\apps\MailFlow padho. Pehle AGENTS.md, phir docs/DEPLOY-RUNBOOK.md.
Step 3 se shuru karo. Har checkpoint par ruko aur batao.
Ye git repo nahi hai — sirf extracted source hai, to git commands mat chalao.
```

> **"Ye git repo nahi hai"** wali line zaroori hai, warna agent `git pull` chalayega
> aur confuse hoga.

---

## 8. Ek page

| | |
|---|---|
| **Aaj** | ZIP: `MailFlow-902dbd3-sources.zip` (278 KB) |
| **Banane ka command** | `./scripts/package.sh` |
| **Verify** | `docs/VERSION.txt` → `157 passed` |
| **Sabse bada khatra** | Server par edit kiya code **git mein nahi** hai |
| **Niyam** | Server par sirf `.env` edit |
| **Naya ZIP** | purani folder **delete** karke extract |
| **Permanent fix** | **Deploy key** — GitHub login nahi chahiye |
| **ZIP kab** | abhi, aur jab SSH block ho |
