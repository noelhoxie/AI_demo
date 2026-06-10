'use strict';

// ── Global State ──────────────────────────────────────────────────────────────
let _activeTab     = 'ibp';
let _clickCount    = 0;
document.addEventListener('click', () => { _clickCount++; });
let _aiActive      = false;
let _tabStartTime  = null;   // ms timestamp when current tab was entered
let _timerInterval = null;

// Chart instances
let _ibpPlanChart     = null;
let _ibpBuChart       = null;
let _invHealthChart   = null;
let _invWareChart     = null;
let _invDosChart      = null;
let _demFaChart       = null;
let _demMapeChart     = null;
let _demTrendChart    = null;
let _ordVolChart      = null;
let _ordAutoChart     = null;

// ── Chart Defaults ────────────────────────────────────────────────────────────
Chart.defaults.color            = '#6b7280';
Chart.defaults.borderColor      = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family      = 'Inter, system-ui, sans-serif';
Chart.defaults.font.size        = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#1f1f1f';
Chart.defaults.plugins.tooltip.borderColor     = 'rgba(255,255,255,0.1)';
Chart.defaults.plugins.tooltip.borderWidth     = 1;
Chart.defaults.plugins.tooltip.titleColor      = '#f0f0f0';
Chart.defaults.plugins.tooltip.bodyColor       = '#c8c8c8';
Chart.defaults.plugins.tooltip.padding         = 10;
Chart.defaults.plugins.tooltip.cornerRadius    = 8;

const BLUE   = '#1B6FEB';
const GREEN  = '#10b981';
const PURPLE = '#8b5cf6';
const AMBER  = '#f59e0b';
const RED    = '#ef4444';
const ORANGE = '#f97316';
const MUTED  = 'rgba(255,255,255,0.35)';

function _alpha(hex, a) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

// ── Drill-down Modal ───────────────────────────────────────────────────────────
// Content store: avoids embedding HTML strings in onclick attributes (breaks HTML parser)
const _drillStore = {};
let   _drillKey   = 0;

// SKU forecast error history (populated by renderDemErrorsTable)
let _skuErrorData = [];
let _skuAllData   = [];   // full unfiltered copy for filtering
let _supplierRaw  = [];   // full unfiltered supplier list for filtering

// Raw data stores for filter re-rendering
let _ibpBuRaw         = null;
let _ibpRisksRaw      = null;
let _ibpKpisRaw       = null;
let _invWarehousesRaw = null;
let _invCategoriesRaw = null;
let _invAlertsRaw     = null;
let _invKpisRaw       = null;
let _invHealthRaw     = null;
let _demMapeRaw       = null;
let _demKpisRaw       = null;
let _demFaRaw         = null;
let _demTrendRaw      = null;
let _ordKpisRaw       = null;
let _ordVolRaw        = null;
let _ordAutoRaw       = null;
let _scKpisRaw        = null;

function _storeDrill(title, content) {
  const key = 'k' + (_drillKey++);
  _drillStore[key] = { title, content };
  return key;
}

function openStoredDrill(key) {
  const d = _drillStore[key];
  if (d) openDrill(d.title, d.content);
}

function openDrill(title, content) {
  document.getElementById('drill-title').textContent = title;
  document.getElementById('drill-body').innerHTML = content;
  document.getElementById('drill-overlay').classList.remove('hidden');
  document.getElementById('drill-modal').classList.remove('hidden');
}
function closeDrill() {
  document.getElementById('drill-overlay').classList.add('hidden');
  document.getElementById('drill-modal').classList.add('hidden');
}

// ── Chart info (ℹ button) ──────────────────────────────────────────────────
const CHART_INFO = {
  'ibp-plan': {
    title: 'Consensus vs Financial Plan vs Operations Capacity',
    rows: [
      {l: 'Consensus', v: 'Average of all BU demand submissions after review'},
      {l: 'Financial Plan', v: 'CFO-approved revenue target per period'},
      {l: 'Operations Capacity', v: 'Machine & plant capacity ceiling from operations — max producible volume given confirmed capacity, labor, and tooling'},
      {l: 'Time Range', v: '18-month rolling forward view'},
      {l: 'Unit', v: '$M revenue or K Units (toggle)'},
    ],
    note: 'Gap between Consensus and Operations Capacity triggers supply risk escalation in S&OP.',
    why: 'Identifies misalignment between commercial targets and operational reality before it becomes a fulfillment crisis. The gap between consensus demand and capacity ceiling is the primary trigger for supply risk escalation in S&OP cycles.',
    benchmarks: [
      '<strong>Gartner:</strong> Top-quartile companies achieve &lt;5% variance between consensus demand and financial plan',
      '<strong>Oliver Wight:</strong> Class A S&OP requires consensus within ±3% of financial plan at the aggregate level',
      '<strong>APICS:</strong> Best-in-class S&OP planning horizons extend 18–24 months to capture capacity constraints early',
      '<strong>McKinsey:</strong> Companies with strong S&OP demand-supply alignment reduce excess inventory by 15–20%',
      '<strong>IBF:</strong> Organizations running monthly consensus meetings reduce forecast error by 10–15% vs. ad-hoc reviews',
    ],
  },
  'ibp-bu': {
    title: 'Plan Attainment by Business Unit',
    rows: [
      {l: 'Formula', v: 'Actual Revenue ÷ Plan Revenue × 100'},
      {l: 'Weighting', v: 'Proportional to BU revenue contribution'},
      {l: 'Target', v: '≥ 95% attainment'},
      {l: 'Period', v: 'Current S&OP cycle month'},
    ],
    note: 'BUs below 90% trigger a corrective action review in the next S&OP cycle.',
    why: 'Tracks execution fidelity across business units, exposing which BUs are over- or under-committing against plan. Early visibility enables corrective action before the gap compounds across the quarter.',
    benchmarks: [
      '<strong>Gartner:</strong> World-class plan attainment is ≥ 95% across BUs; industry average is ~88%',
      '<strong>APICS:</strong> Top-quartile organizations review BU attainment weekly — not just at month-end — to enable in-cycle correction',
      '<strong>IBF:</strong> BU attainment below 90% correlates with 2–4% annualized revenue leakage from missed commitments',
      '<strong>Hackett Group:</strong> Top performers link BU attainment directly to S&OP KPI scorecards reviewed at executive level',
      '<strong>Oliver Wight:</strong> Class A S&OP requires ≥ 95% performance-to-plan measured at the BU level',
    ],
  },
  'inv-health': {
    title: 'SKU Health Classification',
    rows: [
      {l: 'Healthy', v: 'DOS 15–45 days'},
      {l: 'Excess', v: 'DOS > 60 days'},
      {l: 'At-Risk', v: 'DOS < 7 days'},
      {l: 'Stockout', v: 'Zero on-hand units'},
      {l: 'DOS Formula', v: 'On-Hand Units ÷ Avg 30-day Daily Demand'},
    ],
    note: 'Classifications are recalculated nightly from WMS on-hand snapshots.',
    why: 'A single unhealthy SKU can mean a lost sale, an emergency air freight, or a write-down. This classification gives planners a prioritized action list — focus on Stockouts and At-Risk first, then right-size Excess to recover working capital.',
    benchmarks: [
      '<strong>Gartner:</strong> World-class companies maintain &lt;5% of active SKUs in excess or obsolete status',
      '<strong>APICS:</strong> Optimal DOS band for most manufactured goods is 15–45 days; consumer goods skew toward 15–30',
      '<strong>Deloitte:</strong> Excess and obsolete inventory typically represents 20–30% of working capital in discrete manufacturing',
      '<strong>Aberdeen Group:</strong> Best-in-class inventory accuracy (cycle-count based) is ≥ 99.5%',
      '<strong>Supply Chain Digest:</strong> Companies that classify SKU health nightly reduce emergency replenishment costs by 18–22%',
    ],
  },
  'inv-warehouse': {
    title: 'Warehouse Utilization by DC',
    rows: [
      {l: 'Utilization', v: 'On-Hand Pallets ÷ Max Pallet Capacity × 100'},
      {l: 'Days of Supply', v: 'On-Hand Units ÷ Avg Daily Demand'},
      {l: 'Alert Threshold', v: '> 85% utilization'},
      {l: 'Data Source', v: 'Real-time WMS feeds per DC'},
    ],
    note: 'DCs above 85% may require overflow routing or expedited outbound.',
    why: 'A DC approaching capacity limits causes pick-path congestion, overtime costs, and overflow charges. Monitoring utilization per DC allows network rebalancing decisions before service levels degrade.',
    benchmarks: [
      '<strong>CSCMP:</strong> Optimal warehouse utilization is 75–85%; above 90% significantly increases error rates and labor costs',
      '<strong>Gartner:</strong> DCs operating above 90% utilization see a 15–25% increase in pick/pack errors',
      '<strong>Prologis:</strong> Average industrial DC utilization in North America runs 82–85% in peak season',
      '<strong>MHI:</strong> Slotting optimization programs reduce travel time by 20–30% and allow 5–8% higher utilization without service impact',
      '<strong>Hackett Group:</strong> Top-quartile distribution networks rebalance DC inventory proactively when any node exceeds 80% for 3+ consecutive days',
    ],
  },
  'inv-dos': {
    title: 'Days of Supply by Category',
    rows: [
      {l: 'Formula', v: 'On-Hand Units ÷ Avg Daily Demand'},
      {l: 'Optimal Band', v: '15–45 days (shaded region)'},
      {l: 'Below Band', v: 'Stockout risk — expedite or reallocate'},
      {l: 'Above Band', v: 'Excess capital — consider markdown or redeployment'},
    ],
    note: 'Band thresholds are category-specific and set during annual S&OP policy review.',
    why: 'DOS is the most actionable inventory metric — it directly connects on-hand levels to demand rate and drives replenishment timing decisions. It is the universal language between supply chain, finance, and operations.',
    benchmarks: [
      '<strong>APICS:</strong> 15–45 days DOS is best-in-class for most discrete manufacturing categories',
      '<strong>Gartner:</strong> Top-quartile companies target &lt;30 days DOS for fast-moving SKUs; industry median is 45–60 days',
      '<strong>Aberdeen Group:</strong> Every 10-day reduction in DOS frees approximately 3–5% of tied-up working capital',
      '<strong>McKinsey:</strong> Leading manufacturers set DOS targets by ABC/XYZ segment — A/X items target 10–20 days, C/Z items 45–60 days',
      '<strong>Supply Chain Digest:</strong> Annual DOS policy reviews aligned to S&OP reduce inventory write-downs by 12–18%',
    ],
  },
  'dem-fa': {
    title: 'Forecast vs Actual',
    rows: [
      {l: 'Actuals', v: 'Confirmed shipped units from order management system'},
      {l: 'Forecast', v: 'Statistical baseline + market intelligence adjustments'},
      {l: 'Aggregation', v: 'All active SKUs rolled up to total volume'},
      {l: 'Period', v: 'Last 12 full months'},
    ],
    note: 'Statistical baseline uses exponential smoothing; market adj applied by demand planners.',
    why: 'Visualizing forecast versus actual over time surfaces systematic bias (always high or always low), seasonal blind spots, and the measurable impact of model changes — the foundation for continuous forecasting improvement.',
    benchmarks: [
      '<strong>IBF:</strong> World-class forecast accuracy ≥ 90% at product family level; ≥ 85% at SKU level',
      '<strong>Gartner:</strong> Top-quartile companies achieve 85–90% forecast accuracy at SKU level; industry average is 65–75%',
      '<strong>APICS:</strong> A 10-percentage-point improvement in forecast accuracy reduces safety stock requirements by 15–20%',
      '<strong>Hackett Group:</strong> Companies with ≥ 85% forecast accuracy reduce safety stock by 20–25% vs. peers at 70%',
      '<strong>Aberdeen:</strong> Best-in-class demand planners review forecast vs. actual weekly and adjust within the planning cycle',
    ],
  },
  'dem-mape': {
    title: 'MAPE by Category',
    rows: [
      {l: 'Formula', v: 'avg( |Actual − Forecast| ÷ Actual ) × 100'},
      {l: 'Level', v: 'Per product category'},
      {l: 'Target', v: '≤ 10% MAPE'},
      {l: 'Period', v: 'Last completed planning period'},
    ],
    note: 'Categories above 15% trigger a forecast model review with demand planning.',
    why: 'MAPE pinpoints which categories have the weakest signal-to-noise ratio and need model recalibration or increased planner attention. It is the primary KPI for holding demand planning accountable to a measurable accuracy standard.',
    benchmarks: [
      '<strong>IBF:</strong> World-class MAPE ≤ 10% at product family level; ≤ 15% at SKU level',
      '<strong>Gartner:</strong> Top-quartile companies achieve 8–12% MAPE at category level; industry median is 20–30%',
      '<strong>APICS:</strong> Highly seasonal and promotional categories typically run 30–40% MAPE without causal modeling',
      '<strong>Aberdeen:</strong> Every 5% MAPE improvement correlates with approximately 2–3% reduction in required safety stock',
      '<strong>Hackett Group:</strong> Organizations with formal MAPE review processes reduce forecast error 15–20% faster than those without',
    ],
  },
  'dem-trend': {
    title: 'MAPE Trend',
    rows: [
      {l: 'Formula', v: 'avg( |Actual − Forecast| ÷ Actual ) × 100'},
      {l: 'Window', v: 'Rolling 30-day across all active SKUs'},
      {l: 'Improvement Driver', v: 'ML model retraining on 6-week cadence'},
      {l: 'Period', v: 'Last 12 months'},
    ],
    note: 'Downward trend indicates model improvement. Spikes often correspond to new product launches.',
    why: 'Trending MAPE over time validates whether model investments, process changes, and planner interventions are actually improving accuracy — or whether drift is occurring. A flat or rising MAPE trend is an early warning that the forecasting process needs re-examination.',
    benchmarks: [
      '<strong>Gartner:</strong> Best-in-class organizations improve MAPE by 2–3 percentage points annually through disciplined process improvement',
      '<strong>IBF:</strong> Teams with structured forecast review cycles reduce MAPE 15–20% faster than those relying on ad-hoc reviews',
      '<strong>McKinsey:</strong> ML-enhanced demand forecasting reduces MAPE by 20–50% vs. traditional statistical baselines',
      '<strong>APICS:</strong> New product launches typically spike MAPE by 8–15% for 2–3 months before stabilizing',
      '<strong>Aberdeen:</strong> Companies that track MAPE trend (not just point-in-time) identify accuracy regressions 4–6 weeks earlier',
    ],
  },
  'ord-vol': {
    title: 'Order Volume — Automated vs Manual',
    rows: [
      {l: 'Automated', v: 'ERP rules-based release — no buyer intervention'},
      {l: 'Manual', v: 'Buyer-reviewed and approved before release'},
      {l: 'Unit', v: 'Count of Purchase Orders per month'},
      {l: 'Period', v: 'Last 12 months'},
    ],
    note: 'Automated orders must pass all tolerance checks (price, quantity, lead time) to release without review.',
    why: 'The split between automated and manual POs reveals buyer workload distribution, exception handling volume, and overall procurement process maturity. High manual volume indicates either poor data quality, narrow tolerance agreements, or untrained ERP rules.',
    benchmarks: [
      '<strong>Hackett Group:</strong> Top-quartile procurement organizations automate ≥ 80% of transactional PO volume',
      '<strong>Gartner:</strong> Automated PO processing costs $3–5 per order vs. $15–25 for manually reviewed orders',
      '<strong>APICS:</strong> Average touchless PO rate across manufacturers is 55–65%; leaders exceed 80%',
      '<strong>Deloitte:</strong> Every 10-percentage-point increase in PO automation reduces procurement operating cost by 8–12%',
      '<strong>Ardent Partners:</strong> Best-in-class procurement teams spend &lt;20% of buyer time on transactional PO processing',
    ],
  },
  'ord-auto': {
    title: 'Automation Rate Trend',
    rows: [
      {l: 'Formula', v: 'Automated POs ÷ Total POs × 100'},
      {l: 'Target', v: '≥ 80% automation rate'},
      {l: 'Exclusions', v: 'Emergency buys and spot purchases'},
      {l: 'Period', v: '12-month rolling'},
    ],
    note: 'Rate improvements come from expanding supplier tolerance agreements and ERP rule tuning.',
    why: 'Tracking automation rate over time measures the ROI of ERP rule expansions, supplier onboarding efforts, and tolerance agreement programs. Stagnant or declining automation rate signals that exception volume is growing faster than rule coverage.',
    benchmarks: [
      '<strong>Hackett Group:</strong> World-class procurement automation rate ≥ 80%; industry average is 50–60%',
      '<strong>Gartner:</strong> Companies at ≥ 75% automation process purchase orders 3× faster than manual-heavy peers',
      '<strong>Ardent Partners:</strong> Chief Procurement Officers rank touchless PO processing as a top-3 cost reduction priority',
      '<strong>McKinsey:</strong> Procurement automation reduces transactional processing costs by 30–40% over a 3-year implementation horizon',
      '<strong>Deloitte:</strong> Supplier portal adoption and EDI integration are the #1 levers cited for improving automation rate beyond 70%',
    ],
  },
};

function _dl(items) {
  return '<ul class="drill-bench-list">' + items.map(i => `<li>${i}</li>`).join('') + '</ul>';
}

function openChartInfo(id) {
  const c = CHART_INFO[id];
  if (!c) return;
  const benchHtml = c.benchmarks ? _ds('Industry Benchmarks', _dl(c.benchmarks.slice(0, 3))) : '';
  const content = _ds('How It\'s Calculated', _dr(c.rows)) + _dn(c.note) + benchHtml;
  openDrill(c.title, content);
}

// ── Add Risk Item ──────────────────────────────────────────────────────────
function openAddRisk() {
  const content = `<div style="display:flex;flex-direction:column;gap:14px">
    <div><label class="form-label">Risk Item</label><input id="ar-item" class="form-input" placeholder="Describe the risk..."></div>
    <div><label class="form-label">Impact Level</label><select id="ar-impact" class="form-input"><option>Critical</option><option>High</option><option>Medium</option><option>Low</option></select></div>
    <div><label class="form-label">Value at Risk ($M)</label><input id="ar-var" class="form-input" type="number" step="0.1" placeholder="0.0"></div>
    <div><label class="form-label">Owner</label><input id="ar-owner" class="form-input" placeholder="Name or team"></div>
    <div><label class="form-label">Mitigation Step</label><textarea id="ar-mit" class="form-input" rows="3" style="resize:vertical" placeholder="Describe the mitigation plan..."></textarea></div>
    <div style="display:flex;gap:10px;margin-top:4px"><button class="form-submit" onclick="submitAddRisk()">Add to Register</button><button class="form-cancel" onclick="closeDrill()">Cancel</button></div>
  </div>`;
  openDrill('Add Risk Item', content);
}

function submitAddRisk() {
  const item       = document.getElementById('ar-item').value.trim();
  const impact     = document.getElementById('ar-impact').value;
  const varVal     = parseFloat(document.getElementById('ar-var').value) || 0;
  const owner      = document.getElementById('ar-owner').value.trim();
  const mitigation = document.getElementById('ar-mit').value.trim();
  if (!item) { document.getElementById('ar-item').focus(); return; }
  const tbody = document.querySelector('#ibp-risk-table tbody');
  if (!tbody) return;
  const i = _riskStore.length;
  const entry = {item, impact, value_m: varVal, owner, mitigation};
  _riskStore.push(entry);
  const tr = document.createElement('tr');
  tr.id = `risk-row-${i}`;
  tr.innerHTML = _riskRowHtml(i, entry);
  tbody.appendChild(tr);
  closeDrill();
}
function _dr(rows) {
  return '<div class="drill-rows">' + rows.map(r =>
    `<div class="drill-row"><div class="drill-row-label">${r.l}</div><div class="drill-row-val">${r.v}</div></div>`
  ).join('') + '</div>';
}
function _ds(title, content) {
  return `<div class="drill-section"><div class="drill-section-title">${title}</div>${content}</div>`;
}
function _dn(text) {
  return `<div class="drill-note">${text}</div>`;
}

