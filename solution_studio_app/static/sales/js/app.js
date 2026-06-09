/* Sales Intelligence — Frontend */

// ── State ───────────────────────────────────────────────────────────────────
let _activeTab = 'pricing';
let _tabStartTime = null;
let _clickCount   = 0;
document.addEventListener('click', () => { _clickCount++; });
let _pricingLoaded  = false;
let _cpqLoaded      = false;
let _nbcoLoaded     = false;
let _accountsLoaded = false;
let _genieReady     = false;
let _genieTyping    = false;

// cached API data for Genie context
let _kpiData      = null;
let _pricingData  = null;
let _quotesData   = null;
let _nbcoData     = null;
let _accountsData = null;

// ── Helpers ──────────────────────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function fmt$(n)  { return '$' + Number(n).toLocaleString(); }
function fmtK(n)  { return n >= 1000 ? '$' + (n/1000).toFixed(1) + 'K' : '$' + n; }
function fmtM(n)  { return '$' + Number(n).toFixed(1) + 'M'; }
function esc(s)   { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function healthColor(score) {
  if (score >= 80) return '#4CAF7D';
  if (score >= 60) return '#F5A623';
  return '#E05252';
}
function healthPill(score) {
  if (score >= 80) return `<span class="pill pill-green">${score}</span>`;
  if (score >= 60) return `<span class="pill pill-yellow">${score}</span>`;
  return `<span class="pill pill-red">${score}</span>`;
}

// ── Page time + click logging ─────────────────────────────────────────────────
async function _logPageTime(page, seconds) {
  if (seconds < 1) return;
  const clicks = _clickCount;
  _clickCount = 0;
  try {
    await fetch('/sales/api/log-page-time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, seconds_spent: seconds, click_count: clicks }),
    });
  } catch (_) {}
}

// ── Tab Switching ─────────────────────────────────────────────────────────────
function switchTab(tab) {
  if (_tabStartTime !== null && tab !== _activeTab) {
    _logPageTime(_activeTab, Math.floor((Date.now() - _tabStartTime) / 1000));
  }

  document.querySelectorAll('.nav-tab, .nav-ai-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('hidden', p.id !== `tab-${tab}`);
  });
  _activeTab = tab;
  _tabStartTime = Date.now();

  if (tab === 'pricing'  && !_pricingLoaded)  { _pricingLoaded  = true; loadPricing(); }
  if (tab === 'cpq'      && !_cpqLoaded)      { _cpqLoaded      = true; loadCpq(); }
  if (tab === 'nbco'     && !_nbcoLoaded)     { _nbcoLoaded     = true; loadNbco(); }
  if (tab === 'accounts' && !_accountsLoaded) { _accountsLoaded = true; loadAccounts(); }
  if (tab === 'genie') { openGeniePanel(); return; }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadAppConfig();
  loadKpis();
  switchTab('pricing');
  showTutorialIfNew();
  window.addEventListener('beforeunload', () => {
    if (_tabStartTime !== null) {
      const seconds = Math.round((Date.now() - _tabStartTime) / 1000);
      navigator.sendBeacon('/sales/api/log-page-time',
        new Blob([JSON.stringify({ page: _activeTab, seconds_spent: seconds, click_count: _clickCount })],
                 { type: 'application/json' }));
    }
  });
});

