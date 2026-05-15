/* Finance Intelligence — Frontend */

// ── Page-time logging ───────────────────────────────────────────────────────
const _pageLoadTime = Date.now();

window.addEventListener("beforeunload", () => {
  const seconds = Math.round((Date.now() - _pageLoadTime) / 1000);
  navigator.sendBeacon("/api/log-page-time",
    new Blob([JSON.stringify({ page: "dashboard", seconds })],
             { type: "application/json" }));
});

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadKPIs();
  loadBriefing();
  loadTrend();
  loadWorkingCapital();
  initChat();

  // Record a visit (0 seconds) immediately on load
  fetch("/api/log-page-time", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page: "dashboard", seconds: 0 }),
  }).catch(() => {});
});

// ── KPI Banner ─────────────────────────────────────────────────────────────
async function loadKPIs() {
  try {
    const d = await fetch("/api/kpis").then(r => r.json());
    setText("kpi-revenue",   d.revenue    || "—");
    setText("kpi-ebitda",    d.ebitda     || "—");
    setText("kpi-margin",    d.ebitda_margin || "—");
    const vbEl = document.getElementById("kpi-vs-budget");
    if (vbEl) {
      const val = d.vs_budget || "—";
      vbEl.textContent = val;
      const num = parseFloat(String(val).replace(/[^0-9.-]/g, ""));
      vbEl.className = "kpi-value " + (num >= 0 ? "positive" : "negative");
    }
  } catch (_) {}
}

// ── Gemini Executive Briefing ───────────────────────────────────────────────
async function loadBriefing(force = false) {
  const el  = document.getElementById("briefing-text");
  const btn = document.getElementById("btn-refresh-briefing");
  if (!el) return;

  if (btn) { btn.classList.add("spinning"); btn.disabled = true; }
  el.innerHTML = `<div class="skeleton-lines">
    <div class="skel"></div><div class="skel w90"></div>
    <div class="skel w80"></div><div class="skel w70"></div>
  </div>`;

  try {
    const d = await fetch("/api/gemini/briefing", { method: "POST" }).then(r => r.json());
    const text = d.briefing || "";
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
    const paras = [];
    for (let i = 0; i < sentences.length; i += 2) {
      paras.push(sentences.slice(i, i + 2).join(" ").trim());
    }
    el.innerHTML = paras.map(p => `<p>${highlight(p)}</p>`).join("");
  } catch (_) {
    el.innerHTML = `<p>Executive briefing is unavailable. Check that GOOGLE_API_KEY and data sources are configured.</p>`;
  }
  if (btn) { btn.classList.remove("spinning"); btn.disabled = false; }
}

document.getElementById("btn-refresh-briefing")?.addEventListener("click", () => loadBriefing(true));

function highlight(text) {
  return text
    .replace(/(\$[\d,.]+[MBK%]?)/g,         '<strong>$1</strong>')
    .replace(/(\+[\d.]+%)/g,                 '<strong class="positive-text">$1</strong>')
    .replace(/(-[\d.]+%)/g,                  '<strong class="negative-text">$1</strong>');
}

// ── Trend Chart (SVG sparkline) ────────────────────────────────────────────
async function loadTrend() {
  try {
    const rows = await fetch("/api/pl-trend").then(r => r.json());
    if (!rows || !rows.length) return;
    renderTrendChart(rows);
  } catch (_) {}
}

function renderTrendChart(rows) {
  const svg = document.getElementById("trend-chart");
  if (!svg) return;

  const W = 460, H = 130, padL = 36, padR = 12, padT = 14, padB = 22;
  const cw = W - padL - padR;
  const ch = H - padT - padB;
  const n  = rows.length;
  const xs = i => padL + (i / (n - 1)) * cw;

  const revVals  = rows.map(r => parseFloat(r.revenue_m) || 0);
  const ebitVals = rows.map(r => parseFloat(r.ebitda_m)  || 0);
  const allVals  = [...revVals, ...ebitVals];
  const minV = Math.min(...allVals) * 0.9;
  const maxV = Math.max(...allVals) * 1.08;
  const ys   = v => padT + ch - ((v - minV) / (maxV - minV)) * ch;

  const pts = (vals) => vals.map((v, i) => `${xs(i)},${ys(v)}`).join(" ");
  const polyPath = (vals) => {
    const p  = vals.map((v, i) => `${i === 0 ? "M" : "L"}${xs(i)} ${ys(v)}`).join(" ");
    const fb = `L${xs(n-1)} ${padT + ch} L${padL} ${padT + ch} Z`;
    return p + " " + fb;
  };

  let html = "";
  const ticks = 3;
  for (let t = 0; t <= ticks; t++) {
    const v  = minV + (maxV - minV) * (t / ticks);
    const y  = ys(v);
    const lbl = `$${Math.round(v)}M`;
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"
               stroke="#2E2E2E" stroke-width="1" stroke-dasharray="3,3"/>
             <text x="${padL - 4}" y="${y + 4}" text-anchor="end"
               font-size="9" fill="#787868">${lbl}</text>`;
  }

  rows.forEach((r, i) => {
    if (i % 2 === 0) {
      html += `<text x="${xs(i)}" y="${H - 4}" text-anchor="middle"
                 font-size="9" fill="#787868">${r.period_key.replace("FY", "")}</text>`;
    }
  });

  html += `<path d="${polyPath(ebitVals)}" fill="rgba(76,175,125,0.07)" stroke="none"/>`;
  html += `<path d="${polyPath(revVals)}" fill="rgba(212,160,23,0.07)" stroke="none"/>`;

  html += `<polyline points="${pts(revVals)}" fill="none" stroke="#D4A017" stroke-width="2"
             stroke-linejoin="round" stroke-linecap="round"/>`;
  html += `<polyline points="${pts(ebitVals)}" fill="none" stroke="#4CAF7D" stroke-width="2"
             stroke-linejoin="round" stroke-linecap="round"/>`;

  const lasti = n - 1;
  html += `<circle cx="${xs(lasti)}" cy="${ys(revVals[lasti])}"  r="4" fill="#D4A017"/>`;
  html += `<circle cx="${xs(lasti)}" cy="${ys(ebitVals[lasti])}" r="4" fill="#4CAF7D"/>`;

  svg.innerHTML = html;
}

// ── Working Capital Table ──────────────────────────────────────────────────
async function loadWorkingCapital() {
  const tbody = document.getElementById("wc-tbody");
  if (!tbody) return;
  try {
    const rows = await fetch("/api/working-capital").then(r => r.json());
    tbody.innerHTML = rows.map(r => {
      const ccc     = parseFloat(r.ccc);
      const cccCls  = ccc <= 0 ? "ccc-positive" : "ccc-negative";
      const cccSign = ccc <= 0 ? "" : "+";
      const ar90    = parseFloat(r.ar_90_plus_pct);
      const arCls   = ar90 > 7 ? "ar-warn" : "";
      return `<tr>
        <td>${r.region}</td>
        <td>${r.dso}d</td>
        <td>${r.dpo}d</td>
        <td class="${cccCls}">${cccSign}${ccc}d</td>
        <td class="${arCls}">${ar90}%</td>
      </tr>`;
    }).join("");
  } catch (_) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Unable to load</td></tr>`;
  }
}