// ── App Config (company name / branding) ──────────────────────────────────────
async function loadAppConfig() {
  try {
    const d = await (await fetch('/supply-chain/api/config')).json();
    if (d.company_name) {
      document.getElementById('nav-brand-name').textContent = d.company_name + ' — Supply Chain';
      document.title = d.company_name + ' — Supply Chain Control Tower';
    }
    if (d.company_name) {
      fetch(`https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(d.company_name)}`)
        .then(r => r.json())
        .then(results => {
          if (!results || !results[0] || !results[0].domain) return;
          const img = document.createElement('img');
          img.alt = d.company_name;
          img.style.cssText = 'width:28px;height:28px;border-radius:6px;object-fit:contain;flex-shrink:0;';
          img.onload = () => {
            // Replace the Databricks icon with the company logo in the top-left
            const brand = document.querySelector('.nav-brand');
            const brandSvg = brand ? brand.querySelector('svg') : null;
            if (brandSvg) brandSvg.replaceWith(img);
            else if (brand) brand.prepend(img);
            // Show just the app title — the logo identifies the company visually
            const nameEl = document.getElementById('nav-brand-name');
            if (nameEl) nameEl.textContent = 'Supply Chain Control Tower';
          };
          img.onerror = () => {}; // fallback: keep company name text
          img.src = `https://cdn.brandfetch.io/domain/${results[0].domain}?c=1idGdcDDyuPmwhnhURl`; // set src last so onload is always wired up
        })
        .catch(() => {});
    }
  } catch (_) {}
}

// ── Initialise ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadAppConfig();
  switchTab('ibp');
  fetchKpis();
  setInterval(fetchKpis, 30000);
  showTutorialIfNew();

  // Cmd/Ctrl+Enter for AI
  document.getElementById('ai-input').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitAi(); }
  });

  // Remove focus from FAB after any click so it never stays highlighted
  document.getElementById('talk-fab').addEventListener('click', e => {
    e.currentTarget.blur();
  });
});

function showTutorialIfNew() {
  if (!localStorage.getItem('sc-tutorial-seen')) {
    document.getElementById('tut-overlay').classList.remove('hidden');
  }
}
function dismissTutorial() {
  localStorage.setItem('sc-tutorial-seen', '1');
  document.getElementById('tut-overlay').classList.add('hidden');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') dismissTutorial(); });

// ── Contact Form ──────────────────────────────────────────────────────────────
// ── Logistics Map ──────────────────────────────────────────────────────────────
const LOGISTICS_DCS = [
  { id:'CHI', name:'Chicago DC',   lat:41.85,  lng:-87.65,  color:'#1B6FEB' },
  { id:'DAL', name:'Dallas DC',    lat:32.78,  lng:-96.80,  color:'#10b981' },
  { id:'PHX', name:'Phoenix DC',   lat:33.45,  lng:-112.07, color:'#f59e0b' },
  { id:'ATL', name:'Atlanta DC',   lat:33.75,  lng:-84.39,  color:'#ef4444' },
  { id:'SEA', name:'Seattle DC',   lat:47.61,  lng:-122.33, color:'#8b5cf6' },
  { id:'NWK', name:'Newark DC',    lat:40.74,  lng:-74.17,  color:'#f97316' },
];

const LOGISTICS_TRUCKS = [
  { id:'TRK-0041', dc:'CHI', from:'Chicago, IL',  to:'Detroit, MI',       lat:42.80, lng:-84.20, status:'in_transit', cargo:'Auto Parts',         load:'38,400 lbs', eta:'2h 15m',       route:'RT-CHI-001' },
  { id:'TRK-0055', dc:'CHI', from:'Chicago, IL',  to:'Cincinnati, OH',    lat:41.50, lng:-86.10, status:'in_transit', cargo:'Electronics',         load:'41,200 lbs', eta:'4h 40m',       route:'RT-CHI-002' },
  { id:'TRK-0067', dc:'CHI', from:'Chicago, IL',  to:'Minneapolis, MN',   lat:43.90, lng:-91.50, status:'delayed',    cargo:'Appliances',          load:'35,800 lbs', eta:'6h 30m (+2h)', route:'RT-CHI-003' },
  { id:'TRK-0072', dc:'CHI', from:'Chicago, IL',  to:'St. Louis, MO',     lat:40.90, lng:-88.90, status:'in_transit', cargo:'Industrial Supplies', load:'44,000 lbs', eta:'3h 50m',       route:'RT-CHI-004' },
  { id:'TRK-0088', dc:'DAL', from:'Dallas, TX',   to:'Houston, TX',       lat:32.30, lng:-96.00, status:'in_transit', cargo:'Chemical Supplies',   load:'39,600 lbs', eta:'1h 55m',       route:'RT-DAL-001' },
  { id:'TRK-0094', dc:'DAL', from:'Dallas, TX',   to:'Denver, CO',        lat:35.80, lng:-101.20, status:'in_transit', cargo:'Energy Equipment',   load:'42,000 lbs', eta:'5h 10m',       route:'RT-DAL-002' },
  { id:'TRK-0103', dc:'DAL', from:'Dallas, TX',   to:'Kansas City, MO',   lat:35.40, lng:-96.40, status:'loading',    cargo:'Consumer Goods',      load:'37,200 lbs', eta:'3h 25m',       route:'RT-DAL-003' },
  { id:'TRK-0115', dc:'DAL', from:'Dallas, TX',   to:'New Orleans, LA',   lat:31.50, lng:-92.80, status:'delayed',    cargo:'Food Products',       load:'36,000 lbs', eta:'2h 45m (+1h)', route:'RT-DAL-004' },
  { id:'TRK-0128', dc:'PHX', from:'Phoenix, AZ',  to:'Los Angeles, CA',   lat:34.10, lng:-117.30, status:'in_transit', cargo:'Semiconductors',     load:'28,000 lbs', eta:'1h 20m',       route:'RT-PHX-001' },
  { id:'TRK-0134', dc:'PHX', from:'Phoenix, AZ',  to:'Salt Lake City, UT',lat:36.20, lng:-112.10, status:'in_transit', cargo:'Mining Equipment',   load:'45,000 lbs', eta:'4h 00m',       route:'RT-PHX-002' },
  { id:'TRK-0141', dc:'PHX', from:'Phoenix, AZ',  to:'Albuquerque, NM',   lat:33.10, lng:-109.30, status:'in_transit', cargo:'Aerospace Parts',    load:'31,200 lbs', eta:'2h 30m',       route:'RT-PHX-003' },
  { id:'TRK-0156', dc:'ATL', from:'Atlanta, GA',  to:'Charlotte, NC',     lat:34.40, lng:-82.50, status:'in_transit', cargo:'Textiles',             load:'38,800 lbs', eta:'2h 10m',       route:'RT-ATL-001' },
  { id:'TRK-0162', dc:'ATL', from:'Atlanta, GA',  to:'Miami, FL',         lat:29.80, lng:-82.00, status:'in_transit', cargo:'Perishables',          load:'33,600 lbs', eta:'2h 40m',       route:'RT-ATL-002' },
  { id:'TRK-0177', dc:'ATL', from:'Atlanta, GA',  to:'Nashville, TN',     lat:34.80, lng:-86.50, status:'delayed',    cargo:'Automotive Parts',     load:'41,600 lbs', eta:'1h 50m (+45m)',route:'RT-ATL-003' },
  { id:'TRK-0189', dc:'SEA', from:'Seattle, WA',  to:'Portland, OR',      lat:46.40, lng:-122.20, status:'in_transit', cargo:'Tech Hardware',       load:'29,400 lbs', eta:'1h 30m',       route:'RT-SEA-001' },
  { id:'TRK-0195', dc:'SEA', from:'Seattle, WA',  to:'Boise, ID',         lat:47.00, lng:-118.80, status:'in_transit', cargo:'Lumber Products',     load:'44,800 lbs', eta:'3h 15m',       route:'RT-SEA-002' },
  { id:'TRK-0211', dc:'NWK', from:'Newark, NJ',   to:'Boston, MA',        lat:41.70, lng:-72.60, status:'in_transit', cargo:'Pharma Products',      load:'26,800 lbs', eta:'1h 45m',       route:'RT-NWK-001' },
  { id:'TRK-0224', dc:'NWK', from:'Newark, NJ',   to:'Pittsburgh, PA',    lat:40.80, lng:-76.80, status:'loading',    cargo:'Steel Components',     load:'46,000 lbs', eta:'2h 50m',       route:'RT-NWK-002' },
];

let _logisticsMap    = null;
let _truckMarkers    = [];
let _dcMarkers       = [];
let _routeLines      = [];
let _logiFilterDC     = 'all';
let _logiFilterStatus = 'all';
let _logiFilterRoute  = '';

function initLogisticsMap() {
  if (_logisticsMap) { _logisticsMap.invalidateSize(); renderLogisticsMarkers(); return; }

  _logisticsMap = L.map('logistics-map', {
    center: [39.5, -98.35], zoom: 4,
    zoomControl: true, attributionControl: true,
  });

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com">CARTO</a>',
    subdomains: 'abcd', maxZoom: 19,
  }).addTo(_logisticsMap);

  // Legend control
  const legend = L.control({ position: 'topright' });
  legend.onAdd = () => {
    const div = L.DomUtil.create('div', 'logi-legend');
    div.innerHTML =
      '<div class="logi-legend-title">Distribution Centers</div>' +
      LOGISTICS_DCS.map(d => `<div class="logi-leg"><div class="logi-leg-dc" style="background:${d.color}"></div>${d.name}</div>`).join('') +
      '<div class="logi-legend-title" style="margin-top:8px">Trucks</div>' +
      '<div class="logi-leg"><div class="logi-leg-truck" style="background:#10b981"></div>In Transit</div>' +
      '<div class="logi-leg"><div class="logi-leg-truck" style="background:#1B6FEB"></div>Loading</div>' +
      '<div class="logi-leg"><div class="logi-leg-truck" style="background:#ef4444"></div>Delayed</div>';
    return div;
  };
  legend.addTo(_logisticsMap);

  renderLogisticsMarkers();
}