function showTutorialIfNew() {
  if (!localStorage.getItem('sales-tutorial-seen')) {
    document.getElementById('tut-overlay').classList.remove('hidden');
  }
}
function dismissTutorial() {
  localStorage.setItem('sales-tutorial-seen', '1');
  document.getElementById('tut-overlay').classList.add('hidden');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') dismissTutorial(); });

// ── App Config (branding) ─────────────────────────────────────────────────────
async function loadAppConfig() {
  try {
    const d = await (await fetch('/sales/api/config')).json();
    if (d.company_name) {
      document.title = d.company_name + ' — Sales Intelligence';
      const nameEl = document.querySelector('.nav-brand-name');
      if (nameEl) nameEl.textContent = d.company_name + ' — Sales';
      fetch(`https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(d.company_name)}`)
        .then(r => r.json())
        .then(results => {
          if (!results || !results[0] || !results[0].domain) return;
          const img = document.createElement('img');
          img.alt = d.company_name;
          img.style.cssText = 'width:24px;height:24px;border-radius:5px;object-fit:contain;flex-shrink:0;';
          img.onload = () => {
            const icon = document.querySelector('.nav-brand-icon');
            if (icon) icon.replaceWith(img);
            const nameEl = document.querySelector('.nav-brand-name');
            if (nameEl) nameEl.textContent = 'Sales Intelligence';
          };
          img.onerror = () => {};
          img.src = `https://cdn.brandfetch.io/domain/${results[0].domain}?c=1idGdcDDyuPmwhnhURl`;
        }).catch(() => {});
    }
  } catch (_) {}
}

// ── Global KPIs ───────────────────────────────────────────────────────────────
async function loadKpis() {
  try {
    const d = await (await fetch('/sales/api/kpis')).json();
    _kpiData = d;
    setText('gkpi-pipeline',   d.pipeline_value);
    setText('gkpi-winrate',    d.win_rate);
    setText('gkpi-deal',       d.avg_deal_size);
    setText('gkpi-price-real', d.price_realization);
    setText('gkpi-quota',      d.quota_attainment);
    setText('gkpi-rev-opp',    d.revenue_opportunity);
    setText('gkpi-csat',       d.csat);
  } catch (_) {}
}

// ══════════════════════════════════════════════════════════════════════════════
// DYNAMIC PRICING
// ══════════════════════════════════════════════════════════════════════════════
async function loadPricing() {
  try {
    const d = await (await fetch('/sales/api/pricing')).json();
    _pricingData = d;

    // Metric tiles
    setText('pr-rev-opp',   d.revenue_opportunity);
    setText('pr-rev-opp-d', '↑ identifiable this quarter');
    setText('pr-gap',       d.avg_price_gap);
    setText('pr-under',     d.items_underpriced);
    setText('pr-under-d',   d.items_underpriced + ' of ' + d.total_items + ' SKUs below market');
    setText('pr-accuracy',  d.model_accuracy);

    // Product table
    const tbody = document.getElementById('pricing-tbody');
    tbody.innerHTML = d.products.map(p => {
      const varPct = parseFloat(p.variance);
      const varClass = varPct > 0 ? 'color:#4CAF7D' : varPct < 0 ? 'color:#E05252' : '';
      const varSign  = varPct > 0 ? '+' : '';
      const elastClass = parseFloat(p.elasticity) < 0.7 ? 'pill-green' : parseFloat(p.elasticity) < 1.2 ? 'pill-yellow' : 'pill-red';
      const elastLabel = parseFloat(p.elasticity) < 0.7 ? 'Low' : parseFloat(p.elasticity) < 1.2 ? 'Med' : 'High';
      return `<tr>
        <td style="font-weight:600;color:#f0f0f0;">${p.name}</td>
        <td style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;">${fmt$(p.current_price)}</td>
        <td style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;font-weight:700;color:#818cf8;">${fmt$(p.recommended_price)}</td>
        <td style="${varClass};font-weight:700;font-size:12px;">${varSign}${varPct.toFixed(1)}%</td>
        <td><span class="pill ${elastClass}">${elastLabel} (${p.elasticity})</span></td>
        <td><button class="btn-apply" onclick="applyPrice('${p.id}',this)">Apply</button></td>
      </tr>`;
    }).join('');

    // Rules
    const rulesEl = document.getElementById('pricing-rules');
    rulesEl.innerHTML = d.rules.map(r => `
      <div style="background:#242424;border:1px solid #2e2e38;border-radius:8px;padding:10px 12px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <div style="width:8px;height:8px;border-radius:50%;background:${r.color};flex-shrink:0;"></div>
          <span style="font-size:12px;font-weight:700;color:#f0f0f0;">${r.title}</span>
        </div>
        <div style="font-size:11.5px;color:#9ca3af;line-height:1.5;">${r.desc}</div>
      </div>`).join('');

    // Sparkline
    renderPriceSparkline(d.sparkline);
  } catch (_) {}
}

function applyPrice(id, btn) {
  btn.textContent = '✓ Applied';
  btn.style.background = 'rgba(76,175,125,0.15)';
  btn.style.borderColor = 'rgba(76,175,125,0.3)';
  btn.style.color = '#4CAF7D';
  btn.disabled = true;
}

function renderPriceSparkline(data) {
  if (!data || !data.length) return;
  const maxVal = Math.max(...data.map(d => Math.max(d.market, d.internal)));
  const minVal = Math.min(...data.map(d => Math.min(d.market, d.internal)));
  const range  = maxVal - minVal || 1;
  const W = 280, H = 80, PAD = 6;
  const cx = (i) => PAD + (i / (data.length - 1)) * (W - PAD * 2);
  const cy = (v) => H - PAD - ((v - minVal) / range) * (H - PAD * 2);

  const mkPath = (key, color, dash) => {
    const pts = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${cx(i)},${cy(d[key])}`).join(' ');
    return `<path d="${pts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
  };

  const labels = data.map((d, i) => i % 2 === 0 ? `<text x="${cx(i)}" y="${H + 2}" font-size="9" fill="#6b7280" text-anchor="middle">${d.label}</text>` : '').join('');

  document.getElementById('price-sparkline').innerHTML = `
    <svg viewBox="0 0 ${W} ${H + 14}" width="100%" style="overflow:visible;">
      ${mkPath('market', '#6366f1', '')}
      ${mkPath('internal', '#f59e0b', '4,3')}
      ${labels}
    </svg>
    <div style="display:flex;gap:14px;margin-top:6px;font-size:10.5px;color:#6b7280;">
      <span style="display:flex;align-items:center;gap:5px;"><span style="display:inline-block;width:16px;height:2px;background:#6366f1;border-radius:1px;"></span>Market Index</span>
      <span style="display:flex;align-items:center;gap:5px;"><span style="display:inline-block;width:16px;height:2px;background:#f59e0b;border-radius:1px;border-bottom:2px dashed #f59e0b;height:0;"></span>Internal Price</span>
    </div>`;
}

// ══════════════════════════════════════════════════════════════════════════════
// CPQ
// ══════════════════════════════════════════════════════════════════════════════
const PRODUCT_PRICES = {
  pump:     { name: 'Industrial Pump Series A',   unit: 4250 },
  hydraulic:{ name: 'Hydraulic Manifold Pro',     unit: 1890 },
  valve:    { name: 'Precision Valve Kit',         unit: 340  },
  filter:   { name: 'Filter Assembly Bundle',      unit: 890  },
  actuator: { name: 'Actuator Control Module',     unit: 2100 },
  sensor:   { name: 'Sensor Array Unit',           unit: 560  },
};
const SEG_DISCOUNT = { enterprise: 0.05, midmarket: 0.03, smb: 0 };
let _cpqQuoteNum = 891;
let _cpqQuote = null;

async function loadCpq() {
  try {
    const d = await (await fetch('/sales/api/quotes')).json();
    _quotesData = d;
    setText('cpq-pipeline-count', d.quotes.length + ' open');
    const tbody = document.getElementById('cpq-pipeline-tbody');
    tbody.innerHTML = d.quotes.map(q => {
      const stageClass = q.stage === 'Approval' ? 'pill-yellow' : q.stage === 'Negotiation' ? 'pill-blue' : q.stage === 'Sent' ? 'pill-teal' : 'pill-grey';
      return `<tr>
        <td style="font-family:'SF Mono','Fira Code',monospace;font-size:11px;color:#818cf8;">${q.id}</td>
        <td style="font-weight:600;">${q.account}</td>
        <td style="color:#9ca3af;font-size:12px;">${q.product}</td>
        <td style="font-weight:700;">${fmt$(q.value)}</td>
        <td><span class="pill ${stageClass}">${q.stage}</span></td>
        <td style="color:#9ca3af;font-size:12px;">${q.close_date}</td>
      </tr>`;
    }).join('');
  } catch (_) {}
}

function cpqUpdate() {
  const qtyEl = document.getElementById('cpq-qty');
  const discEl = document.getElementById('cpq-discount');
  setText('cpq-qty-val', qtyEl.value);
  setText('cpq-discount-val', discEl.value + '%');
  // Update slider gradient
  const qPct = ((qtyEl.value - 1) / 499 * 100).toFixed(1) + '%';
  const dPct = (discEl.value / 25 * 100).toFixed(1) + '%';
  qtyEl.style.setProperty('--pct', qPct);
  discEl.style.setProperty('--pct', dPct);
}

function generateQuote() {
  const account = document.getElementById('cpq-account').value;
  const productKey = document.getElementById('cpq-product').value;
  const qty = parseInt(document.getElementById('cpq-qty').value);
  const segment = document.getElementById('cpq-segment').value;
  const region  = document.getElementById('cpq-region').value;
  const discOverride = parseInt(document.getElementById('cpq-discount').value) / 100;

  if (!account) { alert('Please select an account.'); return; }
  if (!productKey) { alert('Please select a product line.'); return; }

  const btn = document.getElementById('cpq-generate-btn');
  btn.disabled = true;
  btn.innerHTML = '<div class="typing-ind" style="margin:0 auto;"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';

  setTimeout(() => {
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Generate Quote`;

    const prod  = PRODUCT_PRICES[productKey];
    const segDisc = SEG_DISCOUNT[segment] || 0;
    const volDisc = qty >= 200 ? 0.08 : qty >= 100 ? 0.05 : qty >= 50 ? 0.03 : 0;
    const totalDisc = Math.min(discOverride || (segDisc + volDisc), 0.25);
    const listTotal = prod.unit * qty;
    const discAmt   = Math.round(listTotal * totalDisc);
    const netTotal  = listTotal - discAmt;
    const shipping  = Math.round(netTotal * 0.012);
    const tax       = Math.round(netTotal * 0.072);
    const grandTotal = netTotal + shipping + tax;

    _cpqQuoteNum++;
    const quoteId   = `QUOTE-2025-0${_cpqQuoteNum}`;
    const needsAppr = totalDisc > 0.1 || grandTotal > 100000;
    _cpqQuote = { quoteId, account, prod, qty, region, segment, listTotal, discAmt, totalDisc, netTotal, shipping, tax, grandTotal, needsAppr };

    setText('cpq-quote-id',     quoteId);
    setText('cpq-quote-status', `${account} · ${region} · ${segment.charAt(0).toUpperCase()+segment.slice(1)}`);

    const badgeEl = document.getElementById('cpq-approval-badge');
    badgeEl.style.display = '';
    badgeEl.className = `pill ${needsAppr ? 'pill-yellow' : 'pill-green'}`;
    badgeEl.textContent = needsAppr ? 'Approval Required' : 'Auto-Approved';

    document.getElementById('cpq-quote-body').innerHTML = `
      <div class="quote-line"><span class="quote-line-label">${prod.name} × ${qty}</span><span class="quote-line-val">${fmt$(listTotal)}</span></div>
      ${totalDisc > 0 ? `<div class="quote-line"><span class="quote-line-label" style="color:#F5A623;">Volume + Segment Discount (${(totalDisc*100).toFixed(0)}%)</span><span class="quote-line-val" style="color:#F5A623;">−${fmt$(discAmt)}</span></div>` : ''}
      <div class="quote-line"><span class="quote-line-label">Net Product Total</span><span class="quote-line-val">${fmt$(netTotal)}</span></div>
      <div class="quote-line"><span class="quote-line-label">Shipping &amp; Handling</span><span class="quote-line-val">${fmt$(shipping)}</span></div>
      <div class="quote-line"><span class="quote-line-label">Sales Tax (7.2%)</span><span class="quote-line-val">${fmt$(tax)}</span></div>
      <div class="quote-line" style="margin-top:4px;padding-top:12px;border-top:1px solid rgba(99,102,241,0.2);">
        <span style="font-size:13px;font-weight:700;color:#f0f0f0;">Grand Total</span>
        <span class="quote-total-val">${fmt$(grandTotal)}</span>
      </div>
      <div style="margin-top:10px;padding:8px 10px;background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.12);border-radius:7px;font-size:11px;color:#9ca3af;">
        AI Guidance: ${totalDisc >= 0.15 ? `⚠ Discount exceeds 15% — manager approval required. Consider bundling support contract to improve margin.` : totalDisc >= 0.07 ? `Competitive discount applied. Standard approval flow triggered. Win probability: 74%.` : `Optimal pricing range. Estimated win probability: 82%. No approval required.`}
      </div>`;

    const actEl = document.getElementById('cpq-quote-actions');
    actEl.style.display = 'flex';
    actEl.innerHTML = `
      <button class="btn-primary" onclick="openEmailModal()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="2,4 12,13 22,4"/></svg>
        Send via Email
      </button>
      ${needsAppr ? `<button class="btn-approve" onclick="this.textContent='✓ Submitted';this.disabled=true;">Submit for Approval</button>` : ''}
      <button class="btn-secondary" onclick="this.textContent='✓ Saved';this.disabled=true;">Save Draft</button>`;

  }, 1800 + Math.random() * 1200);
}

function openEmailModal() {
  if (!_cpqQuote) return;
  const q = _cpqQuote;
  const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  const discLine = q.totalDisc > 0
    ? `Volume + Segment Discount (${(q.totalDisc * 100).toFixed(0)}%):    -${fmt$(q.discAmt)}\n` : '';
  const approvalNote = q.needsAppr
    ? 'Note: This quote requires manager approval before finalization.'
    : 'This quote has been auto-approved and is ready to execute.';
  const sep = '─'.repeat(44);
  const emailBody =
    `Dear ${q.account} Team,\n\n` +
    `Please find your customized quote from our sales team below.\n\n` +
    `QUOTE SUMMARY\n${sep}\n` +
    `Quote Number:  ${q.quoteId}\n` +
    `Date:          ${today}\n` +
    `Account:       ${q.account}\n` +
    `Region:        ${q.region}\n` +
    `Segment:       ${q.segment.charAt(0).toUpperCase() + q.segment.slice(1)}\n\n` +
    `LINE ITEMS\n${sep}\n` +
    `${q.prod.name} × ${q.qty}:  ${fmt$(q.listTotal)}\n` +
    discLine +
    `Net Product Total:          ${fmt$(q.netTotal)}\n` +
    `Shipping & Handling:        ${fmt$(q.shipping)}\n` +
    `Sales Tax (7.2%):           ${fmt$(q.tax)}\n` +
    `${sep}\n` +
    `GRAND TOTAL:                ${fmt$(q.grandTotal)}\n\n` +
    `${approvalNote}\n\n` +
    `This quote is valid for 30 days from the date above. Please reply to this email or\n` +
    `contact your account manager with any questions.\n\n` +
    `Best regards,\nSales Team`;

  const contactEmail = q.account.toLowerCase().replace(/[^a-z0-9]+/g, '.').replace(/^\.+|\.+$/g, '') + '@example.com';
  document.getElementById('email-to').value = contactEmail;
  document.getElementById('email-subject').value = `Quote ${q.quoteId} — ${q.prod.name} (${q.qty} units)`;
  document.getElementById('email-body').value = emailBody;
  const modal = document.getElementById('email-modal-overlay');
  modal.classList.remove('hidden');
}

function closeEmailModal() {
  document.getElementById('email-modal-overlay').classList.add('hidden');
}

function sendQuoteEmail() {
  const btn = document.getElementById('email-send-btn');
  btn.disabled = true;
  btn.innerHTML = `<span style="display:flex;align-items:center;gap:6px;"><div class="typing-ind" style="margin:0"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>Sending…</span>`;
  setTimeout(() => {
    btn.innerHTML = '✓ Email Sent';
    btn.style.background = '#22c55e';
    setTimeout(() => closeEmailModal(), 1400);
  }, 1400);
}

// ══════════════════════════════════════════════════════════════════════════════
// NEXT BEST COMMERCIAL OFFER
// ══════════════════════════════════════════════════════════════════════════════
async function loadNbco() {
  try {
    const d = await (await fetch('/sales/api/recommendations')).json();
    _nbcoData = d;
    setText('nbco-opps',       d.total_opportunities);
    setText('nbco-uplift',     d.total_uplift);
    setText('nbco-churn',      d.churn_risk_count);
    setText('nbco-confidence', d.avg_confidence);
    renderNbcoCards(d.top3);
    renderNbcoTable(d.all);
  } catch (_) {}
}

function renderNbcoCards(top3) {
  document.getElementById('nbco-cards').innerHTML = top3.map(r => `
    <div class="reco-card">
      <div class="reco-priority-badge reco-priority-${r.priority.toLowerCase()}">${r.priority} Priority</div>
      <div class="reco-account">${r.account}</div>
      <div class="reco-arr">Current ARR: ${r.arr} · CSM: ${r.csm}</div>
      <div class="reco-offer">${r.offer}</div>
      <div style="display:flex;justify-content:space-between;align-items:flex-end;">
        <div>
          <div class="reco-uplift-val">${r.uplift}</div>
          <div class="reco-uplift-label">Potential Uplift</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:18px;font-weight:800;color:#818cf8;">${r.confidence}</div>
          <div style="font-size:10px;color:#6b7280;">Confidence</div>
        </div>
      </div>
      <div class="reco-actions">
        <button class="btn-primary" style="font-size:11px;padding:6px 12px;" onclick="this.textContent='✓ Queued';this.disabled=true;">Create Offer</button>
        <button class="btn-secondary" style="font-size:11px;padding:5px 10px;" onclick="this.textContent='✓ Noted';this.disabled=true;">Snooze</button>
      </div>
    </div>`).join('');
}

function renderNbcoTable(rows) {
  document.getElementById('nbco-tbody').innerHTML = rows.map(r => {
    const churnClass = r.churn === 'High' ? 'pill-red' : r.churn === 'Medium' ? 'pill-yellow' : 'pill-green';
    const confVal = parseInt(r.confidence);
    const confColor = confVal >= 80 ? '#4CAF7D' : confVal >= 65 ? '#F5A623' : '#E05252';
    return `<tr>
      <td style="font-weight:600;">${r.account}</td>
      <td><span class="pill ${r.tier === 'Enterprise' ? 'pill-blue' : r.tier === 'Strategic' ? 'pill-teal' : 'pill-grey'}">${r.tier}</span></td>
      <td style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;">${r.arr}</td>
      <td style="font-size:12px;color:#b8b8b8;max-width:220px;">${r.offer}</td>
      <td style="font-weight:700;color:#4CAF7D;">${r.uplift}</td>
      <td style="font-weight:700;color:${confColor};">${r.confidence}</td>
      <td><span class="pill ${churnClass}">${r.churn}</span></td>
      <td><button class="btn-apply" onclick="this.textContent='✓';this.disabled=true;">Create</button></td>
    </tr>`;
  }).join('');
}

function runNbcoAnalysis() {
  const btn = document.getElementById('nbco-run-btn');
  const thinking = document.getElementById('nbco-thinking');
  const alertEl  = document.getElementById('nbco-alert');
  btn.disabled = true;
  thinking.style.display = 'block';
  alertEl.style.display  = 'none';

  const steps = [
    'Analyzing account usage patterns and product adoption gaps…',
    'Scoring renewal proximity and churn signals across 847 accounts…',
    'Running propensity models against historical expansion data…',
    'Ranking offers by confidence × uplift potential…',
  ];
  let step = 0;
  const stepInterval = setInterval(() => {
    step++;
    if (step < steps.length) setText('nbco-thinking-txt', steps[step]);
  }, 900);

  setTimeout(() => {
    clearInterval(stepInterval);
    thinking.style.display = 'none';
    alertEl.style.display  = 'block';
    const alertTxt = document.getElementById('nbco-alert-txt');
    alertTxt.innerHTML = `<strong>✓ Analysis Complete</strong> — Identified 3 high-priority expansion opportunities totaling $405K uplift potential. 2 accounts flagged for churn intervention within 30 days.`;
    btn.disabled = false;
  }, 3800 + Math.random() * 1200);
}

// ══════════════════════════════════════════════════════════════════════════════
// ACCOUNT SERVICE DASHBOARD
// ══════════════════════════════════════════════════════════════════════════════
async function loadAccounts() {
  try {
    const d = await (await fetch('/sales/api/accounts')).json();
    _accountsData = d;

    setText('svc-csat',       d.csat);
    setText('svc-tickets',    d.open_tickets);
    setText('svc-tickets-d',  d.open_tickets_delta);
    const ticketsDEl = document.getElementById('svc-tickets-d');
    if (ticketsDEl) ticketsDEl.className = 'metric-delta ' + (d.open_tickets_delta.startsWith('↑') ? 'neg' : 'pos');
    setText('svc-sla',        d.sla_compliance);
    setText('svc-resolution', d.avg_resolution);

    // Escalations
    setText('svc-escalation-count', d.escalations.length + ' active');
    document.getElementById('svc-tickets-list').innerHTML = d.escalations.map(t => `
      <div class="ticket-item">
        <div class="ticket-dot" style="background:${t.priority === 'P0' ? '#E05252' : t.priority === 'P1' ? '#F5A623' : '#818cf8'};"></div>
        <div>
          <div class="ticket-title">${t.account} <span style="font-size:10px;font-weight:700;color:${t.priority === 'P0' ? '#E05252' : t.priority === 'P1' ? '#F5A623' : '#818cf8'};">[${t.priority}]</span></div>
          <div class="ticket-meta">${t.summary} · ${t.age}</div>
        </div>
      </div>`).join('');

    // Priority breakdown bars
    const total = d.ticket_breakdown.reduce((s, b) => s + b.count, 0);
    document.getElementById('svc-priority-bars').innerHTML = d.ticket_breakdown.map(b => `
      <div>
        <div style="display:flex;justify-content:space-between;margin-bottom:5px;">
          <span style="font-size:12px;color:#b8b8b8;font-weight:500;">${b.label}</span>
          <span style="font-size:12px;font-weight:700;color:#f0f0f0;">${b.count}</span>
        </div>
        <div class="health-bar">
          <div class="health-bar-fill" style="width:${(b.count/total*100).toFixed(0)}%;background:${b.color};"></div>
        </div>
      </div>`).join('');

    // Account health table
    document.getElementById('acct-tbody').innerHTML = d.accounts.map(a => `
      <tr>
        <td style="font-weight:600;">${a.name}</td>
        <td><span class="pill ${a.tier === 'Enterprise' ? 'pill-blue' : a.tier === 'Strategic' ? 'pill-teal' : 'pill-grey'}">${a.tier}</span></td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            ${healthPill(a.health)}
            <div class="health-bar" style="width:60px;">
              <div class="health-bar-fill" style="width:${a.health}%;background:${healthColor(a.health)};"></div>
            </div>
          </div>
        </td>
        <td style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;">${a.arr}</td>
        <td style="text-align:center;">${a.tickets}</td>
        <td style="color:#9ca3af;font-size:12px;">${a.renewal}</td>
        <td style="font-size:12px;color:#9ca3af;">${a.csm}</td>
        <td><span class="pill ${a.risk === 'High' ? 'pill-red' : a.risk === 'Medium' ? 'pill-yellow' : 'pill-green'}">${a.risk}</span></td>
      </tr>`).join('');
  } catch (_) {}
}

// ══════════════════════════════════════════════════════════════════════════════
// GENIE AI
// ══════════════════════════════════════════════════════════════════════════════
const GENIE_CHIPS = [
  "What's our biggest pricing opportunity?",
  'Which accounts are at churn risk?',
  'Show me the top open quotes',
  'Who has the highest expansion potential?',
  "What's our current win rate?",
];

// ── Genie chat panel ─────────────────────────────────────────────────────────
let _geniePanelOpen = false;
function toggleGeniePanel() { _geniePanelOpen ? closeGeniePanel() : openGeniePanel(); }
function openGeniePanel() {
  _geniePanelOpen = true;
  document.getElementById('genie-panel-overlay').classList.add('open');
  document.getElementById('genie-chat-panel').classList.add('open');
  if (!_genieReady) { _genieReady = true; initGenie(); }
}
function closeGeniePanel() {
  _geniePanelOpen = false;
  document.getElementById('genie-panel-overlay').classList.remove('open');
  document.getElementById('genie-chat-panel').classList.remove('open');
}

function initGenie() {
  addGenieMsg('bot', `Hi! I'm <strong>Genie</strong>, your AI analytics assistant for Sales Intelligence.<br><br>I have full visibility into your pricing data, quote pipeline, account health, and commercial recommendations — ask me anything.`);
  const chipsHtml = `<div class="genie-chips" id="genie-chips-row">${GENIE_CHIPS.map(q => `<button class="genie-chip" onclick="chipQ(this,'${q.replace(/'/g,"\\'")}')">  ${q}</button>`).join('')}</div>`;
  document.getElementById('genie-msgs').insertAdjacentHTML('beforeend', chipsHtml);
}

function addGenieMsg(role, html) {
  const msgs = document.getElementById('genie-msgs');
  const row = document.createElement('div');
  row.className = `genie-msg-row ${role}`;
  const icon = role === 'bot' ? '✦' : '👤';
  row.innerHTML = `
    <div class="genie-avt ${role}">${icon}</div>
    <div class="genie-bubble ${role}">${html}</div>`;
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
  return row;
}

function chipQ(btn, q) {
  const chips = document.getElementById('genie-chips-row');
  if (chips) chips.remove();
  addGenieMsg('user', q);
  triggerGenieResponse(q);
}

function sendGenieMsg() {
  const inp = document.getElementById('genie-input');
  const q   = (inp.value || '').trim();
  if (!q || _genieTyping) return;
  inp.value = '';
  const chips = document.getElementById('genie-chips-row');
  if (chips) chips.remove();
  addGenieMsg('user', q);
  triggerGenieResponse(q);
}

function genieKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendGenieMsg(); }
}