// ── Chat ───────────────────────────────────────────────────────────────────
function initChat() {
  const input   = document.getElementById("chat-input");
  const btnSend = document.getElementById("btn-send");

  btnSend?.addEventListener("click", () => sendMessage());
  input?.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.q;
      if (q) sendMessage(q);
    });
  });
}

let _sending = false;

async function sendMessage(overrideText) {
  if (_sending) return;
  const input   = document.getElementById("chat-input");
  const btnSend = document.getElementById("btn-send");
  const question = (overrideText || input?.value || "").trim();
  if (!question) return;

  _sending = true;
  if (input)   input.value = "";
  if (btnSend) btnSend.disabled = true;

  appendMsg("user", question);
  const typingId = appendTyping();

  try {
    const resp = await fetch("/api/genie/ask", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ question }),
    });
    const d = await resp.json();
    removeMsg(typingId);
    appendGenieAnswer(d);
  } catch (err) {
    removeMsg(typingId);
    appendMsg("system", "Sorry, I couldn't reach the Genie space. Please try again.");
  }

  _sending = false;
  if (btnSend) btnSend.disabled = false;
  if (input) input.focus();
}

// Generic Databricks-style diamond SVG for assistant avatar
const _assistantAvatarSVG = `<svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="48" height="48" rx="8" fill="#1A1A2E"/>
  <path d="M24 10L10 18v8l14 8 14-8v-8L24 10z" fill="#D4A017"/>
</svg>`;

function appendMsg(type, text) {
  const messages = document.getElementById("messages");
  if (!messages) return null;
  const id = "msg-" + Date.now();
  const isUser = type === "user";

  const div = document.createElement("div");
  div.className = `msg ${isUser ? "msg-user" : ""}`;
  div.id = id;

  const avatar = document.createElement("div");
  avatar.className = `msg-avatar ${isUser ? "user-avatar" : "system-avatar"}`;
  avatar.innerHTML = isUser ? "CFO" : _assistantAvatarSVG;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = `<p>${escHtml(text)}</p>`;

  div.appendChild(avatar);
  div.appendChild(bubble);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return id;
}

function appendGenieAnswer(d) {
  const messages = document.getElementById("messages");
  if (!messages) return;

  const id = "msg-" + Date.now();
  const div = document.createElement("div");
  div.className = "msg";
  div.id = id;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar system-avatar";
  avatar.innerHTML = _assistantAvatarSVG;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  const answerText = d.answer || "No answer returned.";
  bubble.innerHTML = `<p>${highlight(escHtml(answerText))}</p>`;

  if (d.gemini_context) {
    const ctx = document.createElement("div");
    ctx.className = "gemini-context";
    ctx.innerHTML = `<div class="gemini-context-label">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5Z" fill="#8B6914"/>
      </svg>
      Gemini context
    </div>${escHtml(d.gemini_context)}`;
    bubble.appendChild(ctx);
  }

  if (d.query?.sql) {
    const det = document.createElement("details");
    det.className = "sql-disclosure";
    det.innerHTML = `<summary>▶ View SQL</summary><pre>${escHtml(d.query.sql)}</pre>`;
    bubble.appendChild(det);
  }

  div.appendChild(avatar);
  div.appendChild(bubble);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function appendTyping() {
  const messages = document.getElementById("messages");
  if (!messages) return null;
  const id = "typing-" + Date.now();
  const div = document.createElement("div");
  div.className = "msg";
  div.id = id;
  div.innerHTML = `
    <div class="msg-avatar system-avatar">${_assistantAvatarSVG}</div>
    <div class="msg-bubble">
      <div class="typing-dots"><span></span><span></span><span></span></div>
    </div>`;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return id;
}

function removeMsg(id) {
  if (id) document.getElementById(id)?.remove();
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