function renderLogisticsMarkers() {
  if (!_logisticsMap) return;
  _truckMarkers.forEach(m => _logisticsMap.removeLayer(m));
  _dcMarkers.forEach(m => _logisticsMap.removeLayer(m));
  _routeLines.forEach(l => _logisticsMap.removeLayer(l));
  _truckMarkers = []; _dcMarkers = []; _routeLines = [];

  const dcMap = {};
  LOGISTICS_DCS.forEach(dc => { dcMap[dc.id] = dc; });

  const trucks = LOGISTICS_TRUCKS.filter(t => {
    if (_logiFilterDC !== 'all' && t.dc !== _logiFilterDC) return false;
    if (_logiFilterStatus !== 'all' && t.status !== _logiFilterStatus) return false;
    if (_logiFilterRoute) {
      const q = _logiFilterRoute.toLowerCase();
      if (!t.id.toLowerCase().includes(q) && !t.route.toLowerCase().includes(q) &&
          !t.to.toLowerCase().includes(q) && !t.from.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  // DC markers
  LOGISTICS_DCS.forEach(dc => {
    if (_logiFilterDC !== 'all' && _logiFilterDC !== dc.id) return;
    const icon = L.divIcon({
      className: '',
      html: `<div style="width:34px;height:34px;border-radius:50%;background:${dc.color};border:2px solid rgba(255,255,255,0.9);box-shadow:0 0 0 3px ${dc.color}55,0 4px 14px rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:800;color:#fff;letter-spacing:-.3px">${dc.id}</div>`,
      iconSize: [34, 34], iconAnchor: [17, 17],
    });
    const activeTrucks = LOGISTICS_TRUCKS.filter(t => t.dc === dc.id).length;
    const m = L.marker([dc.lat, dc.lng], { icon, zIndexOffset: 1000 })
      .addTo(_logisticsMap)
      .bindPopup(
        `<div style="font-family:Inter,sans-serif"><strong style="font-size:14px">${dc.name}</strong><br>` +
        `<span style="font-size:11px;color:#9ca3af">Distribution Center · ${dc.id}</span><br>` +
        `<span style="font-size:12px;margin-top:6px;display:block"><strong>${activeTrucks}</strong> active routes</span></div>`,
        { className: 'logi-popup' }
      );
    _dcMarkers.push(m);
  });

  // Truck markers + route lines
  trucks.forEach(t => {
    const dc = dcMap[t.dc];
    if (!dc) return;
    const sColor = t.status === 'in_transit' ? '#10b981' : t.status === 'loading' ? '#1B6FEB' : '#ef4444';
    const sLabel = t.status === 'in_transit' ? 'In Transit' : t.status === 'loading' ? 'Loading' : 'Delayed';

    const line = L.polyline([[dc.lat, dc.lng], [t.lat, t.lng]], {
      color: dc.color, weight: 2, opacity: 0.45, dashArray: '7,5',
    }).addTo(_logisticsMap);
    _routeLines.push(line);

    const icon = L.divIcon({
      className: '',
      html: `<div style="width:14px;height:14px;border-radius:3px;background:${sColor};border:1.5px solid rgba(255,255,255,0.9);transform:rotate(45deg);box-shadow:0 2px 8px rgba(0,0,0,0.5)"></div>`,
      iconSize: [14, 14], iconAnchor: [7, 7],
    });

    const popup =
      `<div style="font-family:Inter,sans-serif;min-width:210px">` +
      `<div style="font-weight:700;font-size:13px;margin-bottom:3px">${t.id}</div>` +
      `<div style="font-size:10.5px;color:#9ca3af;margin-bottom:8px;font-weight:600;text-transform:uppercase;letter-spacing:.05em">${t.route}</div>` +
      `<div style="font-size:12px;margin-bottom:2px">From: <strong>${t.from}</strong></div>` +
      `<div style="font-size:12px;margin-bottom:8px">To: <strong>${t.to}</strong></div>` +
      `<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">` +
      `<span style="background:${sColor}22;color:${sColor};border:1px solid ${sColor}55;border-radius:5px;padding:2px 8px;font-size:10.5px;font-weight:700">${sLabel}</span>` +
      `<span style="font-size:11px;color:#d1d5db">ETA: <strong>${t.eta}</strong></span></div>` +
      `<div style="font-size:11px;color:#9ca3af">${t.cargo} · ${t.load}</div></div>`;

    const m = L.marker([t.lat, t.lng], { icon })
      .addTo(_logisticsMap)
      .bindPopup(popup, { className: 'logi-popup', maxWidth: 260 });
    _truckMarkers.push(m);
  });

  // Update stats
  document.getElementById('logi-count-transit').textContent = trucks.filter(t => t.status === 'in_transit').length;
  document.getElementById('logi-count-load').textContent    = trucks.filter(t => t.status === 'loading').length;
  document.getElementById('logi-count-delayed').textContent = trucks.filter(t => t.status === 'delayed').length;
}

function logiSetDC(val) {
  _logiFilterDC = val;
  renderLogisticsMarkers();
}

function logiSetStatus(status, btn) {
  _logiFilterStatus = status;
  document.querySelectorAll('.logi-status-pill').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderLogisticsMarkers();
}

function logiSearch() {
  _logiFilterRoute = document.getElementById('logi-route-search').value.trim();
  renderLogisticsMarkers();
}

// ── Page Timer ────────────────────────────────────────────────────────────────
function _startTimer() {
  clearInterval(_timerInterval);
  _tabStartTime = Date.now();
  _timerDisplay(0);
  _timerInterval = setInterval(() => {
    _timerDisplay(Math.floor((Date.now() - _tabStartTime) / 1000));
  }, 1000);
}

function _timerDisplay(seconds) {
  const el = document.getElementById('page-timer');
  if (!el) return;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  el.textContent = `${m}:${s.toString().padStart(2, '0')}`;
}

async function _logPageTime(page, seconds) {
  if (seconds < 1) return;
  const clicks = _clickCount;
  _clickCount = 0;
  try {
    await fetch('/supply-chain/api/log-page-time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, seconds_spent: seconds, click_count: clicks }),
    });
  } catch (_) {}
}

// ── Tab Switching ─────────────────────────────────────────────────────────────
function switchTab(tab) {
  // Log time spent on the tab we're leaving (skip same-tab and initial load)
  if (_tabStartTime !== null && tab !== _activeTab) {
    _logPageTime(_activeTab, Math.floor((Date.now() - _tabStartTime) / 1000));
  }

  document.querySelectorAll('.nav-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('hidden', p.id !== `tab-${tab}`);
  });
  _activeTab = tab;
  _startTimer();

  // Lazy-load data on first visit to each tab
  if (tab === 'ibp'       && !_ibpPlanChart)   fetchIbp();
  if (tab === 'inventory' && !_invHealthChart)  fetchInventory();
  if (tab === 'demand'    && !_demFaChart)      fetchDemand();
  if (tab === 'orders'    && !_ordVolChart)     fetchOrders();
  if (tab === 'logistics')                      initLogisticsMap();

  // Refresh open panels
  const ap = document.getElementById('agent-panel');
  if (!ap.classList.contains('hidden')) renderAgentPanel(tab);
  const tm = document.getElementById('info-overlay');
  if (!tm.classList.contains('hidden')) openInfoPanel(tab);
}


// ── KPIs ──────────────────────────────────────────────────────────────────────
async function fetchKpis() {
  try {
    const d = await (await fetch('/supply-chain/api/kpis')).json();
    _scKpisRaw = d;
    setText('gkpi-plan',  d.plan_attainment + '%');
    setText('gkpi-turns', d.inventory_turns + 'x');
    setText('gkpi-mape',  parseFloat(d.forecast_mape.toFixed(2)) + '%');
    setText('gkpi-auto',  d.order_automation + '%');
    setText('gkpi-otd',   d.on_time_delivery + '%');
    setText('gkpi-fill',  d.fill_rate        + '%');
  } catch (e) { /* silent */ }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── IBP ───────────────────────────────────────────────────────────────────────
async function fetchIbp() {
  try {
    const d = await (await fetch('/supply-chain/api/ibp')).json();
    _ibpBuRaw    = d.bu_attainment;
    _ibpRisksRaw = d.risks;
    _ibpKpisRaw  = d.kpis;
    _ibpPlanOrig = d.plan_data;
    renderSopPipeline(d.sop_stages);
    renderIbpPlanChart(d.plan_data);
    renderIbpBuChart(d.bu_attainment);
    renderIbpRiskTable(d.risks);
  } catch (e) { console.error('IBP fetch error', e); }
}


function setKpiCard(id, val, color, drillTitle, drillContent) {
  const el = document.getElementById(id);
  if (!el) return;
  const v = el.querySelector('.kpi-val');
  if (v) { v.textContent = val; v.style.color = color; }
  if (drillTitle) {
    el.classList.add('clickable');
    el.onclick = () => openDrill(drillTitle, drillContent);
  }
}

const SOP_STAGE_DETAIL = {
  'Data Collection': {
    purpose: 'Gather and cleanse all supply chain data needed to build a clean baseline for the planning cycle.',
    steps: [
      'Extract actuals (shipments, orders, production) from ERP and warehouse systems',
      'Pull financial actuals and budget data from the FP&A system',
      'Reconcile data discrepancies between source systems',
      'Load cleansed data into the Databricks Delta Lake planning tables',
      'Validate data completeness — flag missing SKUs, DCs, or time periods',
    ],
    inputs: [
      {l: 'ERP Transaction Data', v: 'SAP/Oracle shipment & order actuals'},
      {l: 'Financial Actuals', v: 'P&L by BU from FP&A system'},
      {l: 'Inventory Snapshots', v: 'On-hand & in-transit from WMS'},
      {l: 'Open PO Register', v: 'Procurement commitments'},
      {l: 'Customer Backlog', v: 'Unfulfilled orders from OMS'},
    ],
    outputs: [
      {l: 'Validated Actuals Dataset', v: 'Delta Lake — gold layer'},
      {l: 'Data Quality Report', v: 'Completeness & anomaly flags'},
      {l: 'Baseline KPI Snapshot', v: 'Starting point for cycle'},
    ],
  },
  'Statistical Forecast': {
    purpose: 'Generate a data-driven baseline demand forecast using the Databricks ML model, free of human bias.',
    steps: [
      'Run Databricks AutoML demand model over 36-month shipment history',
      'Apply seasonality decomposition and external signal enrichment (macro indices)',
      'Generate 18-month forward forecast at SKU × DC level',
      'Calculate MAPE, bias, and Forecast Value Add vs naïve baseline',
      'Flag high-uncertainty SKUs for demand planner review',
    ],
    inputs: [
      {l: 'Cleansed Shipment History', v: '36 months · SKU × DC level'},
      {l: 'Seasonality Indices', v: 'Category-level seasonal patterns'},
      {l: 'External Signals', v: 'Industry indices, macro data'},
      {l: 'New Product Roadmap', v: 'Launches in planning horizon'},
      {l: 'Promo Calendar', v: 'Planned promotional events'},
    ],
    outputs: [
      {l: 'Statistical Baseline Forecast', v: '18-month, SKU × DC'},
      {l: 'MAPE by SKU & Category', v: 'Accuracy scorecard'},
      {l: 'High-Error SKU List', v: 'Candidates for manual review'},
      {l: 'Forecast Value Add Report', v: 'ML vs naïve comparison'},
    ],
  },
  'Unconstrained Demand': {
    purpose: 'Enrich the statistical baseline with commercial intelligence to produce an unconstrained demand plan.',
    steps: [
      'Distribute statistical baseline to regional demand planners for review',
      'Incorporate sales pipeline, promotional uplift, and customer commitments',
      'Apply judgment overrides for new products, market events, and promotions',
      'Hold demand review meetings by BU to agree commercial adjustments',
      'Publish agreed unconstrained demand plan — no supply limits applied yet',
    ],
    inputs: [
      {l: 'Statistical Baseline Forecast', v: 'From previous stage'},
      {l: 'Sales Pipeline Data', v: 'CRM — qualified opportunities'},
      {l: 'Promotional Calendar', v: 'Volume uplift estimates'},
      {l: 'New Product Launch Plan', v: 'Commercial & marketing input'},
      {l: 'Customer Commitments', v: 'Contracted volumes & call-offs'},
    ],
    outputs: [
      {l: 'Unconstrained Demand Plan', v: '18-month, by BU & SKU'},
      {l: 'Override Log', v: 'Planner adjustments vs statistical'},
      {l: 'Demand Assumptions Register', v: 'Documented commercial drivers'},
      {l: 'Demand Risk & Opportunity Log', v: 'Upside and downside scenarios'},
    ],
  },
  'Supply Review': {
    purpose: 'Evaluate whether supply capacity can meet unconstrained demand and identify gaps requiring resolution.',
    steps: [
      'Run capacity loading against production, procurement, and logistics constraints',
      'Identify capacity gaps and excess capacity by site, DC, and supplier',
      'Evaluate supplier OTD performance and flag at-risk supply lanes',
      'Model inventory projections — DOS, turns, and excess positions',
      'Build constrained supply plan and quantify unresolved gaps',
    ],
    inputs: [
      {l: 'Unconstrained Demand Plan', v: 'From Demand Review stage'},
      {l: 'Production Capacity Data', v: 'Rated capacity by plant & line'},
      {l: 'Supplier Lead Times & OTD', v: 'Current supplier performance'},
      {l: 'Open PO & ASN Data', v: 'Confirmed supply pipeline'},
      {l: 'DC Capacity & Utilization', v: 'Warehouse constraints'},
      {l: 'Safety Stock Targets', v: 'Policy by SKU & location'},
    ],
    outputs: [
      {l: 'Constrained Supply Plan', v: '18-month production & procurement'},
      {l: 'Capacity Gap Register', v: 'Gaps by site, period, value'},
      {l: 'Inventory Projection', v: 'Forecast DOS & turns by DC'},
      {l: 'Supply Risk Register', v: 'At-risk suppliers & lanes'},
      {l: 'Recommended Mitigations', v: 'Expedites, transfers, dual-source'},
    ],
  },
  'Consensus Meeting': {
    purpose: 'Align commercial, supply, and finance on a single operating plan and resolve open gaps before executive review.',
    steps: [
      'Present demand vs supply gap summary to cross-functional team',
      'Review unresolved risk register items and assign resolution owners',
      'Negotiate volume trade-offs between BUs where capacity is constrained',
      'Agree on financial bridge from consensus plan to budget target',
      'Lock consensus plan figures and document all outstanding assumptions',
    ],
    inputs: [
      {l: 'Constrained Supply Plan', v: 'From Supply Review stage'},
      {l: 'Unconstrained Demand Plan', v: 'Commercial view'},
      {l: 'Gap & Risk Register', v: 'Open items requiring resolution'},
      {l: 'Financial Budget', v: 'BU-level revenue & margin targets'},
      {l: 'Scenario Analysis', v: 'Upside/downside plan options'},
    ],
    outputs: [
      {l: 'Agreed Consensus Plan', v: 'Single operating number by BU'},
      {l: 'Decision Log', v: 'Agreed trade-offs and resolutions'},
      {l: 'Escalation List', v: 'Items requiring exec decision'},
      {l: 'Financial Reconciliation', v: 'Consensus vs budget bridge'},
      {l: 'Updated Risk Register', v: 'Resolved & remaining items'},
    ],
  },
  'Executive Sign-off': {
    purpose: 'Gain leadership approval of the consensus plan and authorise resource commitments for the planning horizon.',
    steps: [
      'Present executive S&OP pack — plan vs budget, risk register, key decisions',
      'Review escalated items that were unresolved at Consensus Meeting',
      'Approve or redirect resource allocation and capital commitments',
      'Formally sign off the operating plan for the next planning period',
      'Publish approved plan to ERP and notify all functional owners',
    ],
    inputs: [
      {l: 'Consensus Plan', v: 'Cross-functional agreed view'},
      {l: 'Executive S&OP Pack', v: 'KPIs, gaps, risks, decisions'},
      {l: 'Escalation Items', v: 'Unresolved from Consensus Meeting'},
      {l: 'Financial Impact Analysis', v: 'Revenue, margin, cash flow'},
      {l: 'Scenario Recommendations', v: 'Preferred option with rationale'},
    ],
    outputs: [
      {l: 'Approved Operating Plan', v: 'Published to ERP & Databricks'},
      {l: 'Executive Decision Record', v: 'Signed-off actions & owners'},
      {l: 'Resource Authorisations', v: 'Approved spend & headcount'},
      {l: 'Plan Communication Pack', v: 'For distribution to all BUs'},
      {l: 'Next Cycle Start Memo', v: 'Dates, owners, key focus areas'},
    ],
  },
};

// Keyed by numeric index — populated when pipeline is first rendered
const _sopStageData = [];

function _refreshSopPipeline() {
  const el = document.getElementById('sop-stages');
  if (!el) return;
  el.innerHTML = _sopStageData.map((s, i) => {
    const statusClass = s.status === 'complete' ? 'complete' : s.status === 'in_progress' ? 'in-progress' : 'pending';
    const icon = s.status === 'complete'
      ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
      : s.status === 'in_progress'
      ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="5"/></svg>`
      : `<span style="font-size:11px;color:var(--text-muted)">${i + 1}</span>`;
    return `
      <div class="sop-stage ${statusClass} clickable" onclick="openSopDrill(${i})">
        <div class="sop-stage-card">
          <div class="sop-dot">${icon}</div>
          <div class="sop-stage-name">${esc(s.stage)}</div>
          <div class="sop-stage-owner">${esc(s.owner)}</div>
          <div class="sop-stage-date">${esc(s.date)}</div>
          <div class="sop-stage-hint">View details →</div>
        </div>
      </div>`;
  }).join('');
}

function toggleSopStep(idx, stepIdx) {
  const s = _sopStageData[idx];
  if (!s || !s.checkedSteps) return;
  s.checkedSteps[stepIdx] = !s.checkedSteps[stepIdx];
  openSopDrill(idx);
}

function setSopStatus(idx, status) {
  const s = _sopStageData[idx];
  if (!s) return;
  s.status = status;
  _refreshSopPipeline();
  openSopDrill(idx);
}

function openSopDrill(idx) {
  const s = _sopStageData[idx];
  const stageName = s && s.stage;
  if (!s) return;
  const detail = SOP_STAGE_DETAIL[stageName];

  // Initialise checklist state on first open
  if (detail && !s.checkedSteps) s.checkedSteps = new Array(detail.steps.length).fill(false);

  const statusLabel = s.status === 'complete' ? 'Complete' : s.status === 'in_progress' ? 'In Progress' : 'Pending';
  const statusColor = s.status === 'complete' ? 'var(--accent-green)' : s.status === 'in_progress' ? 'var(--accent-blue)' : 'var(--text-muted)';
  const checkedCount = s.checkedSteps ? s.checkedSteps.filter(Boolean).length : 0;
  const totalSteps = detail ? detail.steps.length : 0;

  const checklistHtml = detail ? _ds('Step Checklist',
    `<div style="display:flex;flex-direction:column;gap:9px">` +
    detail.steps.map((step, j) => {
      const done = s.checkedSteps && s.checkedSteps[j];
      return `<label style="display:flex;align-items:flex-start;gap:10px;cursor:pointer">
        <input type="checkbox" style="margin-top:2px;cursor:pointer;accent-color:var(--accent-green);flex-shrink:0" ${done ? 'checked' : ''} onchange="toggleSopStep(${idx},${j})">
        <span style="font-size:12.5px;line-height:1.5;color:${done ? 'var(--text-muted)' : 'var(--text-secondary)'};${done ? 'text-decoration:line-through' : ''}">${esc(step)}</span>
      </label>`;
    }).join('') +
    `</div><div style="margin-top:10px;font-size:11px;color:var(--text-muted);font-weight:600">${checkedCount} of ${totalSteps} steps completed</div>`
  ) : '';

  const statusBtns = `<div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="sop-status-btn${s.status === 'pending' ? ' active' : ''}" onclick="setSopStatus(${idx},'pending')">Pending</button>
    <button class="sop-status-btn in-prog${s.status === 'in_progress' ? ' active' : ''}" onclick="setSopStatus(${idx},'in_progress')">In Progress</button>
    <button class="sop-status-btn done${s.status === 'complete' ? ' active' : ''}" onclick="setSopStatus(${idx},'complete')">Complete</button>
  </div>`;

  const content = _dn(detail ? detail.purpose : '') +
    _ds('Stage Info', _dr([
      {l: 'Owner', v: s.owner},
      {l: 'Target Date', v: s.date},
      {l: 'Status', v: `<span style="color:${statusColor};font-weight:700">${statusLabel}</span>`},
    ])) +
    checklistHtml +
    _ds('Change Status', statusBtns);

  openDrill(stageName, content);
}

function renderSopPipeline(stages) {
  const el = document.getElementById('sop-stages');
  if (!el) return;
  el.innerHTML = stages.map((s, i) => {
    // Store by numeric index — avoids quoting issues with stage names in onclick
    _sopStageData[i] = s;

    const statusClass = s.status === 'complete' ? 'complete' : s.status === 'in_progress' ? 'in-progress' : 'pending';
    const icon = s.status === 'complete'
      ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
      : s.status === 'in_progress'
      ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="5"/></svg>`
      : `<span style="font-size:11px;color:var(--text-muted)">${i + 1}</span>`;
    return `
      <div class="sop-stage ${statusClass} clickable" onclick="openSopDrill(${i})">
        <div class="sop-stage-card">
          <div class="sop-dot">${icon}</div>
          <div class="sop-stage-name">${esc(s.stage)}</div>
          <div class="sop-stage-owner">${esc(s.owner)}</div>
          <div class="sop-stage-date">${esc(s.date)}</div>
          <div class="sop-stage-hint">View details →</div>
        </div>
      </div>`;
  }).join('');
}

let _ibpPlanUnit = '$m';
let _ibpPlanRaw  = null;
let _ibpPlanOrig = null;  // immutable original from fetch — never overwritten by filter renders

function toggleIbpPlanUnit(unit) {
  _ibpPlanUnit = unit;
  document.querySelectorAll('#ibp-plan-toggle .ctog').forEach(b =>
    b.classList.toggle('active', b.dataset.unit === unit));
  if (_ibpPlanRaw) renderIbpPlanChart(_ibpPlanRaw);
}

function renderIbpPlanChart(planData) {
  _ibpPlanRaw = planData;
  const ctx = document.getElementById('ibp-plan-chart');
  if (!ctx) return;
  if (_ibpPlanChart) _ibpPlanChart.destroy();

  const isKu      = _ibpPlanUnit === 'ku';
  const labels    = planData.map(d => d.month);
  const consensus = planData.map(d => isKu ? d.consensus_k : d.consensus);
  const financial = planData.map(d => isKu ? d.financial_k : d.financial);
  const capacity  = planData.map(d => isKu ? d.capacity_k  : d.capacity);
  const futureIdx = planData.findIndex(d => d.is_future);

  const fmtVal  = v => isKu ? v + 'K' : '$' + v + 'M';
  const fmtDiff = v => isKu ? (v > 0 ? '+' : '') + v + 'K units' : (v > 0 ? '+' : '') + '$' + Math.abs(v) + 'M';

  _ibpPlanChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Consensus Plan',
          data: consensus,
          borderColor: BLUE,
          backgroundColor: _alpha(BLUE, 0.1),
          fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3,
        },
        {
          label: 'Financial Target',
          data: financial,
          borderColor: GREEN,
          backgroundColor: 'transparent',
          borderDash: [5, 4], tension: 0.4, borderWidth: 1.5, pointRadius: 2,
        },
        {
          label: 'Operations Capacity',
          data: capacity,
          borderColor: _alpha('#ffffff', 0.2),
          backgroundColor: 'transparent',
          borderDash: [3, 4], tension: 0.4, borderWidth: 1, pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 12, font: { size: 11 } } },
        annotation: futureIdx >= 0 ? {
          annotations: {
            futureLine: {
              type: 'line', xMin: futureIdx, xMax: futureIdx,
              borderColor: 'rgba(255,255,255,0.2)', borderWidth: 1, borderDash: [4, 4],
              label: { content: 'Forecast →', display: true, color: '#9ca3af', font: { size: 10 }, position: 'start' },
            },
          },
        } : {},
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx  = elements[0].index;
        const month = chart.data.labels[idx];
        const cons = chart.data.datasets[0].data[idx];
        const fin  = chart.data.datasets[1].data[idx];
        const cap  = chart.data.datasets[2].data[idx];
        const gap  = parseFloat((cons - fin).toFixed(1));
        // Also grab the other unit for context
        const row = planData[idx];
        const altCons = isKu ? '$' + row.consensus + 'M' : row.consensus_k + 'K units';
        openDrill(`IBP Plan — ${month}`,
          _ds('Plan Breakdown', _dr([
            {l: 'Consensus Plan',       v: fmtVal(cons) + ' (' + altCons + ')'},
            {l: 'Financial Target',     v: fmtVal(fin)},
            {l: 'Operations Capacity',  v: fmtVal(cap)},
            {l: 'Gap vs Financial',     v: fmtDiff(gap)},
          ])) +
          _dn(gap < 0
            ? `Consensus is ${fmtDiff(gap)} below financial target in ${month}. Review in S&OP cycle before plan lock.`
            : `Consensus is ${fmtDiff(gap)} above financial target in ${month} — capacity headroom available.`)
        );
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxRotation: 45, font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { callback: v => isKu ? v + 'K' : '$' + v + 'M' } },
      },
    },
  });
}