async function triggerGenieResponse(question) {
  if (_genieTyping) return;
  _genieTyping = true;
  const typRow = addGenieMsg('bot', '<div class="typing-ind"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>');
  try {
    const data = await fetch('/sales/api/genie/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }).then(r => r.json());
    typRow.remove();
    _genieTyping = false;
    const html     = data.answer || data.error || 'No answer returned.';
    const followUps = data.follow_ups || [];
    const wrapEl   = addGenieBotMsg(html, followUps);
    fetch('/sales/api/actions/suggest', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, answer: html }),
    })
      .then(r => r.json())
      .then(actions => { if (actions.length) appendGenieActions(wrapEl, actions); })
      .catch(() => {});
  } catch (e) {
    typRow.remove();
    _genieTyping = false;
    const resp = getGenieResponse(question);
    addGenieBotMsg(resp.html, resp.followUps || []);
  }
}

function getGenieResponse(q) {
  const ql = q.toLowerCase();

  if (/(pric|margin|gap|under|recommend|opport)/.test(ql)) {
    const opp = _kpiData?.revenue_opportunity || '$2.4M';
    const gap = _pricingData?.avg_price_gap || '+6.8%';
    const under = _pricingData?.items_underpriced || '5';
    return {
      html: `Based on today's pricing analysis, there are <strong>${under} SKUs currently underpriced</strong> relative to market index, representing a <strong>${opp}</strong> revenue recovery opportunity this quarter.<br><br>The average price gap across your catalog is <strong>${gap}</strong>. Industrial Pump Series A shows the largest single-SKU opportunity at +9.4% variance — applying the AI recommendation would add ~$48K to pipeline at current run rate.<br><br>Model confidence is high (94.2%) based on 18 months of elasticity data and competitor price signals.`,
      followUps: ['Which SKU has the largest price gap vs market?', 'What is the win rate impact if I apply the pricing recommendation?', 'Show me the pricing opportunities by product line'],
    };
  }

  if (/(win|quota|attain|close|convert)/.test(ql)) {
    const wr = _kpiData?.win_rate || '38.4%';
    const qa = _kpiData?.quota_attainment || '87.2%';
    return {
      html: `Current <strong>win rate is ${wr}</strong> — up 2.1pp vs. last quarter, driven by improved discount discipline in the Enterprise segment.<br><br><strong>Quota attainment is at ${qa}</strong>, with 3 reps above 100% and 2 reps below 70% requiring coaching focus.<br><br>Win rate is highest in Americas (41%) and lowest in APAC (29%), suggesting a need to adjust competitive positioning or channel strategy in the region.`,
      followUps: ['Which reps are below 70% quota attainment?', 'How does APAC win rate compare to last quarter?', 'What discount levels correlate with highest win rates?'],
    };
  }

  if (/(churn|risk|attrition|retain|at.risk|losing)/.test(ql)) {
    const churn = _nbcoData?.churn_risk_count || '4';
    return {
      html: `I've identified <strong>${churn} accounts with elevated churn risk</strong> this quarter:<br><br>
        <strong>1. CoreMfg Inc.</strong> — 87% churn probability. Usage dropped 34% MoM, 3 unresolved P1 tickets. Recommend executive sponsorship call within 7 days.<br><br>
        <strong>2. Meridian Tech</strong> — 71% churn probability. Contract expires in 47 days, no renewal discussion initiated. CSM: schedule QBR immediately.<br><br>
        <strong>3. BlueLine Systems</strong> — 68% churn probability. Competitor evaluation underway per Gong signal. Recommend competitive battlecard + exec engagement.<br><br>Total ARR at risk: <strong>$2.1M</strong>. Intervening on all three accounts within 10 days is projected to retain 60–70% of that value.`,
      followUps: ['What is the renewal date for CoreMfg?', 'What offer should I bring to Meridian Tech?', 'Which CSM owns the BlueLine relationship?'],
    };
  }

  if (/(quote|pipeline|open|pending|approval|deal)/.test(ql)) {
    const pipeline = _kpiData?.pipeline_value || '$8.4M';
    const deal = _kpiData?.avg_deal_size || '$127K';
    return {
      html: `Your open quote pipeline contains <strong>14 active quotes</strong> totaling <strong>${pipeline}</strong>:<br><br>
        • <strong>3 quotes</strong> pending approval (&gt;10% discount or &gt;$100K value) — oldest is 4 days in queue<br>
        • <strong>5 quotes</strong> sent to customer, awaiting response (avg age: 7 days)<br>
        • <strong>4 quotes</strong> in active negotiation<br>
        • <strong>2 quotes</strong> in draft status<br><br>
        Average deal size is <strong>${deal}</strong>. Top quote by value: TechDyn Corp at $127,500 (Industrial Pump, Enterprise, 5% discount — in approval).`,
      followUps: ['Which quotes have been waiting longest for customer response?', 'What is the approval SLA for high-discount quotes?', 'Show me all quotes above $100K'],
    };
  }

  if (/(expan|best offer|next best|upsell|cross|recommend)/.test(ql)) {
    const uplift = _nbcoData?.total_uplift || '$405K';
    return {
      html: `The AI has ranked <strong>12 accounts</strong> by expansion potential this week, with a combined uplift of <strong>${uplift}</strong>:<br><br>
        🥇 <strong>TechDyn Corporation</strong> — Recommend Premium Support + Actuator Module expansion. Confidence 91%, uplift <strong>$184K</strong>. Renewal in 90 days creates urgency.<br><br>
        🥈 <strong>Vertex Manufacturing</strong> — Multi-year renewal + IoT Sensor Bundle. Confidence 87%, uplift <strong>$127K</strong>. High product usage growth signals appetite.<br><br>
        🥉 <strong>Apex Systems</strong> — Service Contract + Hydraulic Manifold Suite. Confidence 82%, uplift <strong>$94K</strong>. They've been evaluating the manifold line for 60 days.<br><br>
        Shall I generate a quote for any of these accounts?`,
      followUps: ['Generate a quote for TechDyn Corporation expansion', "What is TechDyn's current product usage trend?", 'Which accounts have renewals coming up in 90 days?'],
    };
  }

  if (/(csat|service|ticket|support|sla|satisf|nps)/.test(ql)) {
    const csat = _accountsData?.csat || '4.6/5';
    const sla  = _accountsData?.sla_compliance || '97.4%';
    return {
      html: `Current <strong>CSAT is ${csat}</strong> — above the 4.5 target across your book of business.<br><br><strong>SLA compliance is ${sla}</strong>, with 2 accounts (CoreMfg and Meridian Tech) experiencing recent SLA misses that are contributing to their elevated churn risk scores.<br><br>There are currently <strong>23 open tickets</strong>, 4 of which are escalated (1 P0, 2 P1, 1 P2). The P0 at TechDyn Corp (pump system failure) requires immediate attention — it's been open 18 hours.<br><br>Average resolution time is 1.8 days, down from 2.4 days last quarter.`,
      followUps: ['Which accounts have SLA misses this quarter?', 'What is the status of the TechDyn P0 ticket?', 'Show me all accounts with CSAT below 4.0'],
    };
  }

  if (/(help|what can|what do|tell me|overview|summar)/.test(ql)) {
    return {
      html: `I have full visibility into your <strong>Sales Intelligence</strong> data across four domains:<br><br>
        💰 <strong>Dynamic Pricing</strong> — price gap analysis, AI recommendations, elasticity models, revenue opportunity by SKU<br><br>
        📋 <strong>Configure Price Quote</strong> — open quote pipeline, approval status, discount trends, win probability<br><br>
        🎯 <strong>Next Best Commercial Offer</strong> — expansion opportunities, churn predictions, uplift potential by account<br><br>
        🤝 <strong>Account Service</strong> — health scores, ticket escalations, SLA compliance, renewal risk<br><br>
        Ask me anything about any of these areas and I'll pull the latest data.`,
      followUps: ["What's our current win rate?", 'Which accounts are at churn risk?', 'Where is the biggest pricing opportunity?'],
    };
  }

  return {
    html: `Great question. Based on current data across your pricing engine, quote pipeline, and account portfolio, here's what stands out:<br><br>
      • <strong>Pricing:</strong> ${_kpiData?.revenue_opportunity || '$2.4M'} opportunity from ${_pricingData?.items_underpriced || '5'} underpriced SKUs<br>
      • <strong>Pipeline:</strong> ${_kpiData?.pipeline_value || '$8.4M'} in active quotes with a ${_kpiData?.win_rate || '38.4%'} win rate<br>
      • <strong>Expansion:</strong> ${_nbcoData?.total_uplift || '$405K'} identified across ${_nbcoData?.total_opportunities || '12'} accounts<br>
      • <strong>Service:</strong> CSAT ${_accountsData?.csat || '4.6/5'}, ${_accountsData?.churn_risk_count || '4'} accounts at churn risk<br><br>
      Would you like me to go deeper on any of these areas?`,
    followUps: ['Show me the biggest pricing opportunities', 'Which accounts need attention this week?', "What is our current pipeline health?"],
  };
}

