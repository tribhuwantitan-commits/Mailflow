"""The dashboard page itself: one HTML file, no build step, no CDN.

Deliberately boring. The page is served as a string from this module rather than from
a template engine because it has to render on a VPS with no Node, no bundler and no
network access to a CSS CDN, and because a template directory is one more thing that
can be missing at deploy time.

All numbers come from ``/v1/organizations/{id}/stats`` using the existing session
cookie, so the page has no privileges the API does not already grant.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MailFlow</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#111; --muted:#666;
          --line:#e5e5e5; --card:#fafafa; --accent:#059669; --warn:#b45309; --bad:#b91c1c; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0b0b0c; --fg:#f2f2f3; --muted:#9a9a9f; --line:#26262a;
            --card:#141416; --accent:#34d399; --warn:#fbbf24; --bad:#f87171; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  main { max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 28px; }
  .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); }
  .card { border:1px solid var(--line); border-radius:10px; padding:16px; background:var(--card); }
  .card h2 { font-size: 12px; text-transform: uppercase; letter-spacing:.06em;
             color: var(--muted); margin: 0 0 8px; font-weight: 600; }
  .big { font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
  .unit { font-size: 13px; color: var(--muted); font-weight: 400; }
  .bar { height: 6px; border-radius: 3px; background: var(--line);
         margin-top: 10px; overflow: hidden; }
  .bar > i { display: block; height: 100%; background: var(--accent); width: 0; }
  .bar.warn > i { background: var(--warn); }
  .bar.bad > i { background: var(--bad); }
  section { margin-top: 32px; }
  section > h2 { font-size: 14px; margin: 0 0 12px; }
  ol.steps { list-style: none; margin: 0; padding: 0; }
  ol.steps li { display: flex; gap: 10px; align-items: flex-start; padding: 10px 0;
                border-bottom: 1px solid var(--line); }
  ol.steps li:last-child { border-bottom: 0; }
  .tick { width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--line);
          flex: 0 0 auto; margin-top: 2px; font-size: 11px; line-height: 15px; text-align: center; }
  .tick.on { background: var(--accent); border-color: var(--accent); color: #04120c; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; font-size: 12px; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .pill { font-size: 11px; padding: 1px 7px; border-radius: 999px;
          border: 1px solid var(--line); color: var(--muted); }
  .pill.ok { color: var(--accent); border-color: var(--accent); }
  .pill.bad { color: var(--bad); border-color: var(--bad); }
  .spark { display:flex; align-items:flex-end; gap:3px; height:60px; margin-top:12px; }
  .spark > i { flex:1; background: var(--accent); border-radius: 2px 2px 0 0;
               min-height:2px; opacity:.85; }
  .note { color: var(--muted); font-size: 12px; margin-top: 8px; }
  .empty { color: var(--muted); font-size: 13px; padding: 12px 0; }
  .err { color: var(--bad); font-size: 13px; }
</style>
</head>
<body>
<main>
  <h1>MailFlow</h1>
  <div class="sub" id="who">Loading…</div>

  <div class="grid">
    <div class="card">
      <h2>Today</h2>
      <div class="big" id="daily">–</div>
      <div class="bar" id="daily-bar"><i></i></div>
    </div>
    <div class="card">
      <h2>This month</h2>
      <div class="big" id="monthly">–</div>
      <div class="bar" id="monthly-bar"><i></i></div>
    </div>
    <div class="card">
      <h2>Bounce rate</h2>
      <div class="big" id="bounce">–</div>
      <div class="note" id="bounce-note"></div>
    </div>
    <div class="card">
      <h2>Complaint rate</h2>
      <div class="big" id="complaint">–</div>
      <div class="note" id="complaint-note"></div>
    </div>
  </div>

  <section>
    <h2>Get set up</h2>
    <ol class="steps" id="steps"><li class="empty">Loading…</li></ol>
  </section>

  <section>
    <h2>Last 14 days</h2>
    <div class="spark" id="spark"></div>
    <div class="note" id="spark-note"></div>
  </section>

  <section>
    <h2>Recent email</h2>
    <table>
      <thead><tr><th>Subject</th><th>To</th><th>Status</th><th class="num">Created</th></tr></thead>
      <tbody id="rows"><tr><td colspan="4" class="empty">Loading…</td></tr></tbody>
    </table>
  </section>
</main>
<script>
const fmt = n => new Intl.NumberFormat().format(n);
const pct = n => (n * 100).toFixed(2) + "%";
const when = s => s ? new Date(s).toLocaleString() : "—";

function bar(el, used, limit) {
  if (!limit) return;
  const ratio = Math.min(1, used / limit);
  el.querySelector("i").style.width = (ratio * 100) + "%";
  el.className = "bar" + (ratio >= 1 ? " bad" : ratio >= 0.8 ? " warn" : "");
}

async function json(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new Error(res.status === 401 ? "Please sign in again." : "Request failed.");
  return res.json();
}

(async () => {
  try {
    const orgs = await json("/v1/organizations");
    if (!orgs.length) {
      document.getElementById("who").textContent =
        "No organisation yet — create one through the API to get started.";
      return;
    }
    const org = orgs[0];
    const [s, mails] = await Promise.all([
      json(`/v1/organizations/${org.id}/stats`),
      json(`/v1/organizations/${org.id}/emails?limit=10`)
    ]);

    document.getElementById("who").textContent =
      `${org.name} · ${s.plan} plan`;

    document.getElementById("daily").innerHTML =
      `${fmt(s.used.daily_emails)} <span class="unit">of ${fmt(s.limit.daily_emails)}</span>`;
    bar(document.getElementById("daily-bar"), s.used.daily_emails, s.limit.daily_emails);

    document.getElementById("monthly").innerHTML =
      `${fmt(s.used.monthly_emails)} <span class="unit">of ${fmt(s.limit.monthly_emails)}</span>`;
    bar(document.getElementById("monthly-bar"), s.used.monthly_emails, s.limit.monthly_emails);

    const d = s.deliverability;
    document.getElementById("bounce").textContent = d.judged ? pct(d.bounce_rate) : "—";
    document.getElementById("bounce-note").textContent = d.judged
      ? `${fmt(d.bounced)} of ${fmt(d.judged)} judged sends · ${d.window_days}d window`
      : "No delivery data yet";
    document.getElementById("complaint").textContent =
      d.delivered ? pct(d.complaint_rate) : "—";
    document.getElementById("complaint-note").textContent = d.delivered
      ? `${fmt(d.complained)} complaints · ${fmt(d.suppressed)} suppressed`
      : "No delivery data yet";

    const steps = document.getElementById("steps");
    steps.innerHTML = s.activation.steps.map(step => `
      <li><span class="tick ${step.done ? "on" : ""}">${step.done ? "✓" : ""}</span>
          <span>${step.label}</span></li>`).join("");

    const max = Math.max(1, ...s.volume.map(p => p.emails));
    document.getElementById("spark").innerHTML = s.volume.map(p =>
      `<i style="height:${Math.max(2, p.emails / max * 58)}px" title="${p.day}: ${p.emails}"></i>`
    ).join("");
    const total = s.volume.reduce((sum, p) => sum + p.emails, 0);
    document.getElementById("spark-note").textContent = `${fmt(total)} emails in 14 days`;

    const rows = document.getElementById("rows");
    rows.innerHTML = mails.length ? mails.map(m => {
      const tone = m.status === "delivered" ? "ok" : m.status === "bounced" ? "bad" : "";
      return `<tr><td>${m.subject}</td><td>${m.to.join(", ")}</td>
          <td><span class="pill ${tone}">${m.status}</span></td>
          <td class="num">${when(m.created_at)}</td></tr>`;
    }).join("")
      : `<tr><td colspan="4" class="empty">Nothing yet. Send your first email.</td></tr>`;
  } catch (err) {
    document.getElementById("who").innerHTML =
      `<span class="err">${err.message}</span>`;
  }
})();
</script>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page() -> HTMLResponse:
    """Serve the page; the data behind it is fetched with the session cookie."""
    return HTMLResponse(
        PAGE,
        headers={
            "Cache-Control": "no-store",
            # The page inlines its script and style, and nothing else is allowed to run.
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