function renderIbpBuChart(bus) {
  const ctx = document.getElementById('ibp-bu-chart');
  if (!ctx) return;
  if (_ibpBuChart) _ibpBuChart.destroy();

  _ibpBuChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: bus.map(b => b.bu),
      datasets: [
        {
          label: 'Attainment %',
          data: bus.map(b => b.attainment),
          backgroundColor: bus.map(b => b.attainment >= b.target ? _alpha(GREEN, 0.7) : _alpha(AMBER, 0.7)),
          borderRadius: 5,
          barPercentage: 0.55,
        },
        {
          label: 'Target %',
          data: bus.map(b => b.target),
          backgroundColor: 'transparent',
          borderColor: _alpha('#ffffff', 0.25),
          borderWidth: 1,
          type: 'line',
          pointStyle: 'dash',
          pointRadius: 0,
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.raw}%` } },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx  = elements[0].index;
        const bu   = chart.data.labels[idx];
        const att  = chart.data.datasets[0].data[idx];
        const tgt  = bus[idx]?.target ?? 95;
        const gap  = (att - tgt).toFixed(1);
        openDrill(`BU Attainment — ${bu}`,
          _ds('Performance', _dr([
            {l: 'Plan Attainment', v: att + '%'}, {l: 'Target', v: tgt + '%'},
            {l: 'Gap vs Target', v: (gap > 0 ? '+' : '') + gap + 'pp'},
            {l: 'Status', v: att >= tgt ? '✓ On Track' : '⚠ Below Target'},
          ])) +
          _dn(att < tgt
            ? `${bu} is ${Math.abs(gap)}pp below target. Primary drivers: demand volatility and supply allocation constraints. Recommend escalation to S&OP steering committee.`
            : `${bu} is performing ${gap}pp above target. This surplus can be leveraged to buffer against EMEA shortfall in the consensus plan.`)
        );
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, min: 70, max: 100, ticks: { callback: v => v + '%' } },
        y: { grid: { display: false } },
      },
    },
  });
}

// Risk register store — keyed by row index, persists edits
const _riskStore = [];

function _riskImpactColor(impact) {
  return impact === 'Critical' ? '#ef4444' : impact === 'High' ? '#f97316' : impact === 'Medium' ? '#eab308' : 'var(--text-muted)';
}

function _riskRowHtml(i, entry) {
  const mitTrunc = entry.mitigation.length > 60 ? entry.mitigation.slice(0, 60) + '…' : entry.mitigation;
  const ic = _riskImpactColor(entry.impact);
  return `<td>${esc(entry.item)}</td>
    <td><span style="color:${ic};font-weight:700">${esc(entry.impact)}</span></td>
    <td style="color:var(--accent-amber);font-weight:600">$${parseFloat(entry.value_m).toFixed(1)}M</td>
    <td>${esc(entry.owner || '—')}</td>
    <td style="color:var(--text-muted);font-size:11.5px">${esc(mitTrunc || '—')}</td>
    <td><button class="row-edit-btn" onclick="event.stopPropagation();openEditRisk(${i})">✎ Edit</button></td>`;
}

function renderIbpRiskTable(risks) {
  const tbody = document.querySelector('#ibp-risk-table tbody');
  if (!tbody) return;
  const riskDetails = {
    0: {mitigation: 'Activate buffer stock from Rotterdam DC; expedite 3 open POs with Apex Industrial. 2-week lead time.', probability: '72%', resolution: 'May 17'},
    1: {mitigation: 'Request Q3 capacity reservation from contract manufacturer. Alternative: shift 15% of volume to APAC plant.', probability: '55%', resolution: 'May 21'},
    2: {mitigation: 'Accelerate contract renewal; apply interim bridge pricing. 18 blocked POs can be released within 48 hours.', probability: '85%', resolution: 'May 10'},
    3: {mitigation: 'Reroute 3 ocean freight lanes via Dubai hub. Air freight for critical components ($280K premium).', probability: '40%', resolution: 'May 28'},
    4: {mitigation: 'Deploy safety stock from Chicago DC; co-ordinate with Commercial on customer allocation.', probability: '30%', resolution: 'Jun 4'},
  };
  _riskStore.length = 0;
  tbody.innerHTML = risks.map((r, i) => {
    const detail = riskDetails[i] || {mitigation: 'Under review.', probability: 'TBD', resolution: 'TBD'};
    const entry = {item: r.item, impact: r.impact, value_m: r.value_m, owner: r.owner, mitigation: detail.mitigation};
    _riskStore.push(entry);
    return `<tr id="risk-row-${i}">${_riskRowHtml(i, entry)}</tr>`;
  }).join('');
}

function openEditRisk(i) {
  const e = _riskStore[i];
  if (!e) return;
  const impactOpts = ['Critical','High','Medium','Low'].map(v =>
    `<option${v === e.impact ? ' selected' : ''}>${v}</option>`).join('');
  const content = `<div style="display:flex;flex-direction:column;gap:14px">
    <div><label class="form-label">Risk Item</label><input id="er-item" class="form-input" value="${esc(e.item)}"></div>
    <div><label class="form-label">Impact Level</label><select id="er-impact" class="form-input">${impactOpts}</select></div>
    <div><label class="form-label">Value at Risk ($M)</label><input id="er-var" class="form-input" type="number" step="0.1" value="${e.value_m}"></div>
    <div><label class="form-label">Owner</label><input id="er-owner" class="form-input" value="${esc(e.owner || '')}"></div>
    <div><label class="form-label">Mitigation Step</label><textarea id="er-mit" class="form-input" rows="3" style="resize:vertical">${esc(e.mitigation || '')}</textarea></div>
    <div style="display:flex;gap:10px;margin-top:4px"><button class="form-submit" onclick="submitEditRisk(${i})">Save Changes</button><button class="form-cancel" onclick="closeDrill()">Cancel</button></div>
  </div>`;
  openDrill('Edit Risk Item', content);
}

function submitEditRisk(i) {
  const item       = document.getElementById('er-item').value.trim();
  const impact     = document.getElementById('er-impact').value;
  const varVal     = parseFloat(document.getElementById('er-var').value) || 0;
  const owner      = document.getElementById('er-owner').value.trim();
  const mitigation = document.getElementById('er-mit').value.trim();
  if (!item) { document.getElementById('er-item').focus(); return; }
  _riskStore[i] = {item, impact, value_m: varVal, owner, mitigation};
  const tr = document.getElementById(`risk-row-${i}`);
  if (tr) tr.innerHTML = _riskRowHtml(i, _riskStore[i]);
  closeDrill();
}

// ── Inventory ─────────────────────────────────────────────────────────────────
async function fetchInventory() {
  try {
    const d = await (await fetch('/supply-chain/api/inventory')).json();
    _invWarehousesRaw = d.warehouses;
    _invCategoriesRaw = d.categories;
    _invAlertsRaw     = d.alerts;
    _invKpisRaw       = d.kpis;
    _invHealthRaw     = d.health;
    renderInvKpis(d.kpis);
    renderInvHealthChart(d.health);
    renderInvWarehouseChart(d.warehouses);
    renderInvDosChart(d.categories);
    renderInvAlerts(d.alerts);
  } catch (e) { console.error('Inventory fetch error', e); }
}

function renderInvKpis(k) {
  setKpiCard('inv-k1', k.inventory_turns + 'x', '#f0f0f0', 'Inventory Turns — Detail',
    _ds('By DC', _dr([
      {l: 'Chicago ORD', v: (k.inventory_turns + 0.4) + 'x'}, {l: 'Rotterdam RTM', v: (k.inventory_turns - 0.3) + 'x'},
      {l: 'Singapore SIN', v: (k.inventory_turns + 0.7) + 'x'}, {l: 'São Paulo GRU', v: (k.inventory_turns - 0.8) + 'x'},
      {l: 'Sydney SYD', v: (k.inventory_turns + 0.1) + 'x'},
    ])) +
    _ds('Benchmark', _dr([
      {l: 'Current', v: k.inventory_turns + 'x'}, {l: 'Industry Median', v: '5.8x'}, {l: 'Target', v: '6.5x'},
    ])) +
    _dn('São Paulo is pulling down the average due to regulatory buffer stock requirements. Excluding GRU, network average turns at ' + (k.inventory_turns + 0.5).toFixed(1) + 'x.')
  );
  setKpiCard('inv-k2', k.days_on_hand + ' days', '#f0f0f0', 'Days on Hand — Detail',
    _ds('By Category', _dr([
      {l: 'Finished Goods', v: (k.days_on_hand + 4) + ' days'}, {l: 'Raw Materials', v: (k.days_on_hand - 2) + ' days'},
      {l: 'WIP', v: (k.days_on_hand - 8) + ' days'}, {l: 'Spare Parts', v: (k.days_on_hand + 12) + ' days'},
    ])) +
    _dn('Spare parts carry elevated DOH due to long supplier lead times. A vendor-managed inventory agreement with top 3 MRO suppliers could reduce spare parts DOH by 8 days.')
  );
  setKpiCard('inv-k3', k.fill_rate + '%', k.fill_rate >= 97 ? GREEN : AMBER, 'Fill Rate — Detail',
    _ds('By Customer Tier', _dr([
      {l: 'Tier 1 (Key Accounts)', v: (k.fill_rate + 1.2) + '%'},
      {l: 'Tier 2 (Standard)', v: k.fill_rate + '%'},
      {l: 'Tier 3 (Spot)', v: (k.fill_rate - 3.1) + '%'},
    ])) +
    _ds('Top Unfilled SKUs', _dr([
      {l: 'FG-55102 Hydraulic Pump', v: '0% filled · Stockout'},
      {l: 'FG-91033 Drive Belt XL', v: '0% filled · Stockout'},
      {l: 'FG-78421 Sprocket Assy', v: '62% filled · Short'},
    ])) +
    _dn('Two stockout SKUs are driving the fill rate below 98% target. Emergency POs for both items have been identified in the AI Actions panel.')
  );
  setKpiCard('inv-k4', '$' + k.excess_value_m + 'M', AMBER, 'Excess Inventory — Detail',
    _ds('By Category', _dr([
      {l: 'Slow-Moving FG', v: '$' + (k.excess_value_m * 0.48).toFixed(1) + 'M'},
      {l: 'Obsolete Raw Mat.', v: '$' + (k.excess_value_m * 0.22).toFixed(1) + 'M'},
      {l: 'Stranded WIP', v: '$' + (k.excess_value_m * 0.18).toFixed(1) + 'M'},
      {l: 'Safety Stock Overrun', v: '$' + (k.excess_value_m * 0.12).toFixed(1) + 'M'},
    ])) +
    _dn('$' + (k.excess_value_m * 0.48).toFixed(1) + 'M of slow-moving FG is redeployable via lateral DC transfers or promotional pull. Recommend immediate review with Commercial team.')
  );
}

function renderInvHealthChart(health) {
  const ctx = document.getElementById('inv-health-chart');
  if (!ctx) return;
  if (_invHealthChart) _invHealthChart.destroy();

  const data = [health.optimal, health.excess, health.at_risk, health.stockout];
  const labels = ['Optimal', 'Excess', 'At Risk', 'Stockout'];
  const colors = [GREEN, AMBER, ORANGE, RED];

  _invHealthChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors.map(c => _alpha(c, 0.8)), borderColor: colors, borderWidth: 1, hoverOffset: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw.toLocaleString()} SKUs` } },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx   = elements[0].index;
        const label = chart.data.labels[idx];
        const count = chart.data.datasets[0].data[idx];
        const skuExamples = {
          'Optimal':  [{l: 'FG-33201 Assembly Kit', v: '28d DOS'}, {l: 'RM-10482 Steel Billet', v: '31d DOS'}, {l: 'FG-44109 Motor Unit', v: '26d DOS'}],
          'Excess':   [{l: 'FG-78421 Sprocket Assy', v: '87d DOS'}, {l: 'RM-20091 Polymer Resin', v: '94d DOS'}, {l: 'FG-60112 Housing Cover', v: '71d DOS'}],
          'At Risk':  [{l: 'FG-22310 Bearing Set', v: '8d DOS'}, {l: 'RM-50041 Copper Coil', v: '6d DOS'}, {l: 'FG-48801 Valve Body', v: '9d DOS'}],
          'Stockout': [{l: 'FG-55102 Hydraulic Pump', v: '0d — CRITICAL'}, {l: 'FG-91033 Drive Belt XL', v: '0d — CRITICAL'}],
        };
        const examples = skuExamples[label] || [];
        openDrill(`SKU Health — ${label} (${count.toLocaleString()} SKUs)`,
          _ds('Sample SKUs', _dr(examples)) +
          _dn(label === 'Stockout' ? 'Immediate action required. Emergency POs are recommended for both stockout items.' :
              label === 'Excess'   ? 'Excess inventory represents $' + (count * 0.0022).toFixed(1) + 'M in trapped capital. Lateral transfers and promotions can resolve 60% within 30 days.' :
              label === 'At Risk'  ? count + ' SKUs are within 10 days of stockout. Replenishment orders should be raised this week.' :
              count.toLocaleString() + ' SKUs are within target DOS range. Continue monitoring weekly.')
        );
      },
    },
  });

  // Legend
  const legend = document.getElementById('inv-health-legend');
  if (legend) {
    legend.innerHTML = labels.map((l, i) => `
      <div class="legend-item">
        <div class="legend-dot" style="background:${colors[i]}"></div>
        <span>${l}: <strong>${data[i].toLocaleString()}</strong></span>
      </div>`).join('');
  }
}

function renderInvWarehouseChart(warehouses) {
  const ctx = document.getElementById('inv-warehouse-chart');
  if (!ctx) return;
  if (_invWareChart) _invWareChart.destroy();

  _invWareChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: warehouses.map(w => `${w.name} (${w.code})`),
      datasets: [
        {
          label: 'Utilization %',
          data: warehouses.map(w => w.utilization),
          backgroundColor: warehouses.map(w =>
            w.utilization > 88 ? _alpha(RED, 0.7) :
            w.utilization > 80 ? _alpha(AMBER, 0.7) : _alpha(BLUE, 0.7)),
          borderRadius: 5,
          barPercentage: 0.55,
          yAxisID: 'y',
        },
        {
          label: 'Days of Supply',
          data: warehouses.map(w => w.dos),
          type: 'line',
          borderColor: GREEN,
          backgroundColor: 'transparent',
          tension: 0.3,
          pointRadius: 4,
          borderWidth: 2,
          yAxisID: 'y2',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: c => c.datasetIndex === 0
              ? ` Utilization: ${c.raw}%`
              : ` Days of Supply: ${c.raw}d`,
          },
        },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx  = elements[0].index;
        const w    = warehouses[idx];
        if (!w) return;
        openDrill(`${w.name} (${w.code}) — DC Detail`,
          _ds('Key Metrics', _dr([
            {l: 'Utilization', v: w.utilization + '%'},
            {l: 'Days of Supply', v: w.dos + ' days'},
            {l: 'Status', v: w.utilization > 88 ? '🔴 Critical' : w.utilization > 80 ? '🟡 Watch' : '🟢 Normal'},
          ])) +
          _ds('Top SKUs by Volume', _dr([
            {l: 'FG-' + (33000 + idx * 1200) + ' Assembly', v: Math.round(w.utilization * 0.14) + '% of space'},
            {l: 'RM-' + (10000 + idx * 800) + ' Raw Mat.', v: Math.round(w.utilization * 0.09) + '% of space'},
            {l: 'FG-' + (44000 + idx * 600) + ' Component', v: Math.round(w.utilization * 0.07) + '% of space'},
          ])) +
          _dn(w.utilization > 88
            ? `${w.name} is at ${w.utilization}% capacity — above the 88% safety threshold. Inbound shipments should be rerouted or lateral transfers initiated to avoid a freeze on receipts.`
            : `${w.name} is operating within normal parameters at ${w.utilization}% utilization.`)
        );
      },
      scales: {
        x:  { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 20 } },
        y:  { grid: { color: 'rgba(255,255,255,0.04)' }, min: 0, max: 100, ticks: { callback: v => v + '%' } },
        y2: { position: 'right', grid: { display: false }, ticks: { callback: v => v + 'd', font: { size: 10 } } },
      },
    },
  });
}

function renderInvDosChart(cats) {
  const ctx = document.getElementById('inv-dos-chart');
  if (!ctx) return;
  if (_invDosChart) _invDosChart.destroy();

  _invDosChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cats.map(c => c.name),
      datasets: [
        {
          label: 'Days of Supply',
          data: cats.map(c => c.dos),
          backgroundColor: cats.map(c =>
            c.dos > c.hi ? _alpha(AMBER, 0.7) :
            c.dos < c.lo ? _alpha(RED, 0.7) : _alpha(GREEN, 0.7)),
          borderRadius: 5,
          barPercentage: 0.6,
        },
        {
          label: 'Optimal Min',
          data: cats.map(c => c.lo),
          type: 'line',
          borderColor: _alpha(GREEN, 0.5),
          borderDash: [4, 3],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
        {
          label: 'Optimal Max',
          data: cats.map(c => c.hi),
          type: 'line',
          borderColor: _alpha(AMBER, 0.5),
          borderDash: [4, 3],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.raw} days` } },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx = elements[0].index;
        const cat = cats[idx];
        if (!cat) return;
        const status = cat.dos > cat.hi ? 'Excess' : cat.dos < cat.lo ? 'Stockout Risk' : 'Optimal';
        openDrill(`Days of Supply — ${cat.name}`,
          _ds('Position', _dr([
            {l: 'Current DOS', v: cat.dos + ' days'},
            {l: 'Optimal Min', v: cat.lo + ' days'},
            {l: 'Optimal Max', v: cat.hi + ' days'},
            {l: 'Status', v: status},
          ])) +
          _dn(cat.dos > cat.hi
            ? `${cat.name} is ${cat.dos - cat.hi} days above the optimal ceiling. Recommend halting replenishment orders for this category until DOS drops below ${cat.hi} days.`
            : cat.dos < cat.lo
            ? `${cat.name} is ${cat.lo - cat.dos} days below the safety minimum. Emergency replenishment required within 48 hours to avoid customer service impact.`
            : `${cat.name} is within the optimal ${cat.lo}–${cat.hi} day range. Continue standard replenishment cadence.`)
        );
      },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { callback: v => v + 'd' } },
      },
    },
  });
}

function renderInvAlerts(alerts) {
  const el = document.getElementById('inv-alerts-list');
  if (!el) return;
  const typeLabel = { excess: 'Excess', stockout: 'Stockout', at_risk: 'At Risk' };
  const remediation = {
    stockout: 'Raise emergency PO immediately. Select expedited shipping. Alert customer service team to manage order commitments.',
    at_risk:  'Issue standard replenishment PO within 24 hours. Monitor daily until DOS exceeds safety minimum.',
    excess:   'Halt replenishment orders. Evaluate lateral DC transfer or promotional pull to reduce position within 30 days.',
  };
  el.innerHTML = alerts.map(a => {
    const drillContent =
      _ds('Alert Detail', _dr([
        {l: 'SKU', v: a.sku}, {l: 'Description', v: a.desc},
        {l: 'Location', v: a.location}, {l: 'Days of Supply', v: a.dos + 'd'},
        {l: 'Value', v: '$' + a.value_k + 'K'}, {l: 'Alert Type', v: typeLabel[a.type]},
      ])) +
      _dn(`<strong>Recommended Action:</strong> ${remediation[a.type] || 'Review with supply chain team.'}`);
    return `
      <div class="inv-alert-row ${a.type} clickable" onclick="openStoredDrill(${JSON.stringify(_storeDrill(esc(a.sku) + ' — ' + typeLabel[a.type], drillContent))})">
        <div class="inv-alert-sku">${esc(a.sku)}</div>
        <div class="inv-alert-desc">${esc(a.desc)}</div>
        <div class="inv-alert-meta">${esc(a.location)} · ${a.dos}d</div>
        <div><span class="badge badge-${a.type === 'at_risk' ? 'medium' : a.type === 'stockout' ? 'high' : 'medium'}">${typeLabel[a.type]}</span></div>
        <div class="inv-alert-value">$${a.value_k}K</div>
      </div>`;
  }).join('');
}

// ── Demand ────────────────────────────────────────────────────────────────────
async function fetchDemand() {
  try {
    const d = await (await fetch('/supply-chain/api/demand')).json();
    _demMapeRaw  = d.category_mape;
    _skuAllData  = d.top_errors;
    _demKpisRaw  = d.kpis;
    _demFaRaw    = d.forecast_vs_actual;
    _demTrendRaw = d.mape_trend;
    renderDemKpis(d.kpis);
    renderDemFaChart(d.forecast_vs_actual);
    renderDemMapeChart(d.category_mape);
    renderDemTrendChart(d.mape_trend);
    renderDemErrorsTable(d.top_errors);
  } catch (e) { console.error('Demand fetch error', e); }
}

function renderDemKpis(k) {
  setKpiCard('dem-k1', parseFloat(k.mape.toFixed(2)) + '%', k.mape <= 10 ? GREEN : AMBER, 'Forecast MAPE — Detail',
    _ds('By Category', _dr([
      {l: 'Finished Goods', v: (k.mape + 2.1) + '%'}, {l: 'Raw Materials', v: (k.mape - 1.3) + '%'},
      {l: 'MRO / Spare Parts', v: (k.mape + 5.8) + '%'}, {l: 'WIP', v: (k.mape - 0.4) + '%'},
    ])) +
    _ds('Model Comparison', _dr([
      {l: 'Databricks ML (current)', v: k.mape + '%'},
      {l: 'Legacy Statistical', v: (k.mape + 4.9) + '%'},
      {l: 'Industry Best Practice', v: '7–9%'},
    ])) +
    _dn('MRO/Spare Parts shows the highest MAPE due to intermittent demand patterns. A separate intermittent demand model is in development and expected to reduce this category by 4pp.')
  );
  setKpiCard('dem-k2', k.bias + '%', Math.abs(k.bias) < 3 ? GREEN : AMBER, 'Forecast Bias — Detail',
    _ds('Bias Analysis', _dr([
      {l: 'Overall Bias', v: k.bias + '%'},
      {l: 'Finished Goods', v: '-2.3%'}, {l: 'Raw Materials', v: '+0.8%'},
      {l: 'MRO', v: '-1.1%'},
    ])) +
    _dn('Negative bias on Finished Goods means we are systematically under-forecasting, leading to stock shortfalls. The FG-55102 stockout is directly linked to a persistent -6.2% bias on that SKU family.')
  );
  setKpiCard('dem-k3', '+' + k.forecast_value_add + '%', '#f0f0f0', 'Forecast Value Add — Detail',
    _ds('FVA Breakdown', _dr([
      {l: 'ML Model vs Naïve', v: '+' + k.forecast_value_add + '%'},
      {l: 'Human Override Value Add', v: '+2.1%'},
      {l: 'Human Override Degradation', v: '-0.8%'},
      {l: 'Net Human Contribution', v: '+1.3%'},
    ])) +
    _dn('On average, human overrides add 1.3pp of forecast accuracy. However, 18% of overrides actually increase error — review with demand planners which SKUs to exclude from manual adjustment.')
  );
  setKpiCard('dem-k4', k.skus_forecast.toLocaleString(), '#f0f0f0', 'SKUs Forecast — Detail',
    _ds('Coverage', _dr([
      {l: 'Total Active SKUs', v: k.skus_forecast.toLocaleString()},
      {l: 'ML Model Coverage', v: (k.skus_forecast - 124).toLocaleString() + ' SKUs'},
      {l: 'Statistical Only', v: '124 SKUs'},
      {l: 'Not Forecasted', v: '0 SKUs'},
    ])) +
    _dn('124 SKUs with fewer than 6 months of history are forecast using a statistical fallback. These are candidates for ML model inclusion once sufficient data accumulates.')
  );
}

function renderDemFaChart(data) {
  const ctx = document.getElementById('dem-fa-chart');
  if (!ctx) return;
  if (_demFaChart) _demFaChart.destroy();

  const _faReasons = data.map(d => d.reason || '');

  _demFaChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.month),
      datasets: [
        {
          label: 'Forecast',
          data: data.map(d => d.forecast),
          borderColor: PURPLE,
          backgroundColor: _alpha(PURPLE, 0.08),
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 3,
        },
        {
          label: 'Actual',
          data: data.map(d => d.actual),
          borderColor: BLUE,
          backgroundColor: 'transparent',
          borderDash: [5, 3],
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.raw.toLocaleString()} units` } },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx      = elements[0].index;
        const month    = chart.data.labels[idx];
        const forecast = chart.data.datasets[0].data[idx];
        const actual   = chart.data.datasets[1].data[idx];
        if (actual == null) return;
        const mape   = (Math.abs(forecast - actual) / actual * 100).toFixed(1);
        const bias   = ((forecast - actual) / actual * 100).toFixed(1);
        const dir    = forecast > actual ? 'Over-forecast' : forecast < actual ? 'Under-forecast' : 'On target';
        const dirCol = forecast > actual ? 'var(--accent-amber)' : forecast < actual ? '#ef4444' : 'var(--accent-green)';
        const reason = _faReasons[idx] || '';
        openDrill(`Forecast vs Actual — ${month}`,
          _ds('Monthly Detail', _dr([
            {l: 'Forecast', v: forecast.toLocaleString() + ' units'},
            {l: 'Actual',   v: actual.toLocaleString() + ' units'},
            {l: 'Variance', v: (forecast > actual ? '+' : '') + (forecast - actual).toLocaleString() + ' units'},
            {l: 'MAPE',     v: mape + '%'},
            {l: 'Bias',     v: (bias > 0 ? '+' : '') + bias + '%'},
            {l: 'Direction',v: `<span style="color:${dirCol};font-weight:700">${dir}</span>`},
          ])) +
          (reason ? _ds('Reason for Variance', `<div class="drill-why">${esc(reason)}</div>`) : '') +
          _dn(Math.abs(bias) > 5
            ? `A ${Math.abs(bias)}% ${forecast > actual ? 'over' : 'under'}-forecast in ${month}. Review the variance reason above and update model inputs for the next planning cycle.`
            : `Forecast accuracy was within normal range for ${month} — no corrective action required.`)
        );
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxRotation: 45, font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { callback: v => (v/1000).toFixed(0) + 'K' } },
      },
    },
  });
}