function addGenieBotMsg(html, followUps) {
  const msgs = document.getElementById('genie-msgs');
  const row = document.createElement('div');
  row.className = 'genie-msg-row bot';
  const avt = document.createElement('div');
  avt.className = 'genie-avt bot';
  avt.textContent = '✦';
  const wrap = document.createElement('div');
  wrap.className = 'genie-bot-wrap';
  const bubble = document.createElement('div');
  bubble.className = 'genie-bubble bot';
  bubble.innerHTML = html;
  wrap.appendChild(bubble);

  if (followUps && followUps.length) {
    const panelsRow = document.createElement('div');
    panelsRow.className = 'genie-panels-row';

    const fupPanel = document.createElement('div');
    fupPanel.className = 'fup-panel genie-panel-col';
    fupPanel.innerHTML = `<div class="fup-panel-header">Suggested Questions</div>`;
    const fupCards = document.createElement('div');
    fupCards.className = 'fup-cards';
    followUps.forEach(fu => {
      const card = document.createElement('div');
      card.className = 'fup-card';
      card.innerHTML = `<div class="fup-card-text">${esc(fu)}</div><button class="fup-ask-btn">Ask →</button>`;
      card.querySelector('.fup-ask-btn').onclick = () => {
        const inp = document.getElementById('genie-input');
        if (inp) inp.value = fu;
        sendGenieMsg();
      };
      fupCards.appendChild(card);
    });
    fupPanel.appendChild(fupCards);
    panelsRow.appendChild(fupPanel);

    const actionCol = document.createElement('div');
    actionCol.className = 'genie-action-col genie-panel-col';
    panelsRow.appendChild(actionCol);
    wrap.appendChild(panelsRow);
  }

  row.appendChild(avt);
  row.appendChild(wrap);
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
  return wrap;
}