function renderDemMapeChart(cats) {
  const ctx = document.getElementById('dem-mape-chart');
  if (!ctx) return;
  if (_demMapeChart) _demMapeChart.destroy();

  _demMapeChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cats.map(c => c.category),
      datasets: [
        {
          label: 'MAPE %',
          data: cats.map(c => c.mape),
          backgroundColor: cats.map(c => c.mape > 15 ? _alpha(RED, 0.7) : c.mape > 10 ? _alpha(AMBER, 0.7) : _alpha(PURPLE, 0.7)),
          borderRadius: 5,
          barPercentage: 0.6,
        },
        {
          label: 'Target 10%',
          data: cats.map(() => 10),
          type: 'line',
          borderColor: _alpha(GREEN, 0.6),
          borderDash: [5, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.raw}%` } },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx  = elements[0].index;
        const cat  = cats[idx];
        if (!cat) return;
        openDrill(`MAPE by Category — ${cat.category}`,
          _ds('Accuracy Metrics', _dr([
            {l: 'MAPE', v: cat.mape + '%'}, {l: 'Target', v: '10%'},
            {l: 'Gap vs Target', v: (cat.mape - 10).toFixed(1) + 'pp'},
            {l: 'Status', v: cat.mape <= 10 ? '✓ On Target' : cat.mape <= 15 ? '⚠ Watch' : '🔴 Critical'},
          ])) +
          _dn(cat.mape > 15
            ? `${cat.category} MAPE is ${cat.mape - 10}pp above target. Primary causes are typically demand volatility and insufficient history. Recommend review of model parameters and override policy.`
            : cat.mape > 10
            ? `${cat.category} is slightly above the 10% target. Monitor for next 2 cycles before escalating.`
            : `${cat.category} is meeting the accuracy target. No action required.`)
        );
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 20 } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { callback: v => v + '%' } },
      },
    },
  });
}

function renderDemTrendChart(trend) {
  const ctx = document.getElementById('dem-trend-chart');
  if (!ctx) return;
  if (_demTrendChart) _demTrendChart.destroy();

  _demTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trend.map(d => d.month),
      datasets: [
        {
          label: 'MAPE %',
          data: trend.map(d => d.mape),
          borderColor: PURPLE,
          backgroundColor: _alpha(PURPLE, 0.1),
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 3,
        },
        {
          label: 'Target 10%',
          data: trend.map(() => 10),
          borderColor: _alpha(GREEN, 0.5),
          borderDash: [5, 4],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxRotation: 45, font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, min: 6, ticks: { callback: v => v + '%' } },
      },
    },
  });
}

function renderDemErrorsTable(errors) {
  _skuErrorData = errors;
  const tbody = document.querySelector('#dem-errors-table tbody');
  if (!tbody) return;
  tbody.innerHTML = errors.map((e, idx) => {
    const biasColor = e.bias < 0 ? RED : GREEN;
    return `<tr class="clickable" onclick="openSkuDrill(${idx})">
      <td style="font-weight:600;color:var(--text-primary)">${esc(e.sku)}</td>
      <td>${esc(e.desc)}</td>
      <td style="color:${e.mape > 20 ? RED : e.mape > 12 ? AMBER : 'var(--text-secondary)'};font-weight:600">${e.mape}%</td>
      <td style="color:${biasColor};font-weight:600">${e.bias > 0 ? '+' : ''}${e.bias}%</td>
    </tr>`;
  }).join('');
}

function openSkuDrill(idx) {
  const e = _skuErrorData[idx];
  if (!e) return;
  const errorType = e.bias < -5 ? 'Systematic Under-Forecast' : e.bias > 5 ? 'Systematic Over-Forecast' : 'Random Error';
  const insight = e.mape > 25
    ? `${e.sku} has critical forecast error. Human overrides are likely the cause — review with the demand planner responsible for this SKU and consider model-only forecasting.`
    : e.bias < -5
    ? `${e.sku} is consistently under-forecast, risking stockouts. Review if seasonal patterns or promotions are missing from the model.`
    : `${e.sku} shows elevated but manageable error. Standard monitoring and review cycle applies.`;

  const statsHtml = _ds('Forecast Performance', _dr([
    {l: 'SKU',        v: e.sku},
    {l: 'Description',v: e.desc},
    {l: 'MAPE',       v: `<span style="color:${e.mape > 20 ? RED : e.mape > 12 ? AMBER : 'var(--text-secondary)'};font-weight:600">${e.mape}%</span>`},
    {l: 'Bias',       v: `<span style="color:${e.bias < 0 ? RED : GREEN};font-weight:600">${e.bias > 0 ? '+' : ''}${e.bias}%</span>`},
    {l: 'Error Type', v: errorType},
    {l: 'Last Actual',v: e.last_actual ? e.last_actual.toLocaleString() + ' units' : '—'},
  ]));

  const chartId = 'sku-drill-chart-' + idx;
  const chartHtml = `<div class="drill-section"><div class="drill-section-title">12-Month Forecast vs Actual</div>
    <div style="position:relative;height:200px;margin-top:8px"><canvas id="${chartId}"></canvas></div></div>`;

  openDrill(`${esc(e.sku)} — Forecast Analysis`, statsHtml + chartHtml + _dn(insight));

  // Render Chart.js after DOM update
  requestAnimationFrame(() => {
    const canvas = document.getElementById(chartId);
    if (!canvas || !e.history || !e.history.length) return;
    const labels   = e.history.map(d => d.month);
    const actuals  = e.history.map(d => d.actual);
    const forecasts= e.history.map(d => d.forecast);
    new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Actual',   data: actuals,   borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', tension: 0.3, pointRadius: 3, fill: false },
          { label: 'Forecast', data: forecasts, borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.1)',  tension: 0.3, pointRadius: 3, borderDash: [4,3], fill: false },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
          tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.raw.toLocaleString()} units` } },
        },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#9ca3af', maxRotation: 45, font: { size: 10 } } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#9ca3af', callback: v => v.toLocaleString() } },
        },
      },
    });
  });
}

// ── Orders ────────────────────────────────────────────────────────────────────
async function fetchOrders() {
  try {
    const d = await (await fetch('/supply-chain/api/orders')).json();
    _ordKpisRaw  = d.kpis;
    _ordVolRaw   = d.order_volume;
    _ordAutoRaw  = d.automation_trend;
    renderOrdKpis(d.kpis);
    renderOrdVolChart(d.order_volume);
    renderOrdExceptions(d.exceptions);
    renderOrdAutoChart(d.automation_trend);
    renderOrdSupplierTable(d.suppliers);
  } catch (e) { console.error('Orders fetch error', e); }
}

function renderOrdKpis(k) {
  setKpiCard('ord-k1', k.automation_rate + '%', k.automation_rate >= 80 ? GREEN : AMBER, 'Order Automation Rate — Detail',
    _ds('By PO Type', _dr([
      {l: 'Blanket / Scheduled', v: '97.2%'}, {l: 'Spot / Ad-hoc', v: '61.3%'},
      {l: 'Intercompany', v: '99.1%'}, {l: 'Catalog', v: '88.4%'},
    ])) +
    _ds('6-Month Trend', _dr([
      {l: 'Nov', v: '71.2%'}, {l: 'Jan', v: '73.8%'}, {l: 'Mar', v: '76.1%'},
      {l: 'May (current)', v: k.automation_rate + '%'},
    ])) +
    _dn('Spot PO automation at 61.3% is the biggest opportunity. AI contract matching can push this to 85%+ by automatically applying best-match supplier pricing from the approved vendor list.')
  );
  setKpiCard('ord-k2', k.avg_cycle_hours + 'h', '#f0f0f0', 'Order Cycle Time — Detail',
    _ds('Stage Breakdown', _dr([
      {l: 'PO Creation', v: '0.8h'}, {l: 'Supplier Acknowledgement', v: '4.2h'},
      {l: 'ERP Confirmation', v: '1.1h'}, {l: 'Exception Handling', v: (k.avg_cycle_hours - 6.1).toFixed(1) + 'h'},
      {l: 'Total Avg', v: k.avg_cycle_hours + 'h'},
    ])) +
    _dn('Exception handling adds ' + (k.avg_cycle_hours - 6.1).toFixed(1) + 'h average latency. The 47 open price discrepancy exceptions are the primary driver — resolving Pacific Components contract will reduce average cycle time by ~1.8h.')
  );
  setKpiCard('ord-k3', k.exceptions_open, k.exceptions_open > 30 ? RED : AMBER, 'Open Exceptions — Detail',
    _ds('By Type', _dr([
      {l: 'Price Discrepancy', v: '18'}, {l: 'Missing PO Reference', v: '12'},
      {l: 'Unmatched Invoice', v: '9'}, {l: 'Delivery Date Conflict', v: '8'},
    ])) +
    _ds('By Priority', _dr([
      {l: 'High Priority (>$10K)', v: '32'}, {l: 'Medium Priority', v: '15'},
    ])) +
    _dn('18 of the 47 exceptions are from a single supplier (Pacific Components) and relate to a contract renewal gap. Resolving this single issue clears 38% of the queue and releases $143K.')
  );
  setKpiCard('ord-k4', k.on_time_delivery + '%', k.on_time_delivery >= 92 ? GREEN : AMBER, 'On-Time Delivery — Detail',
    _ds('By Supplier Tier', _dr([
      {l: 'Tier 1 (Top 10)', v: '96.2%'}, {l: 'Tier 2 (Mid)', v: k.on_time_delivery + '%'},
      {l: 'Tier 3 (Spot)', v: '81.4%'},
    ])) +
    _ds('Late Delivery Impact', _dr([
      {l: 'Production Disruptions', v: '3 events this month'},
      {l: 'Revenue at Risk', v: '$840K'},
      {l: 'Worst Performer', v: 'EuroTech 79.3%'},
    ])) +
    _dn('EuroTech\'s 79.3% OTD on 54 open POs is a concentration risk. A contract penalty review and dual-sourcing plan is recommended before Q3 volume increases.')
  );
}

function renderOrdVolChart(vol) {
  const ctx = document.getElementById('ord-vol-chart');
  if (!ctx) return;
  if (_ordVolChart) _ordVolChart.destroy();

  _ordVolChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: vol.map(v => v.month),
      datasets: [
        {
          label: 'Automated',
          data: vol.map(v => v.automated),
          backgroundColor: _alpha(BLUE, 0.75),
          borderRadius: 4,
          stack: 'orders',
        },
        {
          label: 'Manual',
          data: vol.map(v => v.manual),
          backgroundColor: _alpha(MUTED, 0.5),
          borderRadius: 4,
          stack: 'orders',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
        tooltip: {
          callbacks: {
            afterBody: items => {
              const auto = items[0]?.raw || 0;
              const total = (items[0]?.raw || 0) + (items[1]?.raw || 0);
              return [`Automation: ${total ? ((auto / total) * 100).toFixed(1) : 0}%`];
            },
          },
        },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx     = elements[0].index;
        const month   = chart.data.labels[idx];
        const auto    = chart.data.datasets[0].data[idx];
        const manual  = chart.data.datasets[1].data[idx];
        const total   = auto + manual;
        const rate    = total ? ((auto / total) * 100).toFixed(1) : 0;
        openDrill(`Order Volume — ${month}`,
          _ds('Monthly Breakdown', _dr([
            {l: 'Total POs', v: total.toLocaleString()},
            {l: 'Automated', v: auto.toLocaleString() + ' (' + rate + '%)'},
            {l: 'Manual', v: manual.toLocaleString()},
            {l: 'Automation Rate', v: rate + '%'},
          ])) +
          _dn(manual > 300
            ? `${month} had elevated manual processing (${manual} POs). The peak is correlated with the Pacific Components exception cluster. Resolving the contract renewal will automate ~${Math.round(manual * 0.38)} of these.`
            : `${month} order volume was within normal range. Automation rate of ${rate}% is ${rate >= 80 ? 'meeting' : 'approaching'} the 80% target.`)
        );
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, stacked: true },
      },
    },
  });
}

function renderOrdExceptions(exceptions) {
  const el = document.getElementById('exception-list');
  if (!el) return;

  el.innerHTML = exceptions.map(ex => {
    // ── PO list table ───────────────────────────────────────────────────────
    const poRows = (ex.pos || []).map(p => `
      <tr>
        <td style="font-family:monospace;font-size:11px;color:var(--accent-blue)">${esc(p.po)}</td>
        <td style="font-size:12px">${esc(p.supplier)}</td>
        <td style="font-size:12px">${esc(p.material)}</td>
        <td style="font-size:12px;color:var(--accent-amber);font-weight:600;white-space:nowrap">$${p.value_k}K</td>
        <td style="font-size:11px;color:var(--text-muted);white-space:nowrap">${p.age_days}d</td>
        <td style="font-size:11px;color:var(--text-secondary);line-height:1.4">${esc(p.issue)}</td>
      </tr>`).join('');

    const poTable = ex.pos && ex.pos.length ? `
      <div class="drill-section">
        <div class="drill-section-title">Purchase Orders (${ex.pos.length} shown${ex.count > ex.pos.length ? ' of ' + ex.count : ''})</div>
        <div style="overflow-x:auto;margin-top:6px">
          <table style="width:100%;border-collapse:collapse;font-size:12px">
            <thead>
              <tr style="border-bottom:1px solid var(--border)">
                <th style="text-align:left;padding:4px 8px 6px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)">PO #</th>
                <th style="text-align:left;padding:4px 8px 6px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)">Supplier</th>
                <th style="text-align:left;padding:4px 8px 6px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)">Material</th>
                <th style="text-align:left;padding:4px 8px 6px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)">Value</th>
                <th style="text-align:left;padding:4px 8px 6px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)">Age</th>
                <th style="text-align:left;padding:4px 0 6px 0;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted)">Issue Detail</th>
              </tr>
            </thead>
            <tbody style="border-collapse:collapse">
              ${poRows}
            </tbody>
          </table>
        </div>
      </div>` : '';

    // ── Agentic recommendations ──────────────────────────────────────────────
    const recItems = (ex.recommendations || []).map((r, i) => {
      const typeCol  = r.type === 'auto' ? 'var(--accent-green)' : 'var(--accent-blue)';
      const typeLabel = r.type === 'auto' ? 'Auto-resolve' : 'Manual action';
      const impCol   = r.impact === 'High' ? '#ef4444' : r.impact === 'Medium' ? 'var(--accent-amber)' : 'var(--text-muted)';
      return `<div style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.04);align-items:flex-start">
        <div style="flex-shrink:0;width:20px;height:20px;border-radius:50%;background:rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--text-muted);margin-top:1px">${i + 1}</div>
        <div style="flex:1">
          <div style="font-size:12.5px;color:var(--text-secondary);line-height:1.5">${esc(r.action)}</div>
          <div style="display:flex;gap:8px;margin-top:5px">
            <span style="font-size:10px;font-weight:700;color:${typeCol};text-transform:uppercase;letter-spacing:.05em">${typeLabel}</span>
            <span style="font-size:10px;color:var(--text-muted)">·</span>
            <span style="font-size:10px;font-weight:700;color:${impCol}">Impact: ${r.impact}</span>
          </div>
        </div>
      </div>`;
    }).join('');

    const recsHtml = ex.recommendations && ex.recommendations.length
      ? `<div class="drill-section">
          <div class="drill-section-title">AI Recommendations</div>
          ${recItems}
        </div>` : '';

    const drillContent =
      _ds('Exception Summary', _dr([
        {l: 'Total POs',   v: ex.count},
        {l: 'Value Held',  v: '$' + ex.value_k + 'K'},
        {l: 'Avg Age',     v: ex.aging_days + ' days'},
        {l: 'Priority',    v: `<span style="color:${ex.priority === 'high' ? '#ef4444' : 'var(--accent-amber)'};font-weight:700;text-transform:capitalize">${ex.priority}</span>`},
      ])) +
      (ex.root_cause ? `<div class="drill-section"><div class="drill-section-title">Root Cause Analysis</div><div class="drill-why" style="margin-top:4px">${esc(ex.root_cause)}</div></div>` : '') +
      poTable +
      recsHtml;

    return `
      <div class="exception-row ${ex.priority} clickable" onclick="openStoredDrill(${JSON.stringify(_storeDrill(esc(ex.type) + ' — Exception Detail', drillContent))})">
        <div class="exception-count ${ex.priority}">${ex.count}</div>
        <div class="exception-info">
          <div class="exception-type">${esc(ex.type)}</div>
          <div class="exception-meta">Avg age: ${ex.aging_days} days · ${ex.priority === 'high' ? 'High priority' : 'Medium priority'}</div>
        </div>
        <div class="exception-value">$${ex.value_k}K</div>
      </div>`;
  }).join('');
}

function renderOrdAutoChart(trend) {
  const ctx = document.getElementById('ord-auto-chart');
  if (!ctx) return;
  if (_ordAutoChart) _ordAutoChart.destroy();

  _ordAutoChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trend.map(d => d.month),
      datasets: [
        {
          label: 'Automation Rate %',
          data: trend.map(d => d.rate),
          borderColor: BLUE,
          backgroundColor: _alpha(BLUE, 0.1),
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 3,
        },
        {
          label: 'Target 80%',
          data: trend.map(() => 80),
          borderColor: _alpha(GREEN, 0.5),
          borderDash: [5, 4],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top', labels: { color: '#9ca3af', boxWidth: 10, font: { size: 10 } } },
      },
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const idx   = elements[0].index;
        const month = chart.data.labels[idx];
        const rate  = chart.data.datasets[0].data[idx];
        openDrill(`Automation Rate — ${month}`,
          _ds('Monthly Detail', _dr([
            {l: 'Automation Rate', v: rate + '%'}, {l: 'Target', v: '80%'},
            {l: 'Gap vs Target', v: (rate - 80).toFixed(1) + 'pp'},
          ])) +
          _dn(rate >= 80
            ? `Automation target met in ${month} at ${rate}%. Key driver: blanket PO expansion with top 5 suppliers.`
            : `${month} was ${(80 - rate).toFixed(1)}pp below the 80% target. Exception volume was elevated — focus on resolving price discrepancy exceptions to recover.`)
        );
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxRotation: 45, font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, min: 60, max: 90, ticks: { callback: v => v + '%' } },
      },
    },
  });
}

function renderOrdSupplierTable(suppliers) {
  const tbody = document.querySelector('#ord-supplier-table tbody');
  if (!tbody) return;
  if (_supplierRaw.length === 0) _supplierRaw = suppliers; // store original on first call
  const sortedSuppliers = [...suppliers].sort((a, b) => b.otd - a.otd);
  tbody.innerHTML = sortedSuppliers.map(s => {
    const cls = s.otd >= 93 ? 'otd-good' : s.otd >= 87 ? 'otd-warn' : 'otd-bad';
    const risk = s.otd < 87 ? 'High' : s.otd < 93 ? 'Medium' : 'Low';
    const drillContent =
      _ds('Supplier Scorecard', _dr([
        {l: 'On-Time Delivery', v: s.otd + '%'},
        {l: 'Country', v: s.country},
        {l: 'Open POs', v: s.pos},
        {l: 'Annual Spend', v: '$' + s.spend_m + 'M'},
        {l: 'Risk Level', v: risk},
      ])) +
      _ds('Performance Trend (Est.)', _dr([
        {l: '3 Months Ago', v: (s.otd + 1.2).toFixed(1) + '%'},
        {l: '2 Months Ago', v: (s.otd + 0.5).toFixed(1) + '%'},
        {l: 'Current', v: s.otd + '%'},
      ])) +
      _dn(s.otd < 87
        ? `${s.name} is a high-risk supplier at ${s.otd}% OTD with ${s.pos} open POs. Recommend dual-sourcing review and contract penalty clause activation.`
        : s.otd < 93
        ? `${s.name} is approaching the 93% OTD threshold. Monitor closely and schedule a supplier performance review.`
        : `${s.name} is a strong performer at ${s.otd}% OTD. Consider for preferred supplier status and increased volume allocation.`);
    const key = _storeDrill(esc(s.name) + ' — Supplier Scorecard', drillContent);
    return `<tr class="clickable" onclick="openStoredDrill(${JSON.stringify(key)})">
      <td style="font-weight:600;color:var(--text-primary)">${esc(s.name)}</td>
      <td>${esc(s.country)}</td>
      <td class="${cls}">${s.otd}%</td>
      <td>${s.pos}</td>
      <td>$${s.spend_m}M</td>
    </tr>`;
  }).join('');
}

// ── Talk Track ────────────────────────────────────────────────────────────────
const TAB_LABELS = {
  ibp:       'Integrated Business Planning',
  inventory: 'Inventory & Logistics',
  demand:    'Demand Forecasting',
  orders:    'Order Processing',
  ai:        'Supply Chain AI',
  logistics: 'Logistics Map',
};

const TALK_TRACKS = {
  ibp: {
    what: 'An 18-month integrated business planning view consolidating demand, supply, financial, and capacity plans — with consensus attainment by business unit, revenue at risk, S&OP cycle gate status, and a risk register quantifying open exposure before executive sign-off.',
    aiml: 'ML consensus models detect plan divergence early by comparing statistical demand signals against commercial submissions from each business unit, surfacing gaps weeks before the monthly S&OP review. Scenario simulation quantifies the financial impact of capacity or supply constraints in real time, enabling executives to make data-backed decisions rather than relying on analyst-prepared what-if slides.',
    benchmark: 'Procter & Gamble’s integrated business planning process is widely cited in supply chain and consulting literature as the benchmark for cross-functional planning maturity. Gartner recognizes S&OP capability as a primary differentiator in its annual Supply Chain Top 25 ranking. McKinsey research shows top-quartile S&OP performers carry 15–20% less inventory and achieve 5–10% higher customer service levels than median peers.',
  },
  inventory: {
    what: 'SKU-level inventory health across all distribution centers — days of supply, stockout risk, overstock exposure, and warehouse utilization — aggregated from ERP and WMS systems into a single operational view with actionable alerts for lateral transfers and demand rebalancing.',
    aiml: 'ML demand sensing models adjust safety stock levels dynamically based on forward-looking signals — promotions, seasonality, external market data — rather than static reorder points. Cluster analysis groups SKUs by demand volatility and gross margin to apply differentiated replenishment policies, replacing the uniform safety stock rules that simultaneously create stockouts and excess.',
    benchmark: 'McKinsey research estimates AI-driven inventory optimization can reduce inventory holding costs by 20–50% while maintaining or improving service levels. Amazon and Walmart are globally recognized for machine learning-driven inventory management. Zara (Inditex) is among the most cited examples in supply chain literature for rapid replenishment cycles enabled by near-real-time inventory data across its global network.',
  },
  demand: {
    what: 'ML-powered 12-month demand forecasts at the SKU-region level with MAPE tracking, forecast bias analysis, and a comparison of model predictions versus planner overrides — enabling supply planners to see where AI outperforms human judgment and where override policies are adding accuracy.',
    aiml: 'Ensemble models combining gradient boosting, ARIMA, and deep learning generate forecasts that systematically outperform statistical baselines on out-of-sample data. MAPE tracking by SKU category identifies where model accuracy degrades so retraining can be precisely targeted. Forecast Value Add analysis automatically identifies planners whose overrides are hurting rather than helping forecast accuracy.',
    benchmark: 'Unilever publicly reported approximately a 20% reduction in forecast error after deploying AI-based demand sensing — one of the most widely cited supply chain AI case studies. Industry benchmarks show ML ensemble models achieving MAPE of 10–15% for CPG SKUs, versus 20–30% for traditional statistical methods. Amazon’s demand forecasting systems process billions of data points across millions of SKUs and are frequently referenced in both supply chain and ML research literature.',
  },
  orders: {
    what: 'Purchase order health across the supplier network — automation rate, exception queue with dollar value on hold, supplier on-time delivery rankings, and order cycle time — identifying where manual intervention is creating cost and delay in the procure-to-pay process.',
    aiml: 'NLP models extract and classify order exceptions from supplier communications and EDI feeds, automatically routing each exception to the appropriate resolver. Predictive scoring flags suppliers at statistical risk of late delivery based on historical patterns and current lead time signals, enabling buyers to act before a confirmed miss. Intelligent automation handles straight-through processing for routine POs that match contract price and quantity parameters.',
    benchmark: 'McKinsey estimates 50–80% of purchase order processing steps can be automated with AI, reducing cycle times by 30–50%. The Hackett Group benchmarks show top-performing procurement organizations process 60%+ of POs straight-through without manual intervention, versus an industry average below 30%. Siemens and Unilever are widely cited for intelligent procurement automation programs that have materially reduced invoice exception rates and processing costs.',
  },
  ai: {
    what: 'A natural language interface to supply chain data — S&OP metrics, inventory positions, demand forecasts, and order data — grounded in your Delta Lake so analysts and executives can get data-backed answers in seconds rather than waiting for analyst-prepared reports.',
    aiml: 'A large language model with retrieval-augmented generation (RAG) translates natural language questions into SQL queries against Unity Catalog-governed Delta Lake tables. Intent classification ensures responses draw from the correct data domain and metric definitions. Conversation history enables multi-turn analysis — asking follow-up questions to drill into a specific supplier, SKU, or region without re-stating context.',
    benchmark: 'Gartner’s 2023 and 2024 surveys identify conversational analytics as one of the top emerging use cases for supply chain AI adoption. McKinsey’s 2023 report on the economic potential of generative AI estimates it could add $2.6–4.4 trillion annually in value across global supply chains. Nestlé, Procter & Gamble, and Unilever have publicly announced generative AI pilots for supply chain planning teams.',
  },
  logistics: {
    what: 'Real-time truck positions across the distribution network, distribution center operational status, shipment ETAs, and route delay alerts — sourced from TMS and telematics feeds to give supply chain teams live visibility into the delivery pipeline and emerging exceptions.',
    aiml: 'Route optimization algorithms continuously minimize transit time and fuel consumption across the DC network, dynamically rerouting around detected delays or closures. Delay prediction models flag individual shipments at risk of missing delivery windows 24–48 hours in advance, enabling proactive customer communication and load rebalancing before a miss becomes a service failure.',
    benchmark: 'UPS’s ORION (On-Road Integrated Optimization and Navigation) system is widely reported to save approximately 100 million miles per year — consistently cited as the standard industry reference for AI route optimization. DHL and FedEx have both published extensively on AI-driven logistics network optimization. McKinsey estimates AI-driven route optimization can reduce transportation costs by 15–20% in large distribution networks.',
  },
};

function openInfoPanel(key) {
  const track = TALK_TRACKS[key] || TALK_TRACKS[_activeTab] || TALK_TRACKS.ibp;
  const label = TAB_LABELS[key] || key;
  document.getElementById('info-panel-title').textContent = label;
  document.getElementById('info-panel-body').innerHTML = `
    <div class="info-sec-block">
      <div class="info-sec-title">What This Page Shows</div>
      <div class="info-what"><p>${track.what || ''}</p></div>
    </div>
    <div class="info-sec-block">
      <div class="info-sec-title info-sec-ai">How AI &amp; ML Is Applied</div>
      <div class="info-what"><p>${track.aiml || ''}</p></div>
    </div>
    <div class="info-sec-block">
      <div class="info-sec-title info-sec-bench">Industry Benchmarks</div>
      <div class="info-what"><p>${track.benchmark || ''}</p></div>
    </div>
  `;
  document.getElementById('info-overlay').classList.remove('hidden');
}
function closeInfoPanel(e) {
  if (!e || e.target === document.getElementById('info-overlay'))
    document.getElementById('info-overlay').classList.add('hidden');
}

// ── Filter Bar ────────────────────────────────────────────────────────────────
// KPI offsets per period (added to base %; turns offset is ×0.1 applied separately)
const _PERIOD_KPI_ADJ = {
  '':    { plan: 0,    mape: 0,    fill: 0,    otd: 0,    auto: 0,    turns: 0    },
  '30d': { plan: -0.8, mape: 0.6,  fill: -0.3, otd: -0.4, auto: -1.2, turns: 0.1  },
  'q1':  { plan: -1.4, mape: 1.1,  fill: -0.5, otd: 0.6,  auto: -2.8, turns: -0.2 },
  'q2':  { plan: 0.5,  mape: -0.4, fill: 0.3,  otd: -0.3, auto: 1.4,  turns: 0.4  },
  '12m': { plan: 0,    mape: 0,    fill: 0,    otd: 0,    auto: 0,    turns: 0    },
};
// KPI offsets per BU
const _BU_KPI_ADJ = {
  '':     { plan: 0,    mape: 0,    fill: 0,    otd: 0,    auto: 0,    turns: 0    },
  'auto': { plan: 1.3,  mape: -0.9, fill: 0.4,  otd: 0.8,  auto: 2.1,  turns: 0.4  },
  'ind':  { plan: -0.7, mape: 1.4,  fill: -0.4, otd: -0.5, auto: -1.8, turns: -0.3 },
  'cons': { plan: 0.8,  mape: -0.5, fill: 0.7,  otd: 0.3,  auto: 1.3,  turns: 0.9  },
  'elec': { plan: -2.2, mape: 2.3,  fill: -0.9, otd: -1.2, auto: -0.9, turns: 1.1  },
};
// Volume scale per BU (applied to absolute $M / count values)
const _BU_VOL_SCALE = { '': 1.0, 'auto': 0.38, 'ind': 0.22, 'cons': 0.28, 'elec': 0.12 };
// IBP BU-name mapping for BU filter
const _BU_REGION_MAP = {
  auto:  ['North America'],
  ind:   ['EMEA', 'Latin America'],
  cons:  ['APAC'],
  elec:  ['Rest of World'],
};

// Clamp + round a KPI value
function _kAdj(base, ...deltas) {
  return Math.max(0, parseFloat((base + deltas.reduce((a, b) => a + b, 0)).toFixed(1)));
}

// Slice a time-series array by the period filter
function _filterByPeriod(arr, period) {
  if (!arr || !period || period === '12m') return arr;
  if (period === '30d') return arr.slice(-1);
  if (period === 'q1')  return arr.filter(d => /^(Jan|Feb|Mar)/.test(d.month));
  if (period === 'q2')  return arr.filter(d => /^(Apr|May|Jun)/.test(d.month));
  return arr;
}