function appendGenieActions(wrapEl, actions) {
  const target = wrapEl.querySelector('.genie-action-col') || wrapEl;
  const panel = document.createElement('div');
  panel.className = 'action-panel';
  const hdr = document.createElement('div');
  hdr.className = 'action-panel-header';
  hdr.innerHTML = `Recommended Actions`;
  panel.appendChild(hdr);
  const cards = document.createElement('div');
  cards.className = 'action-cards';
  actions.forEach(a => {
    const card = document.createElement('div');
    card.className = 'action-card';
    card.id = `sales-action-${a.id}`;
    const impact = a.impact_usd > 0 ? `$${(a.impact_usd / 1000000).toFixed(1)}M impact` : 'Process improvement';
    card.innerHTML = `
      <div class="action-priority-dot ${a.priority}"></div>
      <div class="action-card-body">
        <div class="action-card-title">${a.label}</div>
        <div class="action-card-desc">${a.description}</div>
        <div class="action-card-meta"><span class="action-impact">${impact}</span> · <span>${a.owner}</span></div>
        <div class="action-btns">
          <button class="action-approve-btn" onclick="execSalesAction('${a.id}','approved',this)">Take Action</button>
          <button class="action-dismiss-btn" onclick="execSalesAction('${a.id}','dismissed',this)">Dismiss</button>
        </div>
      </div>`;
    cards.appendChild(card);
  });
  panel.appendChild(cards);
  target.appendChild(panel);
  const msgs = document.getElementById('genie-msgs');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

function execSalesAction(actionId, outcome, btn) {
  btn.disabled = true;
  const card = document.getElementById(`sales-action-${actionId}`);
  btn.closest('.action-btns').innerHTML = outcome === 'approved'
    ? '<span style="color:#10b981;font-size:11px;font-weight:600">✓ Action taken</span>'
    : '<span style="color:#6b7280;font-size:11px">Dismissed</span>';
  if (card) card.style.opacity = '0.45';
}

// ══════════════════════════════════════════════════════════════════════════════
// INFO PANEL
// ══════════════════════════════════════════════════════════════════════════════
const INFO_SECTIONS = {
  'pricing': {
    title: 'Dynamic Pricing Engine',
    what: 'AI-driven price optimization across the product catalog — comparing internal list prices against real-time market index signals and product elasticity models to identify where pricing is leaving margin on the table or where competitive pressure requires adjustment, with one-click application to the ERP approval queue.',
    aiml: 'ML price elasticity models trained on 18 months of deal outcomes, volume data, and competitor signals generate SKU-level price recommendations with confidence scores. Market index comparisons run continuously to detect when competitor pricing moves create reoptimization opportunities. Win probability scoring prevents recommendations from pushing prices into ranges that would reduce close rates.',
    benchmark: 'McKinsey research estimates AI-powered dynamic pricing can improve margins by 2–7% in B2B industrial markets without volume loss. Amazon is the most widely cited reference for real-time dynamic pricing at scale. Companies like Uber, Delta Airlines, and major hotel chains have demonstrated that algorithmic pricing consistently outperforms manual or periodic price list updates by capturing demand signals faster.',
  },
  'pricing-table': {
    title: 'Product Price Optimization Table',
    what: 'Each row represents one SKU from the active price book. The AI Recommended price is generated by the elasticity model, factoring in market index position, recent deal win/loss patterns, and competitive pressure signals. Variance is the percentage difference between current and recommended price.',
    aiml: 'Applying a price change stages it in the approval queue with the requester, timestamp, and variance delta. Changes above 15% auto-route to VP Sales for approval. The system logs all staged and approved changes to a Delta table for audit and model feedback — continuously improving recommendations over time.',
    benchmark: 'Gartner research consistently shows that companies using AI-guided pricing achieve measurable margin improvement versus manual price list management. Salesforce and SAP CPQ platforms are widely deployed across Fortune 500 sales organizations for AI-assisted pricing. Aberdeen Group benchmarks show best-in-class pricing teams applying changes in hours versus days for average performers.',
  },
  'cpq': {
    title: 'Configure Price Quote (CPQ)',
    what: 'A guided quoting experience with AI-driven discount guidance — calculating real-time pricing based on product, volume, customer segment, and region, with intelligent discount logic that factors in win probability, margin floor, and approval routing rules.',
    aiml: 'An XGBoost model trained on 3 years of CRM deal outcomes predicts win probability in real time as a quote is configured, enabling sales reps to see the statistical impact of each discount decision. Discount policy rules are dynamically enforced so margin floors and approval thresholds are applied consistently without manual checking.',
    benchmark: 'Salesforce and Gartner research consistently show that companies using AI-guided CPQ achieve 10–15% higher win rates and 5–10% improvement in average deal size versus manual quoting. The Aberdeen Group benchmarks show best-in-class CPQ users complete quotes in hours versus days for average performers. Oracle, SAP, and Salesforce CPQ platforms are widely deployed across Fortune 500 sales organizations.',
  },
  'nbco': {
    title: 'Next Best Commercial Offer',
    what: 'ML-generated next best commercial offer recommendations for each account — synthesizing product usage, renewal proximity, engagement patterns, support history, and competitor signals to rank accounts by expansion and retention priority with confidence-scored offer narratives.',
    aiml: 'Gradient boosting churn propensity and expansion propensity models score every account nightly on their likelihood to expand or churn within 90 days. LLM-generated offer narratives translate model scores into specific, personalized action recommendations that CSMs can use directly — combining the pattern-recognition power of ML with the communication quality of generative AI.',
    benchmark: 'Bain & Company research shows a 5% increase in customer retention rates typically produces a 25–95% increase in profits — the business case for AI-prioritized retention. Forrester reports that AI-guided customer success programs achieve 15–20% higher expansion revenue rates versus reactive account management. Salesforce and Microsoft are widely cited for deploying ML-based next best action systems at scale across their own sales organizations.',
  },
  'nbco-table': {
    title: 'All Account Recommendations Table',
    what: 'The full recommendations table shows every account ranked by opportunity score — a composite of expansion propensity, uplift potential, and model confidence. Churn risk is overlaid to help CSMs prioritize accounts that need both retention and expansion attention simultaneously.',
    aiml: 'The composite opportunity model combines expansion propensity, churn risk, and model confidence into a single ranked score updated nightly. CSMs see their accounts sorted by the highest combined opportunity and risk, enabling data-driven daily planning without manual triage.',
    benchmark: 'Gainsight’s benchmarking research shows enterprise SaaS companies with mature health scoring programs achieve net dollar retention rates 15–25 points higher than peers without systematic monitoring. Forrester estimates that proactive account management driven by AI scores reduces average churn by 20–30% in enterprise software businesses. Salesforce and ServiceNow are referenced in Gartner evaluations as leaders in ML-driven customer success platforms.',
  },
  'accounts': {
    title: 'Account Service Dashboard',
    what: 'A real-time composite customer health view across the book of business — health scores built from CSAT, product usage trends, ticket volume and severity, NPS, and renewal proximity — giving CS leaders and CSMs a prioritized view of which accounts need attention before a problem becomes a churn event.',
    aiml: 'A weighted ML model continuously recalculates account health scores as new CSAT, usage, and support data flows in — identifying deteriorating accounts days or weeks before they would surface in a manual review. Automated playbooks trigger CSM tasks and escalation alerts based on score thresholds, ensuring no at-risk account slips through without human attention.',
    benchmark: 'Gainsight and Salesforce research consistently show that proactive customer success programs driven by health score monitoring achieve churn rates 20–35% lower than reactive models. Zendesk’s annual Customer Experience Trends Report highlights early warning systems as among the highest-impact investments in customer retention. Companies including Adobe, HubSpot, and Workday are widely cited for mature customer health scoring programs.',
  },
  'acct-health': {
    title: 'Account Health Scorecard',
    what: 'A composite health scorecard (0–100) for every customer account showing whether they are healthy (≥80), at-risk (60–79), or in distress (<60) — based on CSAT, product usage delta, open ticket rate, days to renewal, and engagement signals updated every 4 hours.',
    aiml: 'The composite health model uses a weighted ML ensemble — CSAT, usage trend, support ticket severity, NPS, and renewal proximity — to produce a single actionable score. Automated playbooks trigger at each threshold: CSM check-in at 70, manager escalation at 55, executive sponsor alert at 40 — ensuring interventions are calibrated to risk level without requiring manual triage.',
    benchmark: 'Gainsight’s benchmarking research shows that enterprise SaaS companies with mature health scoring programs achieve net dollar retention rates 15–25 points higher than peers without systematic health monitoring. Salesforce, ServiceNow, and Workday are referenced in Gartner Magic Quadrant evaluations as leaders in health score-driven retention. Forrester estimates that proactive account management driven by AI health scores reduces average churn by 20–30% in enterprise software businesses.',
  },
};

function openInfoPanel(key) {
  const info = INFO_SECTIONS[key];
  if (!info) return;
  setText('info-panel-title', info.title);
  document.getElementById('info-panel-body').innerHTML = `
    <div class="info-sec-block">
      <div class="info-sec-title">What This Page Shows</div>
      <div class="info-what"><p>${info.what || ''}</p></div>
    </div>
    <div class="info-sec-block">
      <div class="info-sec-title info-sec-ai">How AI &amp; ML Is Applied</div>
      <div class="info-what"><p>${info.aiml || ''}</p></div>
    </div>
    <div class="info-sec-block">
      <div class="info-sec-title info-sec-bench">Industry Benchmarks</div>
      <div class="info-what"><p>${info.benchmark || ''}</p></div>
    </div>
  `;
  document.getElementById('info-overlay').classList.remove('hidden');
}

function closeInfoPanel(e) {
  if (!e || e.target === document.getElementById('info-overlay'))
    document.getElementById('info-overlay').classList.add('hidden');
}

// ─── Sales ML Interactive Functions ─────────────────────────────────────────

function _salMlRunnerStart(btnId, thinkingId, steps, stepId, doneCallback) {
  const btn = document.getElementById(btnId);
  const thinking = document.getElementById(thinkingId);
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
  if (thinking) thinking.style.display = 'flex';
  steps.forEach((txt, i) => {
    setTimeout(() => {
      const el = document.getElementById(stepId);
      if (el) el.textContent = txt;
    }, i * 900);
  });
  setTimeout(() => {
    if (thinking) thinking.style.display = 'none';
    if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
    doneCallback();
  }, steps.length * 900 + 500);
}

function _salRenderFeatureBars(containerId, features) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = features.map(f => `
    <div class="feature-row">
      <div class="feature-label">${f.label}</div>
      <div class="feature-bar-wrap"><div class="feature-bar" id="fbar-sal-${f.label.replace(/\W/g,'')}" style="background:#6366f1;"></div></div>
      <div class="feature-pct">${f.pct}%</div>
    </div>`).join('');
  requestAnimationFrame(() => {
    features.forEach(f => {
      const b = document.getElementById('fbar-sal-' + f.label.replace(/\W/g,''));
      if (b) b.style.width = f.pct + '%';
    });
  });
}