function applyFilters() {
  const selects = document.querySelectorAll('.filter-select');
  const active = Array.from(selects).filter(s => s.value !== '').length;
  const clearBtn = document.getElementById('filter-clear');
  const countEl  = document.getElementById('filter-count');
  if (clearBtn) clearBtn.classList.toggle('hidden', active === 0);
  if (countEl) {
    countEl.classList.toggle('hidden', active === 0);
    if (active > 0) countEl.textContent = `${active} filter${active > 1 ? 's' : ''} active`;
  }

  const period   = document.getElementById('f-period')?.value   || '';
  const region   = document.getElementById('f-region')?.value   || '';
  const bu       = document.getElementById('f-bu')?.value       || '';
  const category = document.getElementById('f-category')?.value || '';

  const pAdj     = _PERIOD_KPI_ADJ[period] || _PERIOD_KPI_ADJ[''];
  const bAdj     = _BU_KPI_ADJ[bu]         || _BU_KPI_ADJ[''];
  const volScale = _BU_VOL_SCALE[bu]       || 1.0;

  // Shared dimension maps
  const REGION_BUS = { amer: ['North America', 'Latin America'], emea: ['EMEA'], apac: ['APAC', 'Rest of World'] };
  const REGION_WH  = { amer: ['North America', 'Latin America'], emea: ['EMEA'], apac: ['APAC'] };
  const CAT_INV    = { fg: ['Finished Goods'], rm: ['Raw Materials', 'Components', 'Packaging'], wip: ['Work in Progress', 'MRO'] };
  const CAT_MAPE   = { fg: ['Finished Goods'], rm: ['Raw Materials', 'Components'], wip: ['MRO', 'Packaging'] };
  const CAT_ALERT_PREFIX = { fg: 'FG-', rm: 'RM-', wip: 'WIP-' };

  // ── Global KPI strip ───────────────────────────────────────────────────────
  if (_scKpisRaw) {
    const k = _scKpisRaw;
    setText('gkpi-plan',  _kAdj(k.plan_attainment,  pAdj.plan,  bAdj.plan)  + '%');
    setText('gkpi-turns', _kAdj(k.inventory_turns,  (pAdj.turns + bAdj.turns) * 0.1) + 'x');
    setText('gkpi-mape',  _kAdj(k.forecast_mape,    pAdj.mape,  bAdj.mape)  + '%');
    setText('gkpi-auto',  _kAdj(k.order_automation, pAdj.auto,  bAdj.auto)  + '%');
    setText('gkpi-otd',   _kAdj(k.on_time_delivery, pAdj.otd,   bAdj.otd)   + '%');
    setText('gkpi-fill',  _kAdj(k.fill_rate,        pAdj.fill,  bAdj.fill)  + '%');
  }

  // ── IBP tab ────────────────────────────────────────────────────────────────
  if (_ibpPlanOrig) {
    const planSlice = _filterByPeriod(_ibpPlanOrig, period);
    const planBase  = planSlice.length ? planSlice : _ibpPlanOrig;
    const scaledPlan = bu ? planBase.map(d => ({
      ...d,
      consensus:   parseFloat((d.consensus   * volScale).toFixed(1)),
      financial:   parseFloat((d.financial   * volScale).toFixed(1)),
      capacity:    parseFloat((d.capacity    * volScale).toFixed(1)),
      consensus_k: Math.round(d.consensus_k  * volScale),
      financial_k: Math.round(d.financial_k  * volScale),
      capacity_k:  Math.round(d.capacity_k   * volScale),
    })) : planBase;
    renderIbpPlanChart(scaledPlan);
  }
  if (_ibpBuRaw) {
    let filteredBus = _ibpBuRaw;
    if (region) filteredBus = filteredBus.filter(b => (REGION_BUS[region] || []).includes(b.bu));
    if (bu) {
      const names = _BU_REGION_MAP[bu] || [];
      const byBu  = filteredBus.filter(b => names.includes(b.bu));
      if (byBu.length) filteredBus = byBu;
    }
    const adjustedBus = filteredBus.map(b => ({
      ...b, attainment: _kAdj(b.attainment, pAdj.plan, bAdj.plan),
    }));
    renderIbpBuChart(adjustedBus.length ? adjustedBus : _ibpBuRaw);
  }
  if (_ibpRisksRaw) {
    const regionKw = { amer: ['america', 'north am', 'latin', 'canada'], emea: ['emea', 'europe', 'rotterdam'], apac: ['apac', 'asia', 'port congestion', 'pacific', 'china'] };
    const filteredRisks = region && regionKw[region]
      ? _ibpRisksRaw.filter(r => regionKw[region].some(kw => r.item.toLowerCase().includes(kw)))
      : _ibpRisksRaw;
    renderIbpRiskTable(filteredRisks.length ? filteredRisks : _ibpRisksRaw);
  }

  // ── Inventory tab ──────────────────────────────────────────────────────────
  if (_invKpisRaw) {
    const k     = _invKpisRaw;
    const turns = _kAdj(k.inventory_turns, (pAdj.turns + bAdj.turns) * 0.1);
    const doh   = Math.max(1, Math.round(k.days_on_hand - (pAdj.turns + bAdj.turns) * 1.5));
    const fr    = _kAdj(k.fill_rate,      pAdj.fill, bAdj.fill);
    const exc   = parseFloat((k.excess_value_m * volScale).toFixed(1));
    setKpiCard('inv-k1', turns + 'x',    '#f0f0f0');
    setKpiCard('inv-k2', doh   + ' days','#f0f0f0');
    setKpiCard('inv-k3', fr    + '%',    fr >= 97 ? GREEN : AMBER);
    setKpiCard('inv-k4', '$'  + exc + 'M', AMBER);
  }
  if (_invHealthRaw) {
    const h = _invHealthRaw;
    if (category) {
      const CAT_HEALTH_SCALE = { fg: 0.42, rm: 0.30, wip: 0.20 };
      const scale = CAT_HEALTH_SCALE[category] || 1.0;
      renderInvHealthChart({
        optimal:  Math.round(h.optimal  * scale),
        excess:   Math.round(h.excess   * scale),
        at_risk:  Math.round(h.at_risk  * scale),
        stockout: Math.round(h.stockout * scale),
      });
    } else {
      renderInvHealthChart(h);
    }
  }
  if (_invWarehousesRaw) {
    const filteredWh = region
      ? _invWarehousesRaw.filter(w => (REGION_WH[region] || []).includes(w.region))
      : _invWarehousesRaw;
    renderInvWarehouseChart(filteredWh.length ? filteredWh : _invWarehousesRaw);
  }
  if (_invCategoriesRaw) {
    const filteredCats = category
      ? _invCategoriesRaw.filter(c => (CAT_INV[category] || []).includes(c.name))
      : _invCategoriesRaw;
    renderInvDosChart(filteredCats.length ? filteredCats : _invCategoriesRaw);
  }
  if (_invAlertsRaw) {
    let filteredAlerts = _invAlertsRaw;
    if (region) {
      const whForRegion = (REGION_WH[region] || []);
      const regionDcs = (_invWarehousesRaw || []).filter(w => whForRegion.includes(w.region)).map(w => w.name);
      filteredAlerts = filteredAlerts.filter(a => regionDcs.some(dc => a.location === dc));
    }
    if (category) {
      const prefix = CAT_ALERT_PREFIX[category];
      if (prefix) filteredAlerts = filteredAlerts.filter(a => a.sku.startsWith(prefix));
    }
    renderInvAlerts(filteredAlerts.length ? filteredAlerts : _invAlertsRaw);
  }

  // ── Demand tab ─────────────────────────────────────────────────────────────
  if (_demKpisRaw) {
    const k       = _demKpisRaw;
    const adjMape = _kAdj(k.mape, pAdj.mape, bAdj.mape);
    const adjBias = parseFloat((k.bias + pAdj.mape * 0.15 + bAdj.mape * 0.1).toFixed(1));
    setKpiCard('dem-k1', adjMape + '%',                       adjMape <= 10 ? GREEN : AMBER);
    setKpiCard('dem-k2', adjBias + '%',                       Math.abs(adjBias) < 3 ? GREEN : AMBER);
    setKpiCard('dem-k3', '+' + k.forecast_value_add + '%',    '#f0f0f0');
    setKpiCard('dem-k4', k.skus_forecast.toLocaleString(),    '#f0f0f0');
  }
  if (_demFaRaw) {
    const slice = _filterByPeriod(_demFaRaw, period);
    renderDemFaChart(slice.length ? slice : _demFaRaw);
  }
  if (_demMapeRaw) {
    const filteredMape = category
      ? _demMapeRaw.filter(c => (CAT_MAPE[category] || []).includes(c.category))
      : _demMapeRaw;
    renderDemMapeChart(filteredMape.length ? filteredMape : _demMapeRaw);
  }
  if (_demTrendRaw) {
    const slice = _filterByPeriod(_demTrendRaw, period);
    renderDemTrendChart(slice.length ? slice : _demTrendRaw);
  }
  if (_skuAllData.length) {
    const filteredSkus = !category ? _skuAllData : _skuAllData.filter(e => {
      if (category === 'fg')  return e.sku.startsWith('FG-');
      if (category === 'rm')  return e.sku.startsWith('RM-') || e.sku.startsWith('COMP-');
      if (category === 'wip') return e.sku.startsWith('WIP-');
      return true;
    });
    renderDemErrorsTable(filteredSkus.length ? filteredSkus : _skuAllData);
    if (filteredSkus.length) _skuErrorData = filteredSkus;
  }

  // ── Orders tab ─────────────────────────────────────────────────────────────
  if (_ordKpisRaw) {
    const k    = _ordKpisRaw;
    const auto = _kAdj(k.automation_rate,  pAdj.auto, bAdj.auto);
    const otd  = _kAdj(k.on_time_delivery, pAdj.otd,  bAdj.otd);
    setKpiCard('ord-k1', auto + '%',          auto >= 80 ? GREEN : AMBER);
    setKpiCard('ord-k2', k.avg_cycle_hours + 'h', '#f0f0f0');
    setKpiCard('ord-k3', k.exceptions_open,   k.exceptions_open > 30 ? RED : AMBER);
    setKpiCard('ord-k4', otd + '%',           otd >= 92 ? GREEN : AMBER);
  }
  if (_ordVolRaw) {
    const slice    = _filterByPeriod(_ordVolRaw, period);
    const baseData = slice.length ? slice : _ordVolRaw;
    renderOrdVolChart(bu ? baseData.map(d => ({
      ...d,
      automated: Math.round(d.automated * volScale),
      manual:    Math.round(d.manual    * volScale),
      total:     Math.round(d.total     * volScale),
    })) : baseData);
  }
  if (_ordAutoRaw) {
    const slice    = _filterByPeriod(_ordAutoRaw, period);
    const baseData = slice.length ? slice : _ordAutoRaw;
    renderOrdAutoChart(baseData.map(d => ({
      ...d, rate: _kAdj(d.rate, pAdj.auto * 0.3, bAdj.auto * 0.3),
    })));
  }

  // Supplier OTD table (Orders tab) — region filter
  if (_supplierRaw.length) {
    const AMER = ['USA', 'Canada', 'Mexico', 'Brazil', 'Colombia', 'Argentina'];
    const EMEA = ['Germany', 'UK', 'Netherlands', 'France', 'Spain', 'Italy', 'Belgium', 'Sweden', 'Switzerland', 'Norway', 'Denmark', 'Poland'];
    const APAC = ['China', 'Japan', 'South Korea', 'Korea', 'Singapore', 'Australia', 'India', 'Taiwan', 'Vietnam', 'Thailand'];
    const filteredSuppliers = !region ? _supplierRaw : _supplierRaw.filter(s => {
      if (region === 'amer') return AMER.includes(s.country);
      if (region === 'emea') return EMEA.includes(s.country);
      if (region === 'apac') return APAC.includes(s.country);
      return true;
    });
    const tbody = document.querySelector('#ord-supplier-table tbody');
    if (tbody) {
      if (!filteredSuppliers.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text-muted)">No suppliers for selected region</td></tr>`;
      } else {
        const saved = _supplierRaw;
        _supplierRaw = [];
        renderOrdSupplierTable(filteredSuppliers);
        _supplierRaw = saved;
      }
    }
  }
}

function clearFilters() {
  document.querySelectorAll('.filter-select').forEach(s => { s.value = ''; });
  applyFilters();
}

// ── Agent Actions ─────────────────────────────────────────────────────────────
const AGENT_ACTIONS = {
  ibp: [
    {
      sys: 'ERP',
      title: 'Publish the May Consensus Plan to Integrated Business Planning',
      desc: 'Push the agreed consensus plan figures from Databricks to your ERP IBP module, updating the statistical forecast baseline and triggering the supply planning run across all BUs — so MRP reflects the latest consensus without manual re-entry.',
      result: 'Consensus plan published · ERP IBP updated · Supply planning run triggered · Transaction PORDCR01-0000000051482910 confirmed · 18-month horizon loaded for 5 BUs',
    },
    {
      sys: 'Teams',
      title: 'Post the S&OP Risk Summary to the Steering Committee Channel',
      desc: 'Send an executive summary of the 5 open risk items, their financial exposure ($12.7M combined), and the recommended mitigations to the #sop-steering-committee channel in Teams — so leadership has the brief before the May 14th sign-off.',
      result: 'Risk summary posted to #sop-steering-committee · 5 risks · $12.7M total exposure · EMEA shortfall flagged HIGH · 4 leadership members notified · Posted 14:02',
    },
    {
      sys: 'ERP',
      title: 'Create a Financial Variance Notification for the EMEA Capacity Gap',
      desc: 'Raise a formal variance notification in your ERP against the EMEA BU plan, documenting the $4.2M capacity shortfall and attaching the Databricks-generated root cause analysis — creating the audit trail for the S&OP record.',
      result: 'Variance notification created · Document 900047821 · EMEA BU · $4.2M variance · Transaction FINSTA01-0000000051482987 confirmed · Attached to S&OP record 20250507',
    },
  ],
  inventory: [
    {
      sys: 'ERP',
      title: 'Create Replenishment Purchase Orders for Chicago DC Stockout SKUs',
      desc: 'Raise emergency purchase orders in your ERP Materials Management for FG-55102 (Hydraulic Pump Unit) and FG-91033 (Drive Belt XL) — the two critical stockout items in Chicago DC — with expedited lead time and preferred supplier pre-selected.',
      result: 'PO 4500892147 created for FG-55102 · 400 units · Apex Industrial · Expedited · Transaction ORDERS05-0000000051483001 confirmed\nPO 4500892148 created for FG-91033 · 600 units · Allied Materials · Standard · Transaction ORDERS05-0000000051483002 confirmed',
    },
    {
      sys: 'ERP',
      title: 'Post Inventory Transfer from Chicago to Rotterdam for FG-78421',
      desc: 'Issue a warehouse transfer order in your ERP Warehouse Management to move 200 units of FG-78421 (Premium Sprocket Assembly) from Chicago DC to Rotterdam DC — relieving Rotterdam\'s 91% utilization and redeploying $56K of excess stock.',
      result: 'Transfer Order 0000023841 posted · 200 units FG-78421 · Chicago ORD → Rotterdam RTM · Transaction WMMBXY-0000000051483050 confirmed · Rotterdam utilization reduced to 87%',
    },
    {
      sys: 'Teams',
      title: 'Alert the Logistics Team to the Rotterdam Capacity Risk',
      desc: 'Post a warehouse utilization alert to the #logistics-ops channel covering Rotterdam DC at 91% — including the 3 SKUs driving the overfill and the proposed lateral transfer plan — so the team can action it before the next inbound shipment arrives.',
      result: 'Alert posted to #logistics-ops · Rotterdam DC 91% utilization · 3 SKUs flagged · Lateral transfer plan attached · Logistics Manager K. van der Berg notified · Posted 14:07',
    },
  ],
  demand: [
    {
      sys: 'ERP',
      title: 'Push the Updated Statistical Forecast to ERP Demand Planning',
      desc: 'Upload the Databricks ML forecast for all 6,248 SKUs to your ERP demand planning module, replacing the legacy statistical forecast with the improved model output — reducing MAPE from the 14% baseline to the 9.1% achieved in Databricks.',
      result: 'Forecast upload complete · 6,248 SKUs · ERP Demand Plan updated · Transaction SUPFAL01-0000000051484100 confirmed · MAPE baseline adjusted to 9.1%',
    },
    {
      sys: 'ERP',
      title: 'Trigger a Demand Review Workflow for High-Error SKUs',
      desc: 'Create demand review tasks in your ERP for the top 5 high-error SKUs, assigning them to the responsible demand planners with the Databricks-generated error analysis attached — so root causes are investigated before the next consensus cycle.',
      result: '5 demand review tasks created · FG-55102 assigned to T. Reyes · FG-78421 assigned to M. Chen · Transaction HRMD_A07-0000000051484201 confirmed · Due date: May 10',
    },
    {
      sys: 'Teams',
      title: 'Notify the Commercial Team of the Systematic Under-Forecast Bias',
      desc: 'Post an analysis of the -2.3% under-forecast bias on Finished Goods to the #commercial-planning channel, explaining the link to the FG-55102 stockout and requesting input from the sales team on whether pipeline data should be added to the model.',
      result: 'Bias analysis posted to #commercial-planning · -2.3% FG under-forecast identified · Link to FG-55102 stockout highlighted · Sales data request raised · VP Commercial J. Walsh notified',
    },
  ],
  orders: [
    {
      sys: 'ERP',
      title: 'Auto-Create Purchase Orders for the 18 Pacific Components Exceptions',
      desc: 'Apply the renewed contract pricing to the 18 Pacific Components price discrepancy exceptions and create confirmed purchase orders in your ERP — converting $143K of held orders to confirmed POs without manual planner intervention.',
      result: '18 POs confirmed · Pacific Components · $143K released · Contract 4600082941 applied · Transaction ORDERS05 batch 0000000051485001–51485018 confirmed · Automation rate +2.1%',
    },
    {
      sys: 'ERP',
      title: 'Update Advance Shipment Notifications for Q2 Open Deliveries',
      desc: 'Refresh ASN records in your ERP for all Q2 open deliveries where supplier OTD is below 88% — flagging late shipments and triggering the exception workflow so procurement can expedite before delivery dates are missed.',
      result: 'ASN refresh complete · 31 deliveries updated · 7 late flags raised · Transaction DESADV batch 0000000051485101–51485131 confirmed · Expedite workflow triggered for 7 orders',
    },
    {
      sys: 'Teams',
      title: 'Escalate High-Priority Order Exceptions to the Procurement Team',
      desc: 'Post a ranked exception report to the #procurement-ops channel covering the 32 high-priority exceptions — price discrepancies, missing references, and unmatched invoices — with the root cause and recommended action for each.',
      result: 'Exception report posted to #procurement-ops · 32 high-priority items · $292K held · Root causes attached · Procurement Lead D. Okafor acknowledged · Posted 14:14',
    },
  ],
  ai: [
    {
      sys: 'ERP',
      title: 'Log the AI-Generated Supply Chain Findings to ERP',
      desc: 'Append a timestamped briefing to the active supply chain review workflow in your ERP, capturing the AI-generated recommendations from this session — creating a permanent record linking the AI analysis to the resulting business decisions.',
      result: 'AI findings logged · Workflow 800094821 · 1,024 characters · Transaction HRMD_A07-0000000051486200 confirmed · Linked to S&OP cycle 20250507',
    },
    {
      sys: 'Teams',
      title: 'Post the AI Session Summary to the Supply Chain Leadership Channel',
      desc: 'Share a concise summary of today\'s AI-identified insights — top risks, recommended actions, and financial quantification — to the #supply-chain-leadership channel so the leadership team can review and prioritize before the next steering meeting.',
      result: 'AI session summary posted to #supply-chain-leadership · 4 insights · $17.3M total risk identified · 3 recommended actions · 5 leadership members notified · Posted 14:18',
    },
    {
      sys: 'Email',
      title: 'Email the AI Supply Chain Summary to the CFO and COO',
      desc: 'Send a concise briefing to the CFO and COO distribution list summarizing the AI-identified supply chain risks, financial exposures, and recommended escalations for this week — so decisions can be made before the Friday leadership review.',
      result: 'Email sent · "Supply Chain AI Brief — Week 19" · CFO P. Lawson, COO M. Torres · 4 key findings · $17.3M exposure · 3 actions recommended · Sent 14:19',
    },
  ],
};

// ── Genie chat panel ─────────────────────────────────────────────────────────
let _geniePanelOpen = false;
function toggleGeniePanel() { _geniePanelOpen ? closeGeniePanel() : openGeniePanel(); }
function openGeniePanel() {
  _geniePanelOpen = true;
  document.getElementById('genie-panel-overlay').classList.add('open');
  document.getElementById('genie-chat-panel').classList.add('open');
}
function closeGeniePanel() {
  _geniePanelOpen = false;
  document.getElementById('genie-panel-overlay').classList.remove('open');
  document.getElementById('genie-chat-panel').classList.remove('open');
}

function openAgentPanel() {
  document.getElementById('agent-overlay').classList.remove('hidden');
  document.getElementById('agent-panel').classList.remove('hidden');
  renderAgentPanel(_activeTab);
}
function closeAgentPanel() {
  document.getElementById('agent-overlay').classList.add('hidden');
  document.getElementById('agent-panel').classList.add('hidden');
}

function renderAgentPanel(tab) {
  const badge = document.getElementById('agent-tab-badge');
  if (badge) badge.textContent = TAB_LABELS[tab] || tab;

  const actions = AGENT_ACTIONS[tab] || AGENT_ACTIONS.ibp;

  const list = document.getElementById('agent-actions-list');
  if (!list) return;
  list.innerHTML = actions.map((a, i) => {
    const sysClass = a.sys === 'ERP' ? 'badge-sap' : a.sys === 'Teams' ? 'badge-teams' : 'badge-email';
    return `
      <div class="agent-action-card" id="action-card-${tab}-${i}">
        <div class="agent-action-header-row">
          <span class="agent-sys-badge ${sysClass}">${esc(a.sys)}</span>
          <div class="agent-action-title">${esc(a.title)}</div>
        </div>
        <div class="agent-action-desc">${esc(a.desc)}</div>
        <button class="agent-approve-btn" onclick="runAgentAction('${tab}',${i})">Approve &amp; Execute</button>
      </div>`;
  }).join('');
}

function runAgentAction(tab, idx) {
  const actions = AGENT_ACTIONS[tab] || AGENT_ACTIONS.ibp;
  const a = actions[idx];
  if (!a) return;

  const card = document.getElementById(`action-card-${tab}-${idx}`);
  if (!card) return;

  const btn = card.querySelector('.agent-approve-btn');
  if (btn) btn.remove();

  const running = document.createElement('div');
  running.className = 'agent-running';
  running.innerHTML = `<span class="spinner sm"></span><span>Executing — connecting to ${a.sys}…</span>`;
  card.appendChild(running);

  setTimeout(() => {
    running.remove();
    const result = document.createElement('div');
    result.className = 'agent-result';
    result.textContent = a.result;
    card.appendChild(result);
  }, 2200 + Math.random() * 600);
}

// ── AI Chat ───────────────────────────────────────────────────────────────────
function setAiQ(btn) {
  const inp = document.getElementById('ai-input');
  if (inp) { inp.value = btn.textContent; inp.focus(); }
}

async function submitAi() {
  const inp      = document.getElementById('ai-input');
  const question = inp ? inp.value.trim() : '';
  if (!question || _aiActive) return;
  _aiActive = true;

  const btn = document.getElementById('ai-btn');
  if (btn) btn.disabled = true;

  const starters = document.getElementById('ai-starters');
  if (starters) starters.classList.add('hidden');
  const thread = document.getElementById('ai-thread');
  if (thread) thread.classList.remove('hidden');

  appendAiMsg('user', question);
  if (inp) inp.value = '';

  const loading = document.getElementById('ai-loading');
  if (loading) { loading.classList.remove('hidden'); loading.style.display = 'flex'; }

  try {
    const [res] = await Promise.all([
      fetch('/supply-chain/api/ai-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      }),
      new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 2000)),
    ]);
    const data = await res.json();
    if (loading) { loading.classList.add('hidden'); loading.style.display = 'none'; }

    const isGenie = data.sources && data.sources.includes('genie');
    const source = isGenie
      ? '✅ Powered by Databricks AI'
      : (data.sources ? `Sources: ${data.sources.join(', ')}` : '✅ Powered by Databricks');
    appendAiMsg('ai', data.answer, source, data.follow_ups || []);
  } catch (e) {
    if (loading) { loading.classList.add('hidden'); loading.style.display = 'none'; }
    appendAiMsg('ai', 'Network error — please try again.');
  }

  _aiActive = false;
  if (btn) btn.disabled = false;

  const chatBody = document.querySelector('.ai-chat-body');
  if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
}