// Win Probability Scorer — XGBoost simulation
function scoreThisDeal() {
  const steps = [
    'Loading deal parameters from CRM…',
    'Extracting 3 years of closed/won & closed/lost deal features…',
    'Running XGBoost classifier (847 historical deals)…',
    'Computing SHAP feature importance for this deal…',
    'Generating coaching recommendations…',
  ];
  _salMlRunnerStart('win-score-btn', 'win-thinking', steps, 'win-step', () => {
    const prodSel = document.getElementById('cpq-product');
    const prodVal = prodSel ? prodSel.value : '';
    const baseProb = {enterprise:72, platform:65, professional:58, starter:81}[prodVal] || 68;
    const prob = Math.min(95, Math.max(30, Math.round(baseProb + (Math.random() * 10 - 5))));

    const verdict = prob >= 70 ? {label:'Strong Opportunity', color:'#10b981'} :
                    prob >= 50 ? {label:'Competitive — Act Now', color:'#f59e0b'} :
                                 {label:'At Risk — Intervention Needed', color:'#ef4444'};

    const features = [
      {label:'Champion Engagement',      pct:28},
      {label:'Budget Confirmed',         pct:22},
      {label:'Competitive Positioning',  pct:18},
      {label:'Timeline Alignment',       pct:16},
      {label:'Executive Sponsor',        pct:10},
      {label:'Procurement Involvement',  pct:6},
    ];

    const coachChips = [
      {label:'Schedule exec sponsor briefing', color:'green'},
      {label:'Send competitive battle card', color:'amber'},
      {label:'Confirm Q3 budget lock-in date', color:'blue'},
    ];

    const el = document.getElementById('win-results');
    if (!el) return;

    const r = 38, cx = 55, cy = 55;
    const circ = 2 * Math.PI * r;

    el.innerHTML = `
      <div style="display:flex;align-items:center;gap:20px;margin-bottom:14px;flex-wrap:wrap;">
        <div style="position:relative;width:110px;height:80px;flex-shrink:0;">
          <svg width="110" height="80" viewBox="0 0 110 80">
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="8" stroke-dasharray="${circ}" stroke-dashoffset="${circ * 0.5}" stroke-linecap="round" transform="rotate(180 ${cx} ${cy})"/>
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${verdict.color}" stroke-width="8" stroke-dasharray="${circ}" stroke-dashoffset="${circ - circ * (prob / 100) * 0.5 + circ * 0.5}" stroke-linecap="round" transform="rotate(180 ${cx} ${cy})" style="transition:stroke-dashoffset 1s ease;"/>
          </svg>
          <div style="position:absolute;top:28px;left:0;width:110px;text-align:center;">
            <div style="font-size:22px;font-weight:800;color:${verdict.color};">${prob}%</div>
            <div style="font-size:9px;color:#888;">Win Prob</div>
          </div>
        </div>
        <div>
          <div style="font-size:14px;font-weight:700;color:${verdict.color};">${verdict.label}</div>
          <div style="font-size:11px;color:#aaa;margin-top:4px;">XGBoost confidence interval: ±6%<br>Based on 847 comparable deals</div>
        </div>
      </div>
      <div class="feature-importance-title">Top Win Drivers (SHAP values)</div>
      <div id="win-feat-bars"></div>
      <div class="ml-divider"></div>
      <div style="font-size:11px;color:#aaa;margin-bottom:8px;font-weight:600;">AI Deal Coach — Recommended Actions</div>
      <div class="ml-action-chips">
        ${coachChips.map(c => `<div class="ml-action-chip ${c.color}" onclick="this.style.opacity='0.4';this.textContent='✓ Queued'">${c.label}</div>`).join('')}
      </div>`;
    _salRenderFeatureBars('win-feat-bars', features);
  });
}