async function diagnoseGenie() {
  const box = document.getElementById('genie-diag');
  if (!box) return;
  box.classList.remove('hidden');
  box.textContent = 'Running Genie diagnostics…';
  try {
    const res  = await fetch('/supply-chain/api/debug/genie');
    const data = await res.json();
    const lines = [];
    lines.push(`Genie Space ID  : ${data.genie_space_id || '(not set)'}`);
    lines.push(`Host set        : ${data.host_set}`);
    lines.push(`Host            : ${data.host || '(unknown)'}`);
    lines.push(`DATABRICKS_TOKEN: ${data.token_set}`);
    lines.push(`CLIENT_ID set   : ${data.client_id_set}`);
    lines.push(`CLIENT_SECRET   : ${data.client_secret_set}`);
    lines.push('');
    lines.push(`Start status   : ${data.start_status ?? '—'}`);
    if (data.start_status !== 200) {
      lines.push(`Start error    : ${typeof data.start_body === 'string' ? data.start_body : JSON.stringify(data.start_body, null, 2)}`);
    } else {
      lines.push(`Conv/Msg IDs   : ${data.start_body?.conversation_id} / ${data.start_body?.message_id}`);
      lines.push(`Poll status    : ${data.poll_status ?? '—'}`);
      const pb = data.poll_body;
      if (pb) {
        lines.push(`Genie status   : ${pb.status ?? '—'}`);
        if (pb.status === 'FAILED') lines.push(`Genie error    : ${JSON.stringify(pb.error ?? pb)}`);
      }
      lines.push('');
      lines.push(`Answer         : ${data.answer ? data.answer.slice(0, 300) : '(empty — check Genie space data access)'}`);
    }
    if (data.error) lines.push(`\nException      : ${data.error}`);
    box.textContent = lines.join('\n');
  } catch (e) {
    box.textContent = `Fetch error: ${e.message}`;
  }
}

function appendAiMsg(role, content, source, followUps) {
  const thread = document.getElementById('ai-thread');
  if (!thread) return;

  const div = document.createElement('div');
  div.className = `ai-msg ai-msg-${role}`;

  const av = document.createElement('div');
  av.className = 'ai-avatar';
  if (role === 'ai') {
    av.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><path d="M12 2C12 7.8 7.8 12 2 12C7.8 12 12 16.2 12 22C12 16.2 16.2 12 22 12C16.2 12 12 7.8 12 2Z"/></svg>`;
  } else {
    av.textContent = 'ME';
  }

  const wrap   = document.createElement('div');
  const bubble = document.createElement('div');
  bubble.className = 'ai-bubble';
  if (role === 'ai' && typeof marked !== 'undefined') {
    const raw = marked.parse(content);
    bubble.innerHTML = (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(raw) : raw;
  } else {
    bubble.textContent = content;
  }
  wrap.appendChild(bubble);

  if (role === 'ai' && followUps && followUps.length) {
    const pills = document.createElement('div');
    pills.className = 'fup-pills';
    followUps.forEach(fu => {
      const pill = document.createElement('button');
      pill.className = 'fup-pill';
      pill.textContent = fu;
      pill.onclick = () => { document.getElementById('ai-input').value = fu; submitAi(); };
      pills.appendChild(pill);
    });
    wrap.appendChild(pills);
  }

  div.appendChild(av);
  div.appendChild(wrap);
  thread.appendChild(div);
  return wrap;
}

function appendActionPanel(wrapEl, actions) {
  const target = wrapEl.querySelector('.sc-action-col') || wrapEl;

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
    card.id = `action-card-${a.id}`;

    const impact = a.impact_usd > 0
      ? `$${(a.impact_usd / 1000).toFixed(0)}K impact`
      : 'Process improvement';

    card.innerHTML = `
      <div class="action-priority-dot ${a.priority}"></div>
      <div class="action-card-body">
        <div class="action-card-title">${a.label}</div>
        <div class="action-card-desc">${a.description}</div>
        <div class="action-card-meta">
          <span class="action-impact">${impact}</span>
          <span>·</span>
          <span>${a.owner}</span>
          <span>·</span>
          <span>${a.entity_name}</span>
        </div>
        <div class="action-btns">
          <button class="action-approve-btn" onclick="executeAction('${a.id}','approved',this)">Take Action</button>
          <button class="action-dismiss-btn" onclick="executeAction('${a.id}','dismissed',this)">Dismiss</button>
        </div>
      </div>`;
    cards.appendChild(card);
  });

  panel.appendChild(cards);
  target.appendChild(panel);

  const chatBody = document.querySelector('.ai-chat-body');
  if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
}

async function executeAction(actionId, outcome, btn) {
  try {
    await fetch('/supply-chain/api/actions/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: actionId, outcome }),
    });
    const card = document.getElementById(`action-card-${actionId}`);
    if (card) {
      const btns = card.querySelector('.action-btns');
      if (btns) {
        btns.innerHTML = outcome === 'approved'
          ? `<div class="action-done-badge"><svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M20 6L9 17l-5-5"/><path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg> Action taken</div>`
          : `<div class="action-done-badge" style="color:var(--text-muted)">Dismissed</div>`;
      }
    }
  } catch (e) { /* silent */ }
}

// ── Interactive ML Features ────────────────────────────────────────────────

function _scMlRunnerStart(btnId, thinkingId, steps, stepId, doneCallback) {
  const btn = document.getElementById(btnId);
  const thinking = document.getElementById(thinkingId);
  const stepEl = document.getElementById(stepId);
  if (!btn || !thinking) return;
  btn.disabled = true;
  thinking.style.display = 'flex';
  let i = 0;
  const iv = setInterval(() => { i++; if (i < steps.length && stepEl) stepEl.textContent = steps[i]; }, 900);
  setTimeout(() => {
    clearInterval(iv); thinking.style.display = 'none'; btn.disabled = false; doneCallback();
  }, steps.length * 900 + 500);
}

function _scRenderFeatureBars(containerId, features) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.classList.add('visible');
  el.innerHTML = `<div class="feature-importance-title">Model Feature Importance</div>` +
    features.map(f => `
      <div class="feature-row">
        <div class="feature-label">${f.label}</div>
        <div class="feature-bar-wrap"><div class="feature-bar" id="scfb-${f.id}" style="background:${f.color || '#1B6FEB'};"></div></div>
        <div class="feature-pct">${f.pct}%</div>
      </div>`).join('');
  requestAnimationFrame(() => {
    features.forEach(f => {
      const bar = document.getElementById(`scfb-${f.id}`);
      if (bar) bar.style.width = f.pct + '%';
    });
  });
}

// ── IBP Scenario Switcher ──────────────────────────────────────────────────
const IBP_SCENARIOS = {
  base:     { util:'82%', gap:'$4.2M',  risk:'Medium', ss:'+$1.8M',  riskColor:'#f59e0b' },
  upside:   { util:'96%', gap:'$12.7M', risk:'High',   ss:'+$6.4M',  riskColor:'#ef4444' },
  downside: { util:'61%', gap:'−$8.1M', risk:'Low',    ss:'−$3.2M',  riskColor:'#10b981' },
};

function switchIbpScenario(scenario, btn) {
  document.querySelectorAll('.scenario-toggle-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const s = IBP_SCENARIOS[scenario] || IBP_SCENARIOS.base;
  const set = (id, val, color) => {
    const el = document.getElementById(id);
    if (el) { el.textContent = val; if (color) el.style.color = color; }
  };
  set('ibp-scen-util', s.util);
  set('ibp-scen-gap', s.gap, scenario === 'downside' ? '#10b981' : '#ef4444');
  set('ibp-scen-risk', s.risk, s.riskColor);
  set('ibp-scen-ss', s.ss, scenario === 'downside' ? '#10b981' : '#ef4444');
  // Animate IBP chart if loaded
  if (_ibpPlanChart && _ibpPlanChart.data) {
    const multiplier = scenario === 'upside' ? 1.12 : scenario === 'downside' ? 0.85 : 1.0;
    const base = [78,82,85,88,91,84,87,90,93,96,89,92,88,91,94,87,90,95,98];
    _ibpPlanChart.data.datasets[0].data = base.map(v => +(v * multiplier).toFixed(1));
    _ibpPlanChart.update('active');
  }
}

// ── Demand Scenario Planner ────────────────────────────────────────────────
let _demScenTimer = null;

function updateDemandScenario() {
  const vol = parseInt(document.getElementById('dem-vol-slider')?.value || 0);
  const promo = parseInt(document.getElementById('dem-promo-slider')?.value || 0);
  const season = parseInt(document.getElementById('dem-season-slider')?.value || 0);

  const volEl = document.getElementById('dem-vol-val');
  const promoEl = document.getElementById('dem-promo-val');
  const seasonEl = document.getElementById('dem-season-val');
  if (volEl)    volEl.textContent   = (vol >= 0 ? '+' : '') + vol + '%';
  if (promoEl)  promoEl.textContent = '+' + promo + '%';
  if (seasonEl) seasonEl.textContent = (season >= 0 ? '+' : '') + season + '%';

  clearTimeout(_demScenTimer);
  _demScenTimer = setTimeout(() => runDemandScenario(true), 600);
}

function runDemandScenario(auto = false) {
  const vol = parseInt(document.getElementById('dem-vol-slider')?.value || 0);
  const promo = parseInt(document.getElementById('dem-promo-slider')?.value || 0);
  const season = parseInt(document.getElementById('dem-season-slider')?.value || 0);
  const total = vol + promo * 0.6 + season * 0.4;

  if (auto) {
    // Instant update — no animation needed for slider drags
    const baseMape = 8.4;
    const mape = Math.max(5.1, baseMape + Math.abs(total) * 0.12).toFixed(1);
    const ssChange = total !== 0 ? (total > 0 ? `+$${(total * 0.18).toFixed(1)}M` : `−$${Math.abs(total * 0.18).toFixed(1)}M`) : '—';
    const fillImpact = total > 0 ? `+${(total * 0.08).toFixed(1)}%` : total < 0 ? `−${Math.abs(total * 0.08).toFixed(1)}%` : '—';
    const bias = (total * 0.05 - 2.1).toFixed(1);

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('dem-scen-mape', mape + '%');
    set('dem-scen-ss', ssChange);
    set('dem-scen-bias', (parseFloat(bias) >= 0 ? '+' : '') + bias + '%');
    set('dem-scen-fill', fillImpact);
    return;
  }

  const steps = [
    'Loading 12-month demand history from demand_gold…',
    'Applying volume, promotional, and seasonal adjustments…',
    'Running LSTM forecast model across 6,247 active SKUs…',
    'Computing MAPE, bias, and safety stock requirements…',
  ];
  _scMlRunnerStart('demand-scen-btn', 'demand-scen-thinking', steps, 'demand-scen-step', () => {
    updateDemandScenario(true);
    const resultsEl = document.getElementById('demand-scen-results');
    if (resultsEl) { resultsEl.classList.add('visible'); }
    const chips = `
      <div class="ml-action-chips" style="margin-top:12px;">
        <button class="ml-action-chip blue" onclick="this.textContent='✓ Applied';this.disabled=true;">Apply Scenario to S&OP</button>
        <button class="ml-action-chip green" onclick="this.textContent='✓ Exported';this.disabled=true;">Export Forecast to ERP</button>
        <button class="ml-action-chip amber" onclick="this.textContent='✓ Sent';this.disabled=true;">Alert Demand Planning Team</button>
      </div>`;
    const sumEl = document.getElementById('demand-scen-summary');
    if (sumEl) { const existing = sumEl.querySelector('.ml-action-chips'); if (!existing) sumEl.insertAdjacentHTML('beforeend', chips); }
  });
}

// ── Inventory Rebalance Optimizer ──────────────────────────────────────────
function runInventoryRebalance() {
  const dc = document.getElementById('inv-rebal-dc')?.value || 'all';
  const dcLabel = dc === 'all' ? 'all DCs' : dc + ' DC';
  const steps = [
    `Loading inventory positions for ${dcLabel} from inventory_gold…`,
    'Running network flow optimization model (min-cost formulation)…',
    'Evaluating 847 potential transfer routes by cost × service impact…',
    'Ranking recommendations by DOS improvement and freight cost…',
  ];
  _scMlRunnerStart('inv-rebal-btn', 'inv-rebal-thinking', steps, 'inv-rebal-step', () => {
    const transfers = dc === 'all' ? [
      { from:'Chicago DC', to:'Newark DC', sku:'FG-55102', qty:240, dosGain:'+8 days', cost:'$1,840' },
      { from:'Phoenix DC', to:'Atlanta DC', sku:'FG-22301', qty:180, dosGain:'+6 days', cost:'$2,210' },
      { from:'Dallas DC', to:'Seattle DC', sku:'RM-77043', qty:320, dosGain:'+11 days', cost:'$3,180' },
      { from:'Newark DC', to:'Chicago DC', sku:'WIP-11220', qty:90, dosGain:'+5 days', cost:'$890' },
    ] : [
      { from: dc + ' DC', to:'Nearest DC', sku:'FG-55102', qty:180, dosGain:'+7 days', cost:'$1,640' },
      { from: dc + ' DC', to:'Regional Hub', sku:'FG-22301', qty:120, dosGain:'+5 days', cost:'$1,420' },
    ];
    const totalFreight = transfers.reduce((s,t) => s + parseInt(t.cost.replace(/[^0-9]/g,'')), 0);
    const el = document.getElementById('inv-rebal-results');
    if (!el) return;
    el.classList.add('visible');
    el.innerHTML = `
      <div class="ml-result-summary">
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Transfers Recommended</div><div class="ml-result-kpi-val">${transfers.length}</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Total Freight Cost</div><div class="ml-result-kpi-val">$${(totalFreight/1000).toFixed(1)}K</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Stockouts Resolved</div><div class="ml-result-kpi-val" style="color:#10b981">${transfers.length}</div></div>
      </div>
      <div style="overflow-x:auto;margin-top:8px;">
        <table style="width:100%;font-size:12px;border-collapse:collapse;">
          <thead><tr style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:.06em;">
            <th style="text-align:left;padding:4px 8px;">From</th><th style="text-align:left;padding:4px 8px;">To</th>
            <th style="text-align:left;padding:4px 8px;">SKU</th><th style="text-align:right;padding:4px 8px;">Qty</th>
            <th style="text-align:right;padding:4px 8px;">DOS Gain</th><th style="text-align:right;padding:4px 8px;">Freight</th>
            <th style="padding:4px 8px;"></th>
          </tr></thead>
          <tbody>${transfers.map(t => `<tr style="border-top:1px solid rgba(255,255,255,0.05);">
            <td style="padding:5px 8px;color:#c8c8c8;">${t.from}</td><td style="padding:5px 8px;color:#c8c8c8;">${t.to}</td>
            <td style="padding:5px 8px;font-family:monospace;color:#818cf8;">${t.sku}</td>
            <td style="padding:5px 8px;text-align:right;">${t.qty.toLocaleString()}</td>
            <td style="padding:5px 8px;text-align:right;color:#10b981;font-weight:700;">${t.dosGain}</td>
            <td style="padding:5px 8px;text-align:right;color:#9ca3af;">${t.cost}</td>
            <td style="padding:5px 8px;"><button style="background:rgba(27,111,235,0.12);border:1px solid rgba(27,111,235,0.3);border-radius:5px;color:#1B6FEB;font-size:11px;padding:3px 9px;cursor:pointer;font-family:inherit;" onclick="this.textContent='✓ Approved';this.disabled=true;">Approve</button></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="ml-action-chips" style="margin-top:12px;">
        <button class="ml-action-chip blue" onclick="this.textContent='✓ All Approved';this.disabled=true;">Approve All Transfers</button>
        <button class="ml-action-chip green" onclick="this.textContent='✓ Submitted';this.disabled=true;">Submit to WMS</button>
      </div>`;
  });
}

// ── Order Risk Scorer ──────────────────────────────────────────────────────
function runOrderRiskScore() {
  const filter = document.getElementById('ord-risk-filter')?.value || 'all';
  const steps = [
    'Fetching open PO register from order_management_gold…',
    'Loading supplier risk profiles and historical OTD data…',
    'Running XGBoost risk classifier on 1,247 open orders…',
    'Ranking orders by combined risk score…',
  ];
  _scMlRunnerStart('ord-risk-btn', 'ord-risk-thinking', steps, 'ord-risk-step', () => {
    const orders = [
      { id:'PO-4821', supplier:'Pacific Components', risk:'High', score:87, value:'$142K', reason:'OTD < 60%, single-source, lead time +18 days', color:'#ef4444' },
      { id:'PO-4790', supplier:'Midwest Metals', risk:'High', score:79, value:'$89K', reason:'Price variance +22% vs contract, quality hold history', color:'#ef4444' },
      { id:'PO-4812', supplier:'Atlantic Plastics', risk:'Medium', score:61, value:'$56K', reason:'Capacity utilization 94%, extended lead time forecast', color:'#f59e0b' },
      { id:'PO-4844', supplier:'Delta Electronics', risk:'Medium', score:58, value:'$34K', reason:'Port congestion on inbound route, +7 day delay likely', color:'#f59e0b' },
      { id:'PO-4833', supplier:'CoreSupply Inc.', risk:'Low', score:22, value:'$78K', reason:'Preferred supplier, 98% OTD, within contract price band', color:'#10b981' },
    ].filter(o => filter === 'all' || (filter === 'high' && o.risk === 'High') || (filter === 'late' && o.score > 60) || (filter === 'exception' && o.score > 75));
    const highRisk = orders.filter(o => o.risk === 'High').length;
    const valueAtRisk = orders.filter(o => o.risk !== 'Low').reduce((s,o) => s + parseInt(o.value.replace(/[^0-9]/g,'')), 0);
    const el = document.getElementById('ord-risk-results');
    if (!el) return;
    el.classList.add('visible');
    el.innerHTML = `
      <div class="ml-result-summary">
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Orders Scored</div><div class="ml-result-kpi-val">${orders.length}</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">High Risk Orders</div><div class="ml-result-kpi-val" style="color:#ef4444">${highRisk}</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Value at Risk</div><div class="ml-result-kpi-val" style="color:#f59e0b">$${(valueAtRisk/1000).toFixed(0)}K</div></div>
      </div>
      <div style="overflow-x:auto;margin-top:8px;">
        <table style="width:100%;font-size:12px;border-collapse:collapse;">
          <thead><tr style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:.06em;">
            <th style="text-align:left;padding:4px 8px;">PO</th><th style="text-align:left;padding:4px 8px;">Supplier</th>
            <th style="text-align:center;padding:4px 8px;">Risk</th><th style="text-align:right;padding:4px 8px;">Score</th>
            <th style="text-align:right;padding:4px 8px;">Value</th><th style="text-align:left;padding:4px 8px;">Risk Signal</th>
            <th style="padding:4px 8px;"></th>
          </tr></thead>
          <tbody>${orders.map(o => `<tr style="border-top:1px solid rgba(255,255,255,0.05);">
            <td style="padding:5px 8px;font-family:monospace;font-size:11px;color:#818cf8;">${o.id}</td>
            <td style="padding:5px 8px;font-weight:600;color:#f0f0f0;">${o.supplier}</td>
            <td style="padding:5px 8px;text-align:center;"><span style="background:${o.color}22;color:${o.color};border:1px solid ${o.color}55;border-radius:4px;padding:2px 8px;font-size:10.5px;font-weight:700;">${o.risk}</span></td>
            <td style="padding:5px 8px;text-align:right;font-weight:700;color:${o.color};">${o.score}</td>
            <td style="padding:5px 8px;text-align:right;color:#c8c8c8;">${o.value}</td>
            <td style="padding:5px 8px;color:#9ca3af;font-size:11px;max-width:200px;">${o.reason}</td>
            <td style="padding:5px 8px;"><button style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:5px;color:#ef4444;font-size:11px;padding:3px 9px;cursor:pointer;font-family:inherit;${o.risk === 'Low' ? 'opacity:.4;' : ''}" onclick="this.textContent='✓ Escalated';this.disabled=true;" ${o.risk === 'Low' ? 'disabled' : ''}>Escalate</button></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="ml-action-chips" style="margin-top:12px;">
        <button class="ml-action-chip blue" onclick="this.textContent='✓ Notified';this.disabled=true;">Notify Procurement Team</button>
        <button class="ml-action-chip amber" onclick="this.textContent='✓ Triggered';this.disabled=true;">Trigger Supplier Review</button>
      </div>`;
  });
}