// Price Elasticity Simulator
const ELAS_PRODUCTS = {
  pump:     {basePrice:4800, baseCost:2900, elasticity:-1.4, baseUnits:320},
  hydraulic:{basePrice:3200, baseCost:1800, elasticity:-1.2, baseUnits:510},
  valve:    {basePrice:890,  baseCost:420,  elasticity:-1.7, baseUnits:1840},
  filter:   {basePrice:340,  baseCost:140,  elasticity:-2.1, baseUnits:3200},
  actuator: {basePrice:6200, baseCost:3400, elasticity:-1.1, baseUnits:210},
  sensor:   {basePrice:1450, baseCost:680,  elasticity:-1.5, baseUnits:890},
};

function initElasticity() {
  const sel = document.getElementById('elas-product-sel');
  const panel = document.getElementById('elas-panel');
  if (!sel || !panel) return;
  const prod = ELAS_PRODUCTS[sel.value];
  if (!prod) { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  const slider = document.getElementById('elas-price-slider');
  if (slider) {
    slider.min   = Math.round(prod.basePrice * 0.7);
    slider.max   = Math.round(prod.basePrice * 1.4);
    slider.value = prod.basePrice;
    slider.step  = Math.round(prod.basePrice * 0.01);
  }
  updateElasticity();
}

function updateElasticity() {
  const sel    = document.getElementById('elas-product-sel');
  const slider = document.getElementById('elas-price-slider');
  if (!sel || !slider) return;
  const prod = ELAS_PRODUCTS[sel.value];
  if (!prod) return;

  const price     = parseFloat(slider.value);
  const priceChg  = (price - prod.basePrice) / prod.basePrice;
  const demandChg = prod.elasticity * priceChg;
  const units     = Math.max(0, Math.round(prod.baseUnits * (1 + demandChg)));
  const revImpact = (units * price - prod.baseUnits * prod.basePrice) / 1000;
  const margin    = ((price - prod.baseCost) / price) * 100;
  const winProb   = Math.min(95, Math.max(20, Math.round(68 - priceChg * 50)));
  const demIdx    = Math.round(100 * (1 + demandChg));

  const priceEl  = document.getElementById('elas-price-val');
  const demEl    = document.getElementById('elas-demand');
  const revEl    = document.getElementById('elas-revenue');
  const marginEl = document.getElementById('elas-margin');
  const winEl    = document.getElementById('elas-winprob');

  if (priceEl)  priceEl.textContent  = '$' + price.toLocaleString();
  if (demEl)  { demEl.textContent    = demIdx;  demEl.style.color  = demIdx  >= 100 ? '#10b981' : '#ef4444'; }
  if (revEl)  { revEl.textContent    = (revImpact >= 0 ? '+' : '') + '$' + Math.abs(revImpact).toFixed(0) + 'k';
                revEl.style.color    = revImpact >= 0 ? '#10b981' : '#ef4444'; }
  if (marginEl){ marginEl.textContent= margin.toFixed(1) + '%';
                 marginEl.style.color= margin >= 40 ? '#10b981' : margin >= 25 ? '#f59e0b' : '#ef4444'; }
  if (winEl)  { winEl.textContent    = winProb + '%';
                winEl.style.color    = winProb >= 65 ? '#10b981' : winProb >= 45 ? '#f59e0b' : '#ef4444'; }
}

// Churn Risk Scanner — gradient boosting simulation
function runChurnScan() {
  const tierFilter = (document.getElementById('churn-tier-filter') || {}).value || 'all';
  const steps = [
    'Loading account usage signals and engagement data…',
    'Extracting 18-month feature vectors per account…',
    'Running GBM churn propensity model (1,247 accounts)…',
    'Filtering results by tier: ' + (tierFilter === 'all' ? 'all tiers' : tierFilter) + '…',
    'Generating top signals and recommended plays…',
  ];
  _salMlRunnerStart('churn-scan-btn', 'churn-thinking', steps, 'churn-step', () => {
    const allAccounts = [
      {name:'Apex Industrials',    tier:'Enterprise', arr:'$2.4M', score:0.87, trend:'↑', signals:['Support tickets +180%','DAU -42%','Champion left'],       action:'Executive sponsor call', acolor:'green'},
      {name:'Thornton Group',      tier:'Enterprise', arr:'$1.8M', score:0.79, trend:'↑', signals:['Renewal 45 days','Usage plateau','No expansion talks'],    action:'QBR + expansion pitch',  acolor:'green'},
      {name:'SilverBridge Co.',    tier:'Mid-Market', arr:'$0.6M', score:0.74, trend:'↑', signals:['NPS dropped 28pts','Integration errors','Budget freeze'],  action:'CSM check-in + ROI deck',acolor:'amber'},
      {name:'Cranfield Dynamics',  tier:'Enterprise', arr:'$3.1M', score:0.68, trend:'→', signals:['Competitor RFP issued','Usage -28%','Exec sponsor change'],action:'Competitive battle card', acolor:'amber'},
      {name:'Linden Partners',     tier:'Mid-Market', arr:'$0.4M', score:0.61, trend:'↑', signals:['Log-in -55%','Open tickets 12','No training'],             action:'Re-onboarding session',  acolor:'amber'},
      {name:'MeridianTech',        tier:'SMB',        arr:'$0.1M', score:0.55, trend:'→', signals:['Payment delay 14d','CSAT 3/5','No adoption'],              action:'Account manager outreach',acolor:'blue'},
      {name:'Coastal Engineering', tier:'Enterprise', arr:'$1.2M', score:0.42, trend:'↓', signals:['Expansion discussion','New champion','API usage +67%'],    action:'Upsell opportunity',     acolor:'blue'},
    ];

    const tierMap = {enterprise:'Enterprise', midmarket:'Mid-Market', smb:'SMB'};
    const ft = tierMap[tierFilter] || null;
    const accounts = ft ? allAccounts.filter(a => a.tier === ft) : allAccounts;

    const sColor = s => s >= 0.75 ? '#ef4444' : s >= 0.55 ? '#f59e0b' : '#10b981';
    const rows = accounts.map(a => `
      <tr>
        <td style="font-weight:600;">${a.name}</td>
        <td><span style="font-size:10px;padding:2px 6px;border-radius:8px;background:rgba(99,102,241,0.15);color:#818cf8;">${a.tier}</span></td>
        <td style="text-align:right;font-weight:600;">${a.arr}</td>
        <td style="text-align:center;">
          <div style="display:inline-flex;align-items:center;gap:5px;">
            <div style="width:40px;height:5px;background:rgba(255,255,255,0.1);border-radius:3px;overflow:hidden;">
              <div style="width:${Math.round(a.score*100)}%;height:100%;background:${sColor(a.score)};border-radius:3px;"></div>
            </div>
            <span style="font-size:11px;color:${sColor(a.score)};font-weight:700;">${a.score.toFixed(2)}</span>
            <span style="font-size:12px;">${a.trend}</span>
          </div>
        </td>
        <td style="font-size:11px;color:#aaa;">${a.signals.map(s=>`<span style="display:inline-block;margin:1px 2px;padding:1px 5px;background:rgba(255,255,255,0.06);border-radius:4px;">${s}</span>`).join('')}</td>
        <td><button style="font-size:10px;padding:3px 9px;border:1px solid rgba(99,102,241,0.4);background:transparent;color:#818cf8;border-radius:4px;cursor:pointer;white-space:nowrap;" onclick="this.textContent='Queued ✓';this.disabled=true;">${a.action}</button></td>
      </tr>`).join('');

    const atRisk = accounts.filter(a => a.score >= 0.7).length;
    const riskArr = accounts.filter(a => a.score >= 0.7).reduce((s,a) => s + parseFloat(a.arr.replace(/[^0-9.]/g,'')), 0);

    const el = document.getElementById('churn-results');
    if (!el) return;
    el.innerHTML = `
      <div class="ml-result-summary" style="margin-bottom:14px;">
        <div class="ml-result-kpi"><div style="font-size:18px;font-weight:700;color:#ef4444;">${atRisk}</div><div style="font-size:11px;color:#aaa;">High-Risk Accounts</div></div>
        <div class="ml-result-kpi"><div style="font-size:18px;font-weight:700;color:#f59e0b;">$${riskArr.toFixed(1)}M</div><div style="font-size:11px;color:#aaa;">ARR At Risk</div></div>
        <div class="ml-result-kpi"><div style="font-size:18px;font-weight:700;color:#6366f1;">${accounts.length}</div><div style="font-size:11px;color:#aaa;">Accounts Scanned</div></div>
      </div>
      <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
          <thead><tr style="color:#888;border-bottom:1px solid rgba(255,255,255,0.08);">
            <th style="padding:6px 8px;text-align:left;">Account</th>
            <th style="padding:6px 8px;text-align:left;">Tier</th>
            <th style="padding:6px 8px;text-align:right;">ARR</th>
            <th style="padding:6px 8px;text-align:center;">Churn Score</th>
            <th style="padding:6px 8px;text-align:left;">Top Signals</th>
            <th style="padding:6px 8px;">Recommended Play</th>
          </tr></thead>
          <tbody style="color:#e0e0e0;">${rows}</tbody>
        </table>
      </div>`;
  });
}
