/* ── Databricks Operational Excellence — App Logic ───────────────────── */

// ── State ─────────────────────────────────────────────────────────────────────
let allMachines       = [];
let allAlarms         = [];
let _mtbfRaw          = [];
let _paretoRaw        = [];   // raw downtime pareto for filter re-renders
let _qualityRaw       = null; // raw quality data for filter re-renders
let selectedMachineId = null;
let shiftConvId       = null;
let liveInterval      = null;

let machineChart   = null;
let paretoChart    = null;
let defectChart    = null;
let defectDonut    = null;
let pdmDetailChart = null;

// Calculator state (machine-based)
let calcHours     = 4;
let calcMachineId = 'BDY-SLD-01';

// ── Boot ──────────────────────────────────────────────────────────────────────
// ── Tutorial ──────────────────────────────────────────────────────────────────
function showTutorialIfNew() {
  if (!localStorage.getItem('mfg-tutorial-seen')) {
    document.getElementById('tut-overlay').classList.remove('hidden');
  }
}
function dismissTutorial() {
  localStorage.setItem('mfg-tutorial-seen', '1');
  document.getElementById('tut-overlay').classList.add('hidden');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') dismissTutorial(); });

document.addEventListener('DOMContentLoaded', () => {
  // Apply saved theme before any render
  const savedTheme = localStorage.getItem('mfg-theme');
  if (savedTheme === 'light') {
    document.body.classList.add('light');
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = '☀';
  }

  _tabStartTime = Date.now(); // start timer on initial tab (floor)
  loadStatic();
  startLivePolling();
  initCalculator();
  loadAppConfig();
  showTutorialIfNew();

  document.getElementById('shift-input').addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submitShift();
  });
});

async function loadAppConfig() {
  try {
    const d = await (await fetch('/manufacturing/api/config')).json();
    if (d.company_name) {
      const sub = document.querySelector('.header-title-sub');
      if (sub) sub.textContent = d.company_name + ' · Manufacturing';
      document.title = d.company_name + ' — Operational Excellence';
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
            // db-logo-mark wraps the SVG — replace the whole div
            const logoMark = document.querySelector('.db-logo-mark');
            if (logoMark) logoMark.replaceWith(img);
            else {
              const brand = document.querySelector('.header-brand');
              const brandSvg = brand ? brand.querySelector('svg') : null;
              if (brandSvg) brandSvg.replaceWith(img);
              else if (brand) brand.prepend(img);
            }
            const titleMain = document.querySelector('.header-title-main');
            if (titleMain) titleMain.textContent = 'Operational Excellence';
          };
          img.onerror = () => {};
          img.src = `https://cdn.brandfetch.io/domain/${results[0].domain}?c=1idGdcDDyuPmwhnhURl`;
        })
        .catch(() => {});
    }
  } catch (_) {}
}

function toggleTheme() {
  const isLight = document.body.classList.toggle('light');
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = isLight ? '☀' : '🌙';
  localStorage.setItem('mfg-theme', isLight ? 'light' : 'dark');
  // Redraw charts to pick up new theme colors
  loadStatic();
  if (allMachines.length) renderMachineGrids(allMachines);
}

async function loadStatic() {
  const [alarms, downtime, quality] = await Promise.all([
    fetch('/manufacturing/api/alarms').then(r => r.json()),
    fetch('/manufacturing/api/downtime').then(r => r.json()),
    fetch('/manufacturing/api/quality').then(r => r.json()),
  ]);
  allAlarms   = alarms;
  _mtbfRaw    = downtime.mtbf;
  _paretoRaw  = downtime.pareto;
  _qualityRaw = quality;

  renderAlarmList(alarms);
  _renderSidebarAlarms(alarms);
  applyFilters();
}

function startLivePolling() {
  fetchLive();
  liveInterval = setInterval(fetchLive, 30000);
}

async function fetchLive() {
  const data = await fetch('/manufacturing/api/live').then(r => r.json()).catch(() => null);
  if (!data) return;

  // Dismiss loading screen on first successful data load
  const ls = document.getElementById('mfg-load-screen');
  if (ls && !ls.classList.contains('gone')) {
    ls.classList.add('fade');
    setTimeout(() => ls.classList.add('gone'), 560);
  }

  allMachines = data.machines;
  const kpi   = data.kpi;

  updateHeader(kpi);
  renderMachineGrids(data.machines);
  updateOeeTab(kpi, data.machines);
  updateFloorTicker(kpi, data.machines);
  updateFloorSidebar(kpi, data.machines);
}

// ── Floor Ticker ──────────────────────────────────────────────────────────────
function updateFloorTicker(kpi, machines) {
  const lineAvg = (line) => {
    const ms = machines.filter(m => m.line === line && m.state === 'running' && m.oee > 0);
    return ms.length ? +(ms.reduce((s, m) => s + m.oee, 0) / ms.length).toFixed(1) : null;
  };
  const la = lineAvg('A'), lb = lineAvg('B'), lc = lineAvg('C');
  const oeeColor = kpi.plant_oee >= 88 ? 'green' : kpi.plant_oee >= 80 ? 'amber' : 'red';

  function setTick(id, val, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = val;
    el.className = 'ftick-val' + (cls ? ' ' + cls : '');
  }
  setTick('ftick-oee',     kpi.plant_oee + '%', oeeColor);
  setTick('ftick-running', kpi.running + '/' + kpi.total_machines, 'green');
  setTick('ftick-faults',  kpi.fault, kpi.fault > 0 ? 'red' : 'green');
  setTick('ftick-alarms',  kpi.critical_alarms, kpi.critical_alarms > 0 ? 'red' : 'green');
  setTick('ftick-linea',   la != null ? la + '%' : 'OFFLINE', la != null ? (la >= 85 ? 'green' : la >= 75 ? 'amber' : 'red') : 'red');
  setTick('ftick-lineb',   lb != null ? lb + '%' : 'OFFLINE', lb != null ? (lb >= 85 ? 'green' : lb >= 75 ? 'amber' : 'red') : 'red');
  setTick('ftick-linec',   lc != null ? lc + '%' : 'OFFLINE', lc != null ? (lc >= 85 ? 'green' : lc >= 75 ? 'amber' : 'red') : 'red');
  setTick('ftick-vba',     `${kpi.vba_shift_units}/${kpi.vba_target_shift}`, kpi.vba_shift_units >= kpi.vba_target_shift * 0.9 ? 'green' : 'amber');
  setTick('ftick-pbu',     `${kpi.pbu_shift_units}/${kpi.pbu_target_shift}`, kpi.pbu_shift_units >= kpi.pbu_target_shift * 0.9 ? 'green' : 'amber');
  setTick('ftick-ptm',     `${kpi.ptm_shift_units}/${kpi.ptm_target_shift}`, kpi.ptm_shift_units >= kpi.ptm_target_shift * 0.9 ? 'green' : 'amber');
  setTick('ftick-shift',   Math.floor(kpi.shift_elapsed_min || 0) + ' MIN', null);

  // Duplicate inner content for seamless loop
  const inner = document.getElementById('floor-ticker-inner');
  if (inner && !inner.dataset.doubled) {
    inner.dataset.doubled = '1';
    inner.innerHTML += inner.innerHTML;
  }
}

// ── Floor Sidebar ─────────────────────────────────────────────────────────────
function updateFloorSidebar(kpi, machines) {
  const lineAvg = (line) => {
    const ms = machines.filter(m => m.line === line && m.state === 'running' && m.oee > 0);
    return ms.length ? +(ms.reduce((s, m) => s + m.oee, 0) / ms.length).toFixed(1) : 0;
  };
  const la = lineAvg('A'), lb = lineAvg('B'), lc = lineAvg('C');
  const oeeColor = kpi.plant_oee >= 88 ? 'green' : kpi.plant_oee >= 80 ? 'amber' : 'red';

  // Plant health KPIs
  const oeeEl = document.getElementById('fsb-oee');
  if (oeeEl) { oeeEl.textContent = kpi.plant_oee + '%'; oeeEl.className = 'fsb-kpi-val ' + oeeColor; }
  const runEl = document.getElementById('fsb-running');
  if (runEl) runEl.textContent = kpi.running + '/' + kpi.total_machines;
  const fltEl = document.getElementById('fsb-faults');
  if (fltEl) { fltEl.textContent = kpi.fault; fltEl.className = 'fsb-kpi-val ' + (kpi.fault > 0 ? 'red' : 'green'); }
  const idlEl = document.getElementById('fsb-idle');
  if (idlEl) idlEl.textContent = kpi.idle;

  // Line bars
  function setLineBar(labelId, barId, pct) {
    const lbl = document.getElementById(labelId);
    const bar = document.getElementById(barId);
    if (!lbl || !bar) return;
    lbl.textContent = pct > 0 ? pct + '%' : 'OFFLINE';
    lbl.style.color = pct >= 85 ? '#22c55e' : pct >= 75 ? '#f59e0b' : '#ef4444';
    bar.style.width = pct + '%';
    bar.style.background = pct >= 85 ? '#22c55e' : pct >= 75 ? '#f59e0b' : '#ef4444';
  }
  setLineBar('fsb-line-a', 'fsb-bar-a', la);
  setLineBar('fsb-line-b', 'fsb-bar-b', lb);
  setLineBar('fsb-line-c', 'fsb-bar-c', lc);

  // Shift output bars
  function setProdBar(barId, valId, actual, target) {
    const bar = document.getElementById(barId);
    const val = document.getElementById(valId);
    const pct = target > 0 ? Math.min(100, (actual / target) * 100) : 0;
    if (bar) { bar.style.width = pct + '%'; bar.style.background = pct >= 90 ? '#22c55e' : pct >= 70 ? '#3b82f6' : '#f59e0b'; }
    if (val) val.textContent = actual + ' / ' + target;
  }
  setProdBar('fsb-prod-vba', 'fsb-prod-vba-val', kpi.vba_shift_units, kpi.vba_target_shift);
  setProdBar('fsb-prod-pbu', 'fsb-prod-pbu-val', kpi.pbu_shift_units, kpi.pbu_target_shift);
  setProdBar('fsb-prod-ptm', 'fsb-prod-ptm-val', kpi.ptm_shift_units, kpi.ptm_target_shift);

  // Alarms
  if (allAlarms && allAlarms.length) _renderSidebarAlarms(allAlarms);
}

function _renderSidebarAlarms(alarms) {
  const container = document.getElementById('fsb-alarms');
  const badge     = document.getElementById('fsb-alarm-badge');
  if (!container) return;
  const top = alarms.slice(0, 5);
  if (badge) badge.textContent = alarms.length;
  container.innerHTML = top.map(a => {
    const dotCls = a.severity === 'CRITICAL' ? 'critical' : a.severity === 'HIGH' ? 'high' : 'medium';
    const ago = a.triggered_min_ago < 60 ? a.triggered_min_ago + 'm ago' : Math.floor(a.triggered_min_ago / 60) + 'h ago';
    return `<div class="fsb-alarm-row">
      <div class="fsb-alarm-dot ${dotCls}"></div>
      <div class="fsb-alarm-body">
        <div class="fsb-alarm-machine">${a.machine_id} · ${a.severity}</div>
        <div class="fsb-alarm-msg" title="${a.message}">${a.message}</div>
      </div>
      <div class="fsb-alarm-time">${ago}</div>
    </div>`;
  }).join('');
}

/** OEE traffic light class */
function oeeTrafficClass(pct, target = 88) {
  if (pct == null || Number.isNaN(pct)) return 'oee-na';
  if (pct >= target)     return 'oee-green';
  if (pct >= target - 8) return 'oee-yellow';
  return 'oee-red';
}

function lineAvgOeePct(machines, line) {
  const ms = machines.filter(m => m.line === line && m.state === 'running' && m.oee > 0);
  if (!ms.length) return null;
  return +(ms.reduce((s, m) => s + m.oee, 0) / ms.length).toFixed(1);
}

// ── Tab ───────────────────────────────────────────────────────────────────────
let _visionRan = false;
let _pdmRan    = false;
let _pdmData   = null;
let _pdmView   = 'card';

let _activeTab    = 'floor';
let _tabStartTime = null;
let _clickCount   = 0;
document.addEventListener('click', () => { _clickCount++; });

// ── Page time logging ─────────────────────────────────────────────────────────
async function _logPageTime(page, seconds) {
  if (seconds < 1) return;
  const clicks = _clickCount;
  _clickCount = 0;
  try {
    await fetch('/manufacturing/api/log-page-time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, seconds_spent: seconds, click_count: clicks }),
    });
  } catch (_) {}
}

function switchTab(tab) {
  // Log time on the tab we're leaving before switching
  if (_tabStartTime !== null && tab !== _activeTab) {
    _logPageTime(_activeTab, Math.floor((Date.now() - _tabStartTime) / 1000));
  }
  _tabStartTime = Date.now();

  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.remove('hidden');
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
  _activeTab = tab;
  const filterBar = document.getElementById('filter-bar');
  if (filterBar) filterBar.style.display = '';

  if (tab === 'quality' && !_visionRan) {
    _visionRan = true;
    setTimeout(runAllInspections, 600);
  }
  if (tab === 'maintenance' && !_pdmRan) {
    _pdmRan = true;
    setTimeout(loadPdmPredictions, 400);
  }
  // Re-render downtime chart when tab becomes visible (canvas was hidden during initial load)
  if (tab === 'downtime') {
    setTimeout(() => applyFilters(), 50);
  }

  // Refresh agent panel and info panel if open
  if (!document.getElementById('agent-panel').classList.contains('hidden')) renderAgentPanel(tab);
  if (!document.getElementById('info-overlay').classList.contains('hidden')) openInfoPanel(tab);
}

// ── Header ────────────────────────────────────────────────────────────────────
function updateHeader(kpi) {
  const oeeEl = document.getElementById('hdr-oee');
  const tgt   = kpi.oee_target != null ? kpi.oee_target : 88;
  oeeEl.textContent = kpi.plant_oee + '%';
  oeeEl.className   = 'hdr-kpi-val ' + oeeTrafficClass(kpi.plant_oee, tgt);
  document.getElementById('hdr-running').textContent    = `${kpi.running}/${kpi.total_machines}`;
  document.getElementById('hdr-faults').textContent     = kpi.fault;
  const alarmEl = document.getElementById('hdr-alarm-count'); if (alarmEl) alarmEl.textContent = kpi.critical_alarms;
}

// ── Plant KPI Strip ───────────────────────────────────────────────────────────
// ── 2D Floor Map ───────────────────────────────────────────────────────────────
let _floorZoom = 0.72, _floorPanX = 0, _floorPanY = 0;
let _floorDragging = false, _floorDragSX, _floorDragSY, _floorDragPX, _floorDragPY;

function _applyFloorTransform() {
  const c = document.getElementById('fmap-canvas');
  if (c) c.style.transform = `translate(${_floorPanX}px, ${_floorPanY}px) scale(${_floorZoom})`;
}

function floorZoom(factor) {
  _floorZoom = Math.max(0.3, Math.min(2.5, _floorZoom * factor));
  _applyFloorTransform();
}

function floorZoomReset() {
  _floorZoom = 0.72; _floorPanX = 0; _floorPanY = 0;
  _applyFloorTransform();
}

function _initFloorMap() {
  const vp = document.getElementById('fmap-viewport');
  if (!vp || vp._floorInited) return;
  vp._floorInited = true;
  _applyFloorTransform();

  vp.addEventListener('wheel', e => {
    e.preventDefault();
    floorZoom(e.deltaY < 0 ? 1.1 : 0.91);
  }, { passive: false });

  vp.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    _floorDragging = true;
    _floorDragSX = e.clientX; _floorDragSY = e.clientY;
    _floorDragPX = _floorPanX; _floorDragPY = _floorPanY;
    vp.classList.add('dragging');
  });
  window.addEventListener('mousemove', e => {
    if (!_floorDragging) return;
    _floorPanX = _floorDragPX + (e.clientX - _floorDragSX);
    _floorPanY = _floorDragPY + (e.clientY - _floorDragSY);
    _applyFloorTransform();
  });
  window.addEventListener('mouseup', () => {
    _floorDragging = false;
    vp.classList.remove('dragging');
  });

  // Touch support
  let _t0;
  vp.addEventListener('touchstart', e => {
    if (e.touches.length === 1) {
      _t0 = { x: e.touches[0].clientX, y: e.touches[0].clientY, px: _floorPanX, py: _floorPanY };
    }
  }, { passive: true });
  vp.addEventListener('touchmove', e => {
    if (e.touches.length === 1 && _t0) {
      _floorPanX = _t0.px + (e.touches[0].clientX - _t0.x);
      _floorPanY = _t0.py + (e.touches[0].clientY - _t0.y);
      _applyFloorTransform();
    }
  }, { passive: true });
}

function renderMachineGrids(machines) {
  _initFloorMap();
  machines.forEach(m => {
    const node = document.getElementById(`fnode-${m.id}`);
    if (!node) return;

    const oeeDisplay = m.state === 'fault'       ? 'FAULT'
                     : m.state === 'maintenance'  ? 'PM'
                     : m.state === 'idle'         ? 'IDLE'
                     : (m.oee != null ? m.oee + '%' : '—');

    let oeeClass = '';
    if (m.state === 'running') oeeClass = ' ' + oeeTrafficClass(m.oee);
    node.className = `fnode ${m.state}${oeeClass}${selectedMachineId === m.id ? ' selected' : ''}${m.line === 'S' ? ' fnode-final' : ''}`;

    const alertMsg = m.fault_msg   ? `⚠ ${m.fault_code}: ${m.fault_msg.substring(0, 80)}`
                   : m.idle_reason ? `⏸ ${m.idle_reason.substring(0, 80)}`
                   : m.maintenance_type ? `🔧 ${m.maintenance_type.substring(0, 80)}` : '';

    node.innerHTML = `
      <div style="display:flex;align-items:center;gap:5px;width:100%;justify-content:center;">
        <div class="fnode-status-dot"></div>
        <div class="fnode-id">${m.id}</div>
      </div>
      <div class="fnode-name">${shortMachineName(m.name)}</div>
      <div class="fnode-oee">${oeeDisplay}</div>
      <div class="fnode-temp">${m.temp != null ? m.temp + '°C' : ''}</div>
      <div class="fnode-tip">
        <div class="fnode-tip-name">${m.name}</div>
        <div class="fnode-tip-row"><span>OEE</span><span class="fnode-tip-val">${m.state === 'running' ? m.oee + '%' : '—'}</span></div>
        <div class="fnode-tip-row"><span>Temperature</span><span class="fnode-tip-val">${m.temp != null ? m.temp + '°C' : '—'}</span></div>
        <div class="fnode-tip-row"><span>Cycle Time</span><span class="fnode-tip-val">${m.state === 'running' && m.cycle_time_sec ? m.cycle_time_sec + 's' : '—'}</span></div>
        <div class="fnode-tip-row"><span>Units (shift)</span><span class="fnode-tip-val">${m.units_this_shift > 0 ? m.units_this_shift.toLocaleString() : '—'}</span></div>
        ${alertMsg ? `<div class="fnode-tip-alert">${alertMsg}</div>` : ''}
        <div class="fnode-tip-click">Click for machine status →</div>
      </div>
    `;
    node.onclick = (e) => { e.stopPropagation(); showMachineStatus(m.id); };
  });

}

function renderFloorTrack(containerId, machines) {
  const el = document.getElementById(containerId);
  if (!el) return;

  machines.forEach(m => {
    let asset = el.querySelector(`[data-machine-id="${m.id}"]`);
    if (!asset) {
      asset = document.createElement('div');
      asset.setAttribute('data-machine-id', m.id);
      asset.addEventListener('click', () => showMachineStatus(m.id));
      el.appendChild(asset);
    }

    let oeeClass = '';
    if (m.state === 'running') oeeClass = ' ' + oeeTrafficClass(m.oee);

    asset.className = `floor-asset ${m.state}${oeeClass}${selectedMachineId === m.id ? ' selected' : ''}`;
    asset.innerHTML = buildFloorAssetHTML(m);
  });
}

function buildFloorAssetHTML(m) {
  const oeeDisplay = m.state === 'fault'       ? '—'
                   : m.state === 'maintenance'  ? 'PM'
                   : m.state === 'idle'         ? 'IDLE'
                   : (m.oee != null ? m.oee + '%' : '—');

  return `
    <div class="asset-body">
      <div class="asset-dot"></div>
      <div class="asset-oee">${oeeDisplay}</div>
      <div class="asset-id">${m.id}</div>
      <div class="asset-name">${shortMachineName(m.name)}</div>
    </div>
    ${buildAssetTooltip(m)}
  `;
}

function buildAssetTooltip(m) {
  const oeeStr   = m.state === 'running' ? `${m.oee}%` : '—';
  const tempStr  = m.temp != null ? `${m.temp}°C` : '—';
  const cycleStr = m.state === 'running' && m.cycle_time_sec ? `${m.cycle_time_sec}s` : '—';
  const unitStr  = m.units_this_shift > 0 ? m.units_this_shift.toLocaleString() : '—';

  let alertBlock = '';
  if (m.fault_msg) {
    alertBlock = `<div class="tip-alert fault">⚠ ${m.fault_code}: ${m.fault_msg.substring(0, 72)}</div>`;
  } else if (m.idle_reason) {
    alertBlock = `<div class="tip-alert idle">⏸ ${m.idle_reason.substring(0, 72)}</div>`;
  } else if (m.maintenance_type) {
    alertBlock = `<div class="tip-alert maintenance">🔧 ${m.maintenance_type.substring(0, 72)}</div>`;
  }

  return `
    <div class="asset-tip">
      <div class="tip-name">${m.name}</div>
      <div class="tip-id">${m.id}</div>
      <span class="tip-badge ${m.state}">${m.state.toUpperCase()}</span>
      <div class="tip-divider"></div>
      <div class="tip-row"><span>OEE</span><span class="tip-val">${oeeStr}</span></div>
      <div class="tip-row"><span>Temperature</span><span class="tip-val">${tempStr}</span></div>
      <div class="tip-row"><span>Cycle Time</span><span class="tip-val">${cycleStr}</span></div>
      <div class="tip-row"><span>Units (shift)</span><span class="tip-val">${unitStr}</span></div>
      ${alertBlock}
      <div class="tip-divider"></div>
      <div class="tip-click">Click to run AI diagnosis</div>
    </div>
  `;
}

function getMachineIcon(id) {
  if (id.startsWith('BDY')) {
    // Body shop / stamping / welding
    return `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" width="26" height="26">
      <path d="M4 22 L8 14 L14 12 L22 12 L27 15 L28 22 Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" fill="currentColor" fill-opacity="0.12"/>
      <circle cx="9"  cy="23" r="3" stroke="currentColor" stroke-width="1.4" fill="none"/>
      <circle cx="23" cy="23" r="3" stroke="currentColor" stroke-width="1.4" fill="none"/>
      <line x1="12" y1="23" x2="20" y2="23" stroke="currentColor" stroke-width="1.4"/>
      <line x1="14" y1="12" x2="14" y2="18" stroke="currentColor" stroke-width="1.2" opacity="0.5"/>
      <line x1="20" y1="12" x2="20" y2="18" stroke="currentColor" stroke-width="1.2" opacity="0.5"/>
      <line x1="8"  y1="14" x2="4"  y2="10" stroke="currentColor" stroke-width="1.2" opacity="0.4" stroke-linecap="round"/>
    </svg>`;
  } else if (id.startsWith('PNT')) {
    // Paint spray booth
    return `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" width="26" height="26">
      <rect x="4" y="8" width="16" height="18" rx="2" stroke="currentColor" stroke-width="1.4"/>
      <rect x="7" y="11" width="10" height="12" rx="1" fill="currentColor" fill-opacity="0.15"/>
      <line x1="20" y1="13" x2="24" y2="11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
      <circle cx="25" cy="10" r="1.5" fill="currentColor" opacity="0.7"/>
      <circle cx="27" cy="15" r="1"   fill="currentColor" opacity="0.45"/>
      <circle cx="26" cy="19" r="1"   fill="currentColor" opacity="0.35"/>
      <line x1="20" y1="17" x2="25" y2="16" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      <line x1="20" y1="21" x2="24" y2="20" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      <line x1="7" y1="26" x2="17" y2="26" stroke="currentColor" stroke-width="1.2" opacity="0.4" stroke-linecap="round"/>
    </svg>`;
  } else if (id.startsWith('PTN')) {
    // Engine / gear / powertrain
    return `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" width="26" height="26">
      <circle cx="16" cy="16" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/>
      <circle cx="16" cy="16" r="3" fill="currentColor" opacity="0.4"/>
      <line x1="16" y1="4"  x2="16" y2="9"  stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="16" y1="23" x2="16" y2="28" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="4"  y1="16" x2="9"  y2="16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="23" y1="16" x2="28" y2="16" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="7.5" y1="7.5" x2="11" y2="11" stroke="currentColor" stroke-width="2"   stroke-linecap="round"/>
      <line x1="21" y1="21"  x2="24.5" y2="24.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <line x1="24.5" y1="7.5" x2="21" y2="11" stroke="currentColor" stroke-width="2"   stroke-linecap="round"/>
      <line x1="7.5" y1="24.5" x2="11" y2="21" stroke="currentColor" stroke-width="2"   stroke-linecap="round"/>
    </svg>`;
  } else {
    // Final assembly — car silhouette
    return `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" width="26" height="26">
      <path d="M3 21 L5 17 L10 13 L16 12 L22 13 L27 17 L29 21 L29 23 L3 23 Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" fill="currentColor" fill-opacity="0.15"/>
      <path d="M10 13 L12 9 L20 9 L22 13" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" fill="currentColor" fill-opacity="0.25"/>
      <circle cx="9"  cy="23" r="3.5" stroke="currentColor" stroke-width="1.4" fill="none"/>
      <circle cx="23" cy="23" r="3.5" stroke="currentColor" stroke-width="1.4" fill="none"/>
      <circle cx="9"  cy="23" r="1.2" fill="currentColor" opacity="0.5"/>
      <circle cx="23" cy="23" r="1.2" fill="currentColor" opacity="0.5"/>
      <line x1="12.5" y1="23" x2="19.5" y2="23" stroke="currentColor" stroke-width="1.2"/>
    </svg>`;
  }
}

function shortMachineName(name) {
  if (!name) return '';
  const words = name.split(' ');
  return words.length <= 3 ? name : words.slice(0, 3).join(' ') + '…';
}

// ── Machine Status Modal ──────────────────────────────────────────────────────
function showMachineStatus(machineId) {
  const machine = allMachines.find(m => m.id === machineId);
  if (!machine) return;

  const alarms  = allAlarms.filter(a => a.machine_id === machineId);
  const modal   = document.getElementById('machine-status-modal');
  const overlay = document.getElementById('machine-status-overlay');

  const stateLabel = { running: 'RUNNING', fault: 'FAULT', idle: 'IDLE', maintenance: 'PM' }[machine.state] || machine.state.toUpperCase();
  const stateColor = machine.state === 'running' ? '#00DC82' : machine.state === 'fault' ? '#ef4444' : machine.state === 'idle' ? '#f59e0b' : '#3b82f6';

  const faultBlock = machine.state === 'fault' && machine.fault_code ? `
    <div class="msm-fault-hero">
      <div class="msm-fault-code">${machine.fault_code}</div>
      <div class="msm-fault-msg">${machine.fault_msg || ''}</div>
    </div>` : '';

  const alarmRows = alarms.length ? alarms.map(a => `
    <div class="msm-alarm msm-alarm-${a.severity.toLowerCase()}">
      <span class="msm-alarm-code">[${a.code}]</span>
      <div class="msm-alarm-detail">
        <div class="msm-alarm-msg">${a.message}</div>
        <div class="msm-alarm-cause">Root Cause: ${a.ai_root_cause}</div>
      </div>
      <span class="msm-alarm-sev">${a.severity}</span>
    </div>`).join('') :
    `<div class="msm-no-alarms">No active alarms</div>`;

  modal.innerHTML = `
    <div class="msm-header">
      <div class="msm-title-block">
        <div class="msm-machine-id">${machine.id}</div>
        <div class="msm-machine-name">${machine.name}</div>
        <div class="msm-machine-desc">${machine.description || ''}</div>
      </div>
      <div class="msm-header-right">
        <div class="msm-state-badge" style="color:${stateColor};border-color:${stateColor}20;background:${stateColor}15">${stateLabel}</div>
        ${machine.state === 'running' ? `<div class="msm-oee-big">${machine.oee}% <span>OEE</span></div>` : ''}
      </div>
      <button class="msm-close" onclick="closeMachineStatus()">✕</button>
    </div>

    ${faultBlock}

    <div class="msm-body">
      <div class="msm-section">
        <div class="msm-section-title">Active Alarms</div>
        ${alarmRows}
      </div>
      <div class="msm-section">
        <div class="msm-section-title">Live Sensor Data</div>
        <div class="msm-sensors">
          <div class="msm-sensor"><div class="msm-sensor-label">Temperature</div><div class="msm-sensor-val">${machine.temp != null ? machine.temp + '°C' : '—'}</div></div>
          <div class="msm-sensor"><div class="msm-sensor-label">OEE</div><div class="msm-sensor-val">${machine.state === 'running' ? machine.oee + '%' : '—'}</div></div>
          <div class="msm-sensor"><div class="msm-sensor-label">Cycle Time</div><div class="msm-sensor-val">${machine.cycle_time_sec ? machine.cycle_time_sec + 's' : '—'}</div></div>
          <div class="msm-sensor"><div class="msm-sensor-label">Units / Shift</div><div class="msm-sensor-val">${machine.units_this_shift > 0 ? machine.units_this_shift.toLocaleString() : '—'}</div></div>
        </div>
      </div>
    </div>
  `;

  overlay.classList.remove('hidden');
  modal.classList.remove('hidden');
}

function closeMachineStatus() {
  document.getElementById('machine-status-overlay').classList.add('hidden');
  document.getElementById('machine-status-modal').classList.add('hidden');
}

// ── OEE Tab ───────────────────────────────────────────────────────────────────
function updateOeeTab(_kpi, _machines) {
  // Delegate to applyFilters so period/shift/plant filters are always respected
  applyFilters();
}

// Theme-aware chart colors
function tc(dark, light) {
  return document.body.classList.contains('light') ? light : dark;
}
function chartGridColor()   { return tc('#E5E8EF', '#1A1A1A'); }
function chartTickColor()   { return tc('#6B7280', '#666666'); }
function chartBgColor()     { return tc('rgba(0,0,0,0)', '#0F0F0F'); }
function chartBorderColor() { return tc('#D1D5DB', '#2A2A2A'); }
function legendLabelColor() { return tc('#374151', '#666'); }

// Per-machine OEE factor data (Availability × Performance × Quality = OEE)
// Factors calibrated to match live OEE values and the cascade failure story.
const OEE_FACTORS = {
  'BDY-STM-01': { a: 74.2, p: 82.1, q: 92.8,
    a_note: 'Forced idle — FAL-ASM-01 conveyor fault blocking all body throughput upstream',
    p_note: 'Progressive die feed rate within spec; minor setup delays between die changes',
    q_note: 'Stamped panels meeting dimensional tolerance — no scrapped blanks this shift',
    solutions: [
      'Restore FAL-ASM-01 to clear WIP queue and unlock full stamping capacity (immediate)',
      'Implement accumulation buffer decoupling to isolate stamping from final assembly stops',
      'Review die change sequence — 3 min average reduction per change yields ~2% Availability gain',
    ]
  },
  'PNT-PRP-01': { a: 76.4, p: 83.2, q: 92.6,
    a_note: 'Reduced body volume entering line — PNT-ECT-01 bath fault has cut upstream demand',
    p_note: 'Phosphate bath cycle time nominal; pH trending toward upper limit (+0.4 vs target)',
    q_note: 'Coating weight within 8–12 g/m² spec on all panels checked this shift',
    solutions: [
      'Restore PNT-ECT-01 E-Coat bath to resume full panel throughput through phosphate stage',
      'Adjust bath chemistry within next 48h — pH at 5.9 vs. 5.5 target reduces conversion quality',
      'Increase rinse stage dwell time by 15s to reduce iron dragout and protect E-Coat bath life',
    ]
  },
  'PTN-MCH-01': { a: 82.4, p: 84.8, q: 90.5,
    a_note: 'Scheduled coolant change consumed 28 min; no unplanned stops this shift',
    p_note: 'Spindle load trending high (78% vs 65% baseline) — boring insert showing wear pattern',
    q_note: 'Bore diameter CPK at 1.12 — below 1.33 target; 3 blocks rejected for out-of-tolerance',
    solutions: [
      'Replace boring head insert immediately — spindle load increase indicates 60–70% tool life consumed',
      'Check coolant flow rate to boring spindle — reduced flow is contributing to thermal drift in bore diameter',
      'Reduce feed rate by 8% until insert replaced to recover Quality factor to >95%',
    ]
  },
  'PTN-HAD-01': { a: 70.3, p: 81.2, q: 92.4,
    a_note: 'WIP starvation — FAL-ASM-01 fault cascaded upstream, reducing head assembly demand',
    p_note: 'Valve clearance measurement cycle adding 6s per head vs. 4s standard',
    q_note: 'Torque-to-yield readings nominal; valve train assembly pass rate 96.8%',
    solutions: [
      'Prioritise FAL-ASM-01 repair — restoring final assembly unlocks full Powertrain line demand',
      'Re-calibrate torque transducer on station 3 — measurement cycle 50% over standard time',
      'Pre-stage head sub-assemblies to reduce idle gaps between engine build cycles',
    ]
  },
  'PTN-DYN-01': { a: 60.1, p: 77.8, q: 89.0,
    a_note: 'Long cold-test cycle (5 min/engine) combined with upstream engine build fault reducing cell utilisation',
    p_note: 'Dyno coupling vibration causing extended re-test loops — 4 engines re-tested this shift',
    q_note: 'Compression variance on 2 engines borderline — leak-down rate at 8% vs 6% spec',
    solutions: [
      'Inspect and replace dyno coupling — vibration signature confirms worn flexible element (7,200 hr life exceeded)',
      'Restore PTN-BLD-01 engine build station to increase engine feed rate into dyno cell',
      'Recalibrate leak-down test fixture seal — false failures inflating re-test rate by ~15%',
    ]
  },
};

function _oeeFactors(machine) {
  const known = OEE_FACTORS[machine.id];
  if (known) return known;
  // Generic derivation for any machine not in the lookup
  const oee = machine.oee || 0;
  const a   = Math.min(99, oee + 3.5 + Math.sin(oee) * 2);
  const p   = Math.min(99, oee + 1.8 + Math.cos(oee) * 1.5);
  const q   = Math.min(99, oee + 4.8 + Math.sin(oee * 0.7) * 1.2);
  return { a, p, q,
    a_note: 'Availability affected by unplanned stops and upstream queue fluctuations',
    p_note: 'Performance losses from minor stoppages and speed reductions',
    q_note: 'Quality losses from rework and first-pass failures',
    solutions: [
      'Investigate root cause of unplanned stops to improve Availability',
      'Reduce minor stoppages and optimise cycle time to recover Performance',
      'Review process parameters to reduce rework and improve Quality yield',
    ]
  };
}

function showOeeFactors(machine) {
  const panel = document.getElementById('oee-factors-panel');
  if (!panel) return;

  const f       = _oeeFactors(machine);
  const oeeCalc = ((f.a / 100) * (f.p / 100) * (f.q / 100) * 100).toFixed(1);
  const oeeColor = machine.oee >= 80 ? '#00DC82' : machine.oee >= 65 ? '#FFD600' : '#FF8C00';

  const factorBar = (pct, color) =>
    `<div class="oee-factor-bar-track"><div class="oee-factor-bar-fill" style="width:${pct}%;background:${color}"></div></div>`;

  panel.innerHTML = `
    <div class="oee-factors-header">
      <div class="oee-factors-machine">
        <span class="oee-factors-id">${machine.id}</span>
        <span class="oee-factors-name">${machine.name}</span>
      </div>
      <div class="oee-factors-formula">
        <span class="oee-f-val" style="color:#60a5fa">${f.a.toFixed(1)}%</span>
        <span class="oee-f-op">×</span>
        <span class="oee-f-val" style="color:#a78bfa">${f.p.toFixed(1)}%</span>
        <span class="oee-f-op">×</span>
        <span class="oee-f-val" style="color:#34d399">${f.q.toFixed(1)}%</span>
        <span class="oee-f-op">=</span>
        <span class="oee-f-oee" style="color:${oeeColor}">${oeeCalc}%</span>
      </div>
      <button class="oee-factors-close" onclick="document.getElementById('oee-factors-panel').classList.add('hidden');document.getElementById('oee-click-hint').classList.remove('hidden')">✕</button>
    </div>
    <div class="oee-factors-body">
      <div class="oee-factor-block">
        <div class="oee-factor-label" style="color:#60a5fa">AVAILABILITY</div>
        <div class="oee-factor-pct" style="color:#60a5fa">${f.a.toFixed(1)}%</div>
        ${factorBar(f.a, '#60a5fa')}
        <div class="oee-factor-note">${f.a_note}</div>
      </div>
      <div class="oee-factor-block">
        <div class="oee-factor-label" style="color:#a78bfa">PERFORMANCE</div>
        <div class="oee-factor-pct" style="color:#a78bfa">${f.p.toFixed(1)}%</div>
        ${factorBar(f.p, '#a78bfa')}
        <div class="oee-factor-note">${f.p_note}</div>
      </div>
      <div class="oee-factor-block">
        <div class="oee-factor-label" style="color:#34d399">QUALITY</div>
        <div class="oee-factor-pct" style="color:#34d399">${f.q.toFixed(1)}%</div>
        ${factorBar(f.q, '#34d399')}
        <div class="oee-factor-note">${f.q_note}</div>
      </div>
    </div>
    <div class="oee-factors-solutions">
      <div class="oee-solutions-title">Improvement Actions</div>
      ${f.solutions.map((s, i) => `
        <div class="oee-solution-row">
          <span class="oee-solution-num">${i + 1}</span>
          <span class="oee-solution-text">${s}</span>
        </div>
      `).join('')}
    </div>
  `;
  document.getElementById('oee-click-hint')?.classList.add('hidden');
  panel.classList.remove('hidden');
}

function renderMachineOeeChart(machines) {
  const running = machines.filter(m => m.oee > 0);
  const ctx     = document.getElementById('oee-machine-chart').getContext('2d');
  if (machineChart) machineChart.destroy();

  const colors = running.map(m =>
    m.state === 'fault' ? '#FF4444' :
    m.oee >= 90         ? '#00DC82' :
    m.oee >= 80         ? '#FFD600' : '#FF8C00'
  );

  const barValueLabels = {
    id: 'barValueLabels',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((dataset, i) => {
        const meta = chart.getDatasetMeta(i);
        meta.data.forEach((bar, j) => {
          const val = dataset.data[j];
          ctx.save();
          ctx.fillStyle = 'rgba(255,255,255,0.72)';
          ctx.font = '700 9px -apple-system, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(val + '%', bar.x, bar.y - 3);
          ctx.restore();
        });
      });
    },
  };

  machineChart = new Chart(ctx, {
    type: 'bar',
    plugins: [barValueLabels],
    data: {
      labels: running.map(m => m.id),
      datasets: [{ label: 'OEE %', data: running.map(m => m.oee), backgroundColor: colors, borderRadius: 3 }],
    },
    options: {
      responsive: true,
      onClick(_, elements) {
        if (!elements.length) return;
        const machine = running[elements[0].index];
        showOeeFactors(machine);
      },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: '#0F0F0F', borderColor: '#2A2A2A', borderWidth: 1,
          callbacks: { footer: () => 'Click to see A × P × Q breakdown' } },
      },
      scales: {
        x: { ticks: { color: chartTickColor(), font: { size: 9 }, maxRotation: 45 }, grid: { display: false } },
        y: { min: 0, max: 100, display: false },
      },
    },
  });
}

function renderOeeBreakdownCards(machines) {
  const el      = document.getElementById('oee-breakdown-cards');
  const running = machines.filter(m => m.state === 'running' && m.oee > 0).slice(0, 6);

  el.innerHTML = running.map(m => {
    const oeeColor = m.oee >= 90 ? '#00DC82' : m.oee >= 80 ? '#FFD600' : '#FF8C00';
    return `
      <div class="oee-breakdown-card">
        <div class="obc-machine">${m.id}</div>
        <div class="obc-oee" style="color:${oeeColor};">${m.oee}%</div>
        <div class="obc-row"><span class="obc-label">Availability</span><span class="obc-val">${Math.min(99.9, m.oee + 3.1).toFixed(1)}%</span></div>
        <div class="obc-row"><span class="obc-label">Performance</span><span class="obc-val">${Math.min(99.9, m.oee + 1.4).toFixed(1)}%</span></div>
        <div class="obc-row"><span class="obc-label">Quality</span><span class="obc-val">${Math.min(99.9, m.oee + 4.2).toFixed(1)}%</span></div>
        <div class="obc-bar-wrap"><div class="obc-bar" style="width:${m.oee}%;background:${oeeColor};"></div></div>
      </div>
    `;
  }).join('');
}

// ── Downtime ──────────────────────────────────────────────────────────────────
function renderParetoChart(pareto) {
  const ctx = document.getElementById('pareto-chart').getContext('2d');
  if (paretoChart) paretoChart.destroy();

  let cumulative = 0;
  const cumPcts  = pareto.map(p => { cumulative += p.pct; return +cumulative.toFixed(1); });

  paretoChart = new Chart(ctx, {
    data: {
      labels: pareto.map(p => p.reason),
      datasets: [
        { type: 'bar',  label: 'Minutes',      data: pareto.map(p => p.minutes), backgroundColor: ['#FF4444','#FF8C00','#FFD600','#4CC9F0','#A78BFA','#666'], borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'Cumulative %', data: cumPcts, borderColor: '#FF3621', borderWidth: 2, pointRadius: 3, fill: false, yAxisID: 'y2', tension: 0 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#666', font: { size: 10 }, boxWidth: 10 } }, tooltip: { backgroundColor: '#0F0F0F', borderColor: '#2A2A2A', borderWidth: 1 } },
      scales: {
        x:  { ticks: { color: chartTickColor(), font: { size: 10 } }, grid: { color: chartGridColor() } },
        y:  { ticks: { color: chartTickColor(), font: { size: 10 } }, grid: { color: chartGridColor() }, title: { display: true, text: 'Minutes', color: chartTickColor(), font: { size: 9 } } },
        y2: { position: 'right', min: 0, max: 100, ticks: { color: '#FF3621', font: { size: 10 } }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function renderMtbfTable(mtbf) {
  const tbody = document.getElementById('mtbf-tbody');
  tbody.innerHTML = mtbf.map(m => {
    const flagged = m.flagged ? '<span style="color:var(--red);font-size:9px;font-weight:800;margin-left:4px;">⚠ BELOW 200H</span>' : '';
    return `
      <tr>
        <td><span style="font-family:monospace;font-size:11px;">${m.id}</span></td>
        <td><span style="color:${m.mtbf_hrs < 200 ? 'var(--red)' : m.mtbf_hrs < 300 ? 'var(--yellow)' : 'var(--green)'};font-weight:700;">${m.mtbf_hrs}h</span>${flagged}</td>
        <td>${m.mttr_hrs}h</td>
        <td>${m.failures_ytd}</td>
        <td><span class="alarm-sev ${m.flagged ? 'CRITICAL' : 'MEDIUM'}">${m.flagged ? 'ALERT' : 'OK'}</span></td>
      </tr>
    `;
  }).join('');
}

function renderAlarmList(alarms) {
  document.getElementById('alarm-count-label').textContent = `${alarms.length} active`;
  const el = document.getElementById('alarm-list');
  el.innerHTML = alarms.map(a => `
    <div class="alarm-item">
      <div class="alarm-item-header">
        <span class="alarm-sev ${a.severity}">${a.severity}</span>
        <span class="alarm-machine">${a.machine_id}</span>
        <span class="alarm-acked">${a.acknowledged ? '✓ Acked' : '⚠ Unacked'}</span>
      </div>
      <div class="alarm-msg">${a.message}</div>
      <div class="alarm-impact">${a.impact}</div>
    </div>
  `).join('');
}

// ── Quality ───────────────────────────────────────────────────────────────────
function renderQuality(quality) {
  const s   = quality.summary;
  const fyp = s.first_pass_yield;

  document.getElementById('q-fpy').textContent      = fyp + '%';
  document.getElementById('q-fpy').className        = 'kpi-value ' + (fyp >= 99 ? 'green' : fyp >= 97 ? 'yellow' : 'red');
  document.getElementById('q-fpy-bar').style.width  = fyp + '%';
  document.getElementById('q-scrap').textContent    = s.total_scrap_shift + ' units';
  document.getElementById('q-rework').textContent   = s.total_rework_shift + ' units';
  document.getElementById('q-inspected').textContent = s.total_inspected_shift.toLocaleString();
  document.getElementById('q-passed').textContent   = s.total_passed_shift.toLocaleString();

  renderDefectChart(quality.defects);
  renderDefectDonut(quality.defects);
}

function renderDefectChart(defects) {
  const ctx = document.getElementById('defect-chart').getContext('2d');
  if (defectChart) defectChart.destroy();

  defectChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: defects.map(d => d.type),
      datasets: [{ label: 'Count', data: defects.map(d => d.count), backgroundColor: ['#FF4444','#FF8C00','#FFD600','#A78BFA','#4CC9F0','#666'], borderRadius: 4 }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { backgroundColor: chartBgColor(), borderColor: chartBorderColor(), borderWidth: 1 } },
      scales: {
        x: { ticks: { color: chartTickColor(), font: { size: 10 } }, grid: { color: chartGridColor() } },
        y: { ticks: { color: chartTickColor(), font: { size: 10 } }, grid: { color: chartGridColor() } },
      },
    },
  });
}

function renderDefectDonut(defects) {
  const ctx = document.getElementById('defect-donut').getContext('2d');
  if (defectDonut) defectDonut.destroy();

  defectDonut = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: defects.map(d => d.type),
      datasets: [{ data: defects.map(d => d.count), backgroundColor: ['#FF4444','#FF8C00','#FFD600','#A78BFA','#4CC9F0','#666'], borderWidth: 1, borderColor: chartBgColor() }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { color: legendLabelColor(), font: { size: 9 }, padding: 6, boxWidth: 8 } },
        tooltip: { backgroundColor: chartBgColor(), borderColor: chartBorderColor(), borderWidth: 1 },
      },
    },
  });
}

// ── Vision AI Inspection ───────────────────────────────────────────────────────

const VISION_PARTS = [
  { id: 'insp_001', part: 'Door Outer — RH Front' },
  { id: 'insp_002', part: 'Hood Outer Panel' },
  { id: 'insp_003', part: 'Roof Panel' },
  { id: 'insp_004', part: 'Quarter Panel — RH' },
  { id: 'insp_005', part: 'Fender — LH Front' },
  { id: 'insp_006', part: 'Door Outer — LH Front' },
  { id: 'insp_007', part: 'Trunk Lid Panel' },
  { id: 'insp_008', part: 'Door Outer — LH Rear' },
  { id: 'insp_009', part: 'Quarter Panel — LH' },
  { id: 'insp_010', part: 'Fender — RH Front' },
];

let visionResults = {};

function initVisionGrid() {
  const grid = document.getElementById('vision-grid');
  if (!grid) return;
  grid.innerHTML = VISION_PARTS.map(p => `
    <div class="vision-card" id="vcard-${p.id}" data-id="${p.id}">
      <div class="vision-img-wrap" onclick="openLightbox('/manufacturing/api/inspection/image/${p.id}', '${p.part}')">
        <img src="/manufacturing/api/inspection/image/${p.id}" alt="${p.part}" loading="lazy" />
        <div class="scan-line hidden" id="vscan-${p.id}"></div>
        <div class="defect-bbox hidden" id="vbbox-${p.id}"></div>
        <div class="vision-badge hidden" id="vbadge-${p.id}"></div>
      </div>
      <div class="vision-card-meta">
        <div class="vision-part-row">
          <div class="vision-part">${p.part}</div>
          <div class="vision-status-pill" id="vstatus-${p.id}"></div>
        </div>
        <div class="vision-result pending" id="vresult-${p.id}">Awaiting inspection</div>
      </div>
    </div>
  `).join('');
}

async function runInspection(imageId) {
  const card     = document.getElementById(`vcard-${imageId}`);
  const scanEl   = document.getElementById(`vscan-${imageId}`);
  const bboxEl   = document.getElementById(`vbbox-${imageId}`);
  const badgeEl  = document.getElementById(`vbadge-${imageId}`);
  const resEl    = document.getElementById(`vresult-${imageId}`);
  const statusEl = document.getElementById(`vstatus-${imageId}`);

  // Scanning animation
  card.classList.remove('pass', 'fail');
  card.classList.add('scanning');
  scanEl.classList.remove('hidden');
  bboxEl.classList.add('hidden');
  badgeEl.classList.add('hidden');
  resEl.className = 'vision-result scanning';
  resEl.textContent = 'Scanning…';

  try {
    const r = await fetch(`/manufacturing/api/inspect/${imageId}`);
    const data = await r.json();
    visionResults[imageId] = data;

    // Small pause so the animation reads naturally
    await new Promise(res => setTimeout(res, 280));
    scanEl.classList.add('hidden');
    card.classList.remove('scanning');

    if (data.prediction === 'defective') {
      card.classList.add('fail');
      resEl.className = 'vision-result fail';
      resEl.textContent = `${data.defect_type} · ${(data.confidence * 100).toFixed(1)}%`;
      badgeEl.textContent = data.severity;
      badgeEl.className = `vision-badge ${data.severity === 'HIGH' ? 'badge-high' : 'badge-med'}`;
      badgeEl.classList.remove('hidden');
      statusEl.textContent = 'FAIL';
      statusEl.className = 'vision-status-pill pill-fail';

      // Bounding box overlay (coordinates are for 320×320 source image)
      if (data.bbox) {
        const [x0, y0, x1, y1] = data.bbox;
        bboxEl.style.left   = (x0 / 320 * 100).toFixed(2) + '%';
        bboxEl.style.top    = (y0 / 320 * 100).toFixed(2) + '%';
        bboxEl.style.width  = ((x1 - x0) / 320 * 100).toFixed(2) + '%';
        bboxEl.style.height = ((y1 - y0) / 320 * 100).toFixed(2) + '%';
        const labelText = (data.defect_type || 'DEFECT').replace('E-Coat Adhesion Failure', 'E-COAT');
        bboxEl.innerHTML = `
          <div class="defect-corner tl"></div>
          <div class="defect-corner tr"></div>
          <div class="defect-corner bl"></div>
          <div class="defect-corner br"></div>
          <div class="defect-label">${labelText} · ${(data.confidence * 100).toFixed(0)}%</div>
        `;
        bboxEl.classList.remove('hidden');
      }
    } else {
      card.classList.add('pass');
      resEl.className = 'vision-result pass';
      resEl.textContent = `No Defect · ${(data.confidence * 100).toFixed(1)}%`;
      badgeEl.textContent = 'PASS';
      badgeEl.className = 'vision-badge badge-pass';
      badgeEl.classList.remove('hidden');
      statusEl.textContent = 'PASS';
      statusEl.className = 'vision-status-pill pill-pass';
    }
  } catch (e) {
    scanEl.classList.add('hidden');
    card.classList.remove('scanning');
    resEl.className = 'vision-result';
    resEl.textContent = 'Error';
  }
}

async function runAllInspections() {
  const btn = document.getElementById('vision-run-btn');
  btn.disabled = true;
  btn.textContent = 'Running…';
  visionResults = {};

  const summary = document.getElementById('vision-summary');
  summary.classList.add('hidden');

  for (let i = 0; i < VISION_PARTS.length; i++) {
    await runInspection(VISION_PARTS[i].id);
    await new Promise(res => setTimeout(res, 120));
  }

  // Summary row
  const vals = Object.values(visionResults);
  const passes  = vals.filter(v => v.prediction === 'clean').length;
  const fails   = vals.filter(v => v.prediction === 'defective').length;
  const modelName = vals[0]?.model || 'databricks-ecoat-defect-v2';
  const ucVol = vals[0]?.uc_volume || '';
  document.getElementById('vsumm-pass').textContent  = `${passes} PASS`;
  document.getElementById('vsumm-fail').textContent  = `${fails} DEFECT`;
  document.getElementById('vsumm-total').textContent = `${vals.length} INSPECTED`;
  document.getElementById('vsumm-model').textContent = `Model: ${modelName}`;
  if (ucVol) {
    document.getElementById('vision-model-tag').textContent = ucVol;
  }
  summary.classList.remove('hidden');

  // Trigger production impact analysis for any defective images
  const defectiveIds = Object.entries(visionResults)
    .filter(([, v]) => v.prediction === 'defective')
    .map(([id]) => id);
  if (defectiveIds.length > 0) {
    runImpactAnalysis(defectiveIds);
  }

  btn.disabled = false;
  btn.textContent = 'Re-run Batch';
}

async function runImpactAnalysis(imageIds) {
  const panel = document.getElementById('impact-panel');
  if (!panel) return;
  panel.classList.remove('hidden');
  document.getElementById('impact-cards').innerHTML = imageIds.map(id => `
    <div class="impact-card loading" id="impact-card-${id}">
      <div class="impact-card-header">
        <span class="impact-part-name">${(visionResults[id]?.part) || id}</span>
        <span class="impact-severity-tag ${visionResults[id]?.severity === 'HIGH' ? 'sev-high' : 'sev-med'}">${visionResults[id]?.severity || ''}</span>
      </div>
      <div class="impact-loading">Analyzing production impact…</div>
    </div>
  `).join('');

  await Promise.all(imageIds.map(async id => {
    try {
      const r = await fetch(`/manufacturing/api/impact/${id}`);
      const data = await r.json();
      renderImpactCard(id, data);
    } catch {
      document.getElementById(`impact-card-${id}`).innerHTML += '<div class="impact-error">Analysis unavailable</div>';
    }
  }));
}

function renderImpactCard(imageId, d) {
  const card = document.getElementById(`impact-card-${imageId}`);
  if (!card) return;
  card.classList.remove('loading');
  card.innerHTML = `
    <div class="impact-card-header">
      <span class="impact-part-name">${d.part}</span>
      <span class="impact-severity-tag ${d.severity === 'HIGH' ? 'sev-high' : 'sev-med'}">${d.severity}</span>
      <span class="impact-decision ${d.decision === 'SCRAP' ? 'dec-scrap' : 'dec-rework'}">${d.decision}</span>
    </div>
    <div class="impact-body">
      <div class="impact-col">
        <div class="impact-col-title">Machine Time Required</div>
        ${d.machine_time.map(m => `
          <div class="impact-station">
            <span class="station-name">${m.station}</span>
            <span class="station-time">${m.minutes} min</span>
          </div>
        `).join('')}
        <div class="impact-total-time">Total: ${d.total_minutes} min</div>
      </div>
      <div class="impact-col">
        <div class="impact-col-title">Materials Required</div>
        ${d.materials.map(m => `
          <div class="impact-material">
            <span class="mat-name">${m.name}</span>
            <span class="mat-qty">${m.quantity}</span>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="impact-footer">
      <span class="impact-cost">Est. Rework Cost: <strong>${d.estimated_cost}</strong></span>
      ${d.decision === 'SCRAP' ? `<span class="impact-scrap-note">New DP780 AHSS blank required — panel cannot be reworked</span>` : ''}
    </div>
  `;
}

// ── Predictive Maintenance ────────────────────────────────────────────────────

async function loadPdmPredictions() {
  const grid = document.getElementById('pdm-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="pdm-loading"><div class="spinner sm"></div> Running failure prediction model…</div>';

  try {
    const r    = await fetch('/manufacturing/api/predict-maintenance');
    const data = await r.json();
    _pdmData = data;
    renderPdmView();
  } catch (e) {
    grid.innerHTML = '<div class="pdm-error">Prediction unavailable — check model endpoint</div>';
  }
}

function togglePdmView(view) {
  _pdmView = view;
  document.querySelectorAll('.pdm-view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  renderPdmView();
}

function _pdmFilteredMachines() {
  if (!_pdmData) return [];
  const plant  = document.getElementById('f-plant')?.value || '';
  const prefix = plant ? _PLANT_LINE[plant] : null;
  return prefix
    ? _pdmData.machines.filter(m => (m.machine_id || '').startsWith(prefix))
    : _pdmData.machines;
}

function renderPdmView() {
  if (!_pdmData) return;
  const machines = _pdmFilteredMachines();

  // Update summary pills to reflect filtered set
  const pills = document.getElementById('pdm-summary-pills');
  const tag   = document.getElementById('pdm-model-tag');
  if (tag && _pdmData.summary?.model) tag.textContent = _pdmData.summary.model;
  if (pills) {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    machines.forEach(m => { const k = m.risk_level?.toLowerCase(); if (k in counts) counts[k]++; });
    pills.innerHTML = [
      counts.critical ? `<span class="pdm-pill pill-critical">${counts.critical} CRITICAL</span>` : '',
      counts.high     ? `<span class="pdm-pill pill-high">${counts.high} HIGH</span>` : '',
      counts.medium   ? `<span class="pdm-pill pill-medium">${counts.medium} MEDIUM</span>` : '',
      counts.low      ? `<span class="pdm-pill pill-low">${counts.low} LOW</span>` : '',
    ].join('');
  }

  if (_pdmView === 'table') renderPdmTable(machines);
  else renderPdmGrid(machines);
}

function renderPdmGrid(machines) {
  const grid = document.getElementById('pdm-grid');
  if (!machines.length) {
    grid.innerHTML = '<div class="pdm-loading">No machines match the current filter.</div>';
    return;
  }
  grid.className = 'pdm-grid';
  grid.innerHTML = machines.map(m => {
    const pct   = Math.round(m.failure_prob * 100);
    const ttf   = m.hours_to_failure > 0
      ? `${m.hours_to_failure.toFixed(1)} hrs`
      : '<span class="pdm-faulted">FAULTED NOW</span>';
    const feats = m.features || {};
    return `
      <div class="pdm-card pdm-risk-${m.risk_level.toLowerCase()}" onclick="showPdmDetail('${m.machine_id}','${m.machine_name}','${m.risk_level}')">
        <div class="pdm-card-top">
          <div class="pdm-machine-info">
            <div class="pdm-machine-id">${m.machine_id}</div>
            <div class="pdm-machine-name">${m.machine_name}</div>
            <div class="pdm-line-tag">${m.line_name || 'Line ' + m.line}</div>
          </div>
          <div class="pdm-risk-badge pdm-badge-${m.risk_level.toLowerCase()}">${m.risk_level}</div>
        </div>

        <div class="pdm-gauge-row">
          <div class="pdm-gauge-label">Failure Probability</div>
          <div class="pdm-gauge-pct">${pct}%</div>
        </div>
        <div class="pdm-gauge-track">
          <div class="pdm-gauge-fill pdm-fill-${m.risk_level.toLowerCase()}" style="width:${pct}%"></div>
        </div>

        <div class="pdm-ttf-row">
          <span class="pdm-ttf-label">Time to Failure</span>
          <span class="pdm-ttf-val">${ttf}</span>
        </div>

        <div class="pdm-sensors">
          ${_pdmSensorChip('Temp', feats.temp_c?.toFixed(1) + '°C', feats.temp_c > 60)}
          ${_pdmSensorChip('Vibration', feats.vibration_rms?.toFixed(2) + ' m/s²', feats.vibration_rms > 3.5)}
          ${_pdmSensorChip('Spindle Load', feats.spindle_load_pct?.toFixed(0) + '%', feats.spindle_load_pct > 85)}
          ${_pdmSensorChip('Oil Pressure', feats.oil_pressure_bar?.toFixed(1) + ' bar', feats.oil_pressure_bar < 1.5)}
          ${_pdmSensorChip('Cycle Dev.', feats.cycle_time_deviation_pct?.toFixed(1) + '%', feats.cycle_time_deviation_pct > 15)}
          ${_pdmSensorChip('Hrs Since PM', Math.round(feats.hours_since_last_pm) + 'h', feats.hours_since_last_pm > 1500)}
        </div>

        <div class="pdm-action">
          <div class="pdm-action-label">Recommended Action</div>
          <div class="pdm-action-text">${m.recommended_action}</div>
        </div>
      </div>
    `;
  }).join('');
}

function renderPdmTable(machines) {
  const grid = document.getElementById('pdm-grid');
  grid.className = 'pdm-table-wrap';
  if (!machines.length) {
    grid.innerHTML = '<div class="pdm-loading">No machines match the current filter.</div>';
    return;
  }
  grid.innerHTML = `
    <table class="pdm-table">
      <thead>
        <tr>
          <th>Machine</th>
          <th>Line</th>
          <th>Risk</th>
          <th>Failure Prob.</th>
          <th>Time to Failure</th>
          <th>Temp</th>
          <th>Vibration</th>
          <th>Hrs Since PM</th>
          <th>Recommended Action</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${machines.map(m => {
          const pct   = Math.round(m.failure_prob * 100);
          const f     = m.features || {};
          const ttf   = m.hours_to_failure > 0 ? `${m.hours_to_failure.toFixed(1)} hrs` : 'FAULTED';
          const tAlert = f.temp_c > 60;
          const vAlert = f.vibration_rms > 3.5;
          const pmAlert = f.hours_since_last_pm > 1500;
          return `
            <tr class="pdm-table-row" onclick="showPdmDetail('${m.machine_id}','${m.machine_name}','${m.risk_level}')">
              <td><span class="pdm-machine-id">${m.machine_id}</span><br><span class="pdm-machine-name">${m.machine_name}</span></td>
              <td class="pdm-line-tag">${m.line_name || 'Line ' + m.line}</td>
              <td><span class="pdm-risk-badge pdm-badge-${m.risk_level.toLowerCase()}">${m.risk_level}</span></td>
              <td>
                <div class="pdm-tbl-prob">
                  <span class="pdm-tbl-pct pdm-fill-${m.risk_level.toLowerCase()}">${pct}%</span>
                  <div class="pdm-gauge-track" style="width:80px;margin-top:4px"><div class="pdm-gauge-fill pdm-fill-${m.risk_level.toLowerCase()}" style="width:${pct}%"></div></div>
                </div>
              </td>
              <td class="${m.hours_to_failure <= 0 ? 'pdm-faulted' : ''}">${ttf}</td>
              <td class="${tAlert  ? 'pdm-tbl-alert' : ''}">${f.temp_c?.toFixed(1) ?? '—'}°C</td>
              <td class="${vAlert  ? 'pdm-tbl-alert' : ''}">${f.vibration_rms?.toFixed(2) ?? '—'} m/s²</td>
              <td class="${pmAlert ? 'pdm-tbl-alert' : ''}">${Math.round(f.hours_since_last_pm ?? 0)}h</td>
              <td class="pdm-tbl-action">${m.recommended_action}</td>
              <td><button class="pdm-tbl-detail-btn" onclick="event.stopPropagation();showPdmDetail('${m.machine_id}','${m.machine_name}','${m.risk_level}')">Detail →</button></td>
            </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

function _pdmSensorChip(label, value, alert) {
  return `<div class="pdm-sensor-chip ${alert ? 'chip-alert' : ''}">
    <span class="chip-label">${label}</span>
    <span class="chip-val">${value}</span>
  </div>`;
}

// ── PDM Detail Modal ──────────────────────────────────────────────────────────

async function showPdmDetail(machineId, machineName, riskLevel) {
  const overlay = document.getElementById('pdm-detail-overlay');
  const modal   = document.getElementById('pdm-detail-modal');
  overlay.classList.remove('hidden');
  modal.classList.remove('hidden');

  // Populate header immediately
  document.getElementById('pdm-modal-machine-id').textContent   = machineId;
  document.getElementById('pdm-modal-machine-name').textContent  = machineName;
  document.getElementById('pdm-modal-sensor-label').textContent  = 'Loading…';
  const badge = document.getElementById('pdm-modal-risk-badge');
  badge.textContent  = riskLevel;
  badge.className    = `pdm-modal-risk-badge pdm-badge-${riskLevel.toLowerCase()}`;

  let ts;
  try {
    ts = await fetch(`/manufacturing/api/pdm-timeseries/${machineId}`).then(r => r.json());
  } catch {
    document.getElementById('pdm-modal-sensor-label').textContent = 'Data unavailable';
    return;
  }

  // Update stats
  document.getElementById('pdm-modal-sensor-label').textContent = ts.label;
  document.getElementById('pdm-modal-current').textContent      = `${ts.current} ${ts.unit}`;
  document.getElementById('pdm-modal-threshold').textContent    = `${ts.threshold} ${ts.unit}`;
  document.getElementById('pdm-modal-prob').textContent         = `${Math.round(ts.failure_prob * 100)}%`;
  document.getElementById('pdm-modal-zone-label').textContent   = ts.threshold_label;

  const isDark    = !document.body.classList.contains('light');
  const gridColor = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)';
  const textColor = isDark ? '#94a3b8' : '#64748b';
  const lineColor = ts.risk_color || '#ef4444';
  const dangerFill = 'rgba(239,68,68,0.13)';

  if (pdmDetailChart) { pdmDetailChart.destroy(); pdmDetailChart = null; }

  const ctx = document.getElementById('pdm-ts-chart').getContext('2d');
  pdmDetailChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: ts.labels,
      datasets: [
        {
          label: ts.label,
          data: ts.values,
          borderColor: lineColor,
          backgroundColor: 'transparent',
          borderWidth: 2.5,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 5,
          fill: {
            target: { value: ts.threshold },
            above: ts.direction === 'above' ? dangerFill : 'transparent',
            below: ts.direction === 'below' ? dangerFill : 'transparent',
          },
        },
        {
          label: ts.threshold_label,
          data: Array(ts.labels.length).fill(ts.threshold),
          borderColor: 'rgba(239,68,68,0.65)',
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1e293b' : '#fff',
          titleColor: textColor,
          bodyColor: isDark ? '#cbd5e1' : '#374151',
          borderColor: isDark ? '#334155' : '#e2e8f0',
          borderWidth: 1,
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)} ${ts.unit}`,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: textColor,
            maxTicksLimit: 8,
            maxRotation: 0,
            font: { size: 11 },
          },
          grid: { color: gridColor },
        },
        y: {
          ticks: { color: textColor, font: { size: 11 } },
          grid: { color: gridColor },
          title: {
            display: true,
            text: ts.unit,
            color: textColor,
            font: { size: 11 },
          },
        },
      },
    },
  });
}

function closePdmDetail() {
  document.getElementById('pdm-detail-overlay').classList.add('hidden');
  document.getElementById('pdm-detail-modal').classList.add('hidden');
  if (pdmDetailChart) { pdmDetailChart.destroy(); pdmDetailChart = null; }
}

// ── Talk Track ────────────────────────────────────────────────────────────────

const TALK_TRACKS = {
  floor: {
    what: 'Real-time map of every machine on the plant floor showing operational status (running, idle, fault), live OEE inputs, active alarm codes, and throughput by production line — updated on a sub-minute streaming pipeline from your manufacturing lakehouse.',
    aiml: 'Sensor fusion models aggregate multi-frequency telemetry streams to detect anomalies before they trigger unplanned stoppages. Fault classification algorithms automatically route alerts to the right maintenance crew, reducing mean-time-to-respond. Streaming anomaly detection identifies machines trending toward fault conditions before the issue becomes a production loss event.',
    benchmark: 'Toyota\'s production system is the global benchmark for real-time floor visibility and the jidoka principle — stopping to fix defects at the source immediately. Siemens\' Amberg Electronics Plant is widely cited in Industry 4.0 literature for near-100% digital traceability per unit. McKinsey & Company cites real-time plant floor monitoring as a top driver of manufacturing productivity improvement across discrete and process industries.',
  },
  oee: {
    what: 'Overall Equipment Effectiveness broken down into Availability, Performance, and Quality for each machine and production line — the industry-standard composite KPI for measuring how effectively manufacturing assets convert scheduled time into good output.',
    aiml: 'ML regression models identify which combinations of shift, product changeover, and maintenance history most strongly predict OEE degradation, enabling supervisors to act before losses accumulate. Anomaly detection continuously monitors OEE components and flags assets trending below threshold before they hit reportable loss levels or end-of-shift reporting buries the signal.',
    benchmark: 'A world-class OEE of 85% or above is the widely cited benchmark established by Seiichi Nakajima and maintained by the OEE Foundation. Industry surveys estimate the average for discrete manufacturers at 60–65%. McKinsey & Company cites OEE improvement as one of the highest-ROI operational levers, with top-quartile plants sustaining 10–15 percentage point OEE advantages over median peers.',
  },
  downtime: {
    what: 'Downtime events categorized by cause — mechanical failure, planned maintenance, changeover, quality stop — with MTBF and MTTR trend analysis over rolling periods to separate chronic recurring failures from new emerging fault modes.',
    aiml: 'Time-series classification models identify recurring downtime patterns linked to specific operators, shifts, or product runs that would be invisible in aggregate fault counts. Natural language processing applied to technician work order notes extracts root-cause signals that structured fault codes alone consistently miss, surfacing systemic issues faster.',
    benchmark: 'McKinsey & Company estimates AI-driven downtime analysis can reduce unplanned downtime by 10–20% in capital-intensive manufacturing. Aberdeen Group research shows best-in-class manufacturers achieve MTBF improvements of 20–30% through systematic downtime analytics programs. Caterpillar and Honeywell are among the manufacturers widely cited in industry press for data-driven predictive maintenance reducing reactive maintenance labor by 15–25%.',
  },
  maintenance: {
    what: 'Machine health scores, predicted time-to-failure, and prioritized maintenance recommendations derived from vibration, temperature, current draw, and cycle count sensor data — presented by risk tier (Critical, Warning, Healthy) so maintenance planners act on the highest-risk assets first.',
    aiml: 'Gradient boosting and survival analysis models predict failure probability from multivariate sensor streams, converting raw telemetry into actionable risk scores. Prescriptive AI ranks work orders by cost-of-delay versus cost-of-maintenance so planners optimize maintenance windows for maximum production impact. Models are versioned and governed in Unity Catalog alongside training data for full auditability.',
    benchmark: 'Deloitte Insights reports industrial predictive maintenance programs delivering 25% reductions in maintenance costs and up to 70% decrease in equipment breakdowns. Caterpillar (Cat Digital) and Rolls-Royce (TotalCare program) are among the most widely referenced deployed examples of predictive maintenance at industrial scale. McKinsey Global Institute estimated the addressable value of predictive maintenance across global manufacturing and infrastructure at $240–630 billion annually.',
  },
  quality: {
    what: 'Computer vision inspection results for E-coat body panels — pass/fail classification per panel, defect type localization (blistering, pinholes, cratering), first pass yield trend, and a production impact analysis showing machine time and material cost associated with each defective unit.',
    aiml: 'Convolutional neural network (CNN) models classify defect types from high-resolution panel images with real-time inference via Databricks Model Serving at line speed. Active learning continuously improves model accuracy as new defect patterns are encountered and labeled. All model versions, training images, and inference results are governed in Unity Catalog for PPAP evidence and recall simulation readiness.',
    benchmark: 'BMW Group is widely cited — including in their own public disclosures and industry publications — for deploying AI-based optical quality inspection in paint and final assembly operations. Industry studies generally report AI vision systems achieving 90%+ defect detection accuracy versus 70–80% for manual visual inspection. Volkswagen and Continental have also published on computer vision deployments for automotive surface and paint quality.',
  },
  shift: {
    what: 'A natural language interface to live manufacturing data — OEE, downtime, quality, and throughput — allowing shift managers and process engineers to get immediate answers from their Delta Lake using plain English, without writing SQL or submitting an analytics request.',
    aiml: 'A large language model (LLM) with retrieval-augmented generation (RAG) grounds all responses in live Unity Catalog-governed tables, preventing hallucination on numerical KPIs. Intent classification routes queries to the appropriate data domain before SQL generation. Multi-turn conversation enables analysts to drill down with follow-up questions without re-establishing context.',
    benchmark: 'Gartner surveys from 2023–2024 found that over 50% of manufacturing executives planned to pilot generative AI for operations within 12 months. Siemens and GE have publicly announced AI assistant deployments for manufacturing operations teams. McKinsey\'s 2023 report on the economic potential of generative AI estimates the technology could deliver over $170 billion in annual value to advanced manufacturing globally.',
  },
  manuals: {
    what: 'A natural language search interface over equipment manuals — allowing maintenance technicians to ask plain-language questions about procedures, torque specifications, and wiring diagrams, with responses grounded in and citing the actual OEM PDFs stored in Unity Catalog Volumes.',
    aiml: 'A retrieval-augmented generation (RAG) system uses vector search over PDF chunks to find the most relevant passages across all manuals, then generates a grounded answer with direct citations to the source document and page number — ensuring technicians get accurate, auditable guidance rather than an unverified response.',
    benchmark: 'McKinsey & Company cites technician knowledge management as a top opportunity in manufacturing AI, with leading plants reporting significant mean-time-to-repair reductions when technicians have instant access to searchable documentation. Siemens and ABB have published on RAG-based maintenance assistant pilots for field service technicians. Industry data consistently shows technicians spend 30–40% of diagnosis time searching for the right documentation — the primary problem this capability solves.',
  },
};

function openInfoPanel(key) {
  const track = TALK_TRACKS[key] || TALK_TRACKS[_activeTab] || TALK_TRACKS.floor;
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
// Plant filter → machine ID prefix
const _PLANT_LINE    = { p1: 'BDY', p2: 'PNT', p3: 'PTN', p4: 'FAL' };
// Machine prefix → production line (for quality defect filtering)
const _PREFIX_LINE   = { BDY: 'A', PNT: 'B', PTN: 'C', FAL: 'S' };

// Shift and period multipliers applied to synthetic data
const _SHIFT_OEE = { '': 1.00, day: 1.04, eve: 1.00, night: 0.93 };
const _SHIFT_DT  = { '': 1.00, day: 0.82, eve: 1.00, night: 1.25 };
const _SHIFT_FPY = { '': 0.0,  day: +1.2, eve:  0.0, night: -3.1 }; // additive to FPY %
const _PERIOD_OEE = { '': 1.00, '24h': 0.97, '7d': 0.95, '30d': 0.92 };
const _PERIOD_DT  = { '': 1.00, '24h': 3.0,  '7d': 21.0, '30d': 90.0 };
const _PERIOD_Q   = { '': 1.00, '24h': 3.0,  '7d': 21.0, '30d': 90.0 };

function _fmtTime(min) {
  if (min < 120) return min + ' min';
  return (min / 60).toFixed(1) + ' hrs';
}

function applyFilters() {
  const selects = document.querySelectorAll('.filter-select');
  const active = Array.from(selects).filter(s => s.value !== '' && s.id !== 'oee-line-filter' && s.id !== 'qual-line-filter' && s.id !== 'qual-defect-filter').length;
  const clearBtn = document.getElementById('filter-clear');
  const countEl  = document.getElementById('filter-count');
  if (clearBtn) clearBtn.classList.toggle('hidden', active === 0);
  if (countEl) {
    countEl.classList.toggle('hidden', active === 0);
    if (active > 0) countEl.textContent = `${active} filter${active > 1 ? 's' : ''} active`;
  }

  const period = document.getElementById('f-period')?.value || '';
  const plant  = document.getElementById('f-plant')?.value  || '';
  const shift  = document.getElementById('f-shift')?.value  || '';
  const prefix = plant ? _PLANT_LINE[plant] : null;

  const oeeMul = (_PERIOD_OEE[period] ?? 1) * (_SHIFT_OEE[shift] ?? 1);
  const dtMul  = (_PERIOD_DT[period]  ?? 1) * (_SHIFT_DT[shift]  ?? 1);
  const qMul   = (_PERIOD_Q[period]   ?? 1);
  const fpyDelta = _SHIFT_FPY[shift] ?? 0;

  // ── Floor map: dim/restore machine nodes by plant ────────────────────────
  document.querySelectorAll('.fnode[id^="fnode-"]').forEach(node => {
    const mp = node.id.replace('fnode-', '').split('-')[0];
    const show = !prefix || mp === prefix;
    node.style.opacity = show ? '' : '0.18';
    node.style.pointerEvents = show ? '' : 'none';
  });

  // ── OEE KPI cards + machine chart + breakdown ────────────────────────────
  if (allMachines && allMachines.length) {
    const src = (prefix
      ? allMachines.filter(m => (m.id || '').startsWith(prefix))
      : allMachines).length
        ? (prefix ? allMachines.filter(m => (m.id || '').startsWith(prefix)) : allMachines)
        : allMachines;

    const scaled = src.map(m => ({ ...m, oee: Math.min(99.9, +(m.oee * oeeMul).toFixed(1)) }));
    const running = scaled.filter(m => m.state === 'running' && m.oee > 0);
    const plantOee = running.length
      ? +(running.reduce((s, m) => s + m.oee, 0) / running.length).toFixed(1) : 0;
    const lineAvg = (ln) => {
      const ms = scaled.filter(m => m.line === ln && m.state === 'running' && m.oee > 0);
      return ms.length ? +(ms.reduce((s, m) => s + m.oee, 0) / ms.length).toFixed(1) : 0;
    };

    const setTxt = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    const oeePlEl = document.getElementById('oee-plant');
    if (oeePlEl) {
      oeePlEl.textContent = plantOee + '%';
      oeePlEl.className = 'kpi-value ' + (plantOee >= 88 ? 'green' : plantOee >= 80 ? 'yellow' : 'red');
    }
    setTxt('oee-line-a', lineAvg('A') + '%');
    setTxt('oee-line-b', lineAvg('B') + '%');
    setTxt('oee-line-c', lineAvg('C') + '%');

    const hdrEl = document.getElementById('hdr-oee');
    if (hdrEl) {
      hdrEl.textContent = plantOee + '%';
      hdrEl.className = 'hdr-kpi-val ' + (plantOee >= 88 ? 'green' : plantOee >= 80 ? 'amber' : 'red');
    }
    renderMachineOeeChart(scaled);
    renderOeeBreakdownCards(scaled);
  }

  // ── Downtime KPIs + Pareto chart ─────────────────────────────────────────
  if (_paretoRaw.length) {
    const scaledPareto = _paretoRaw.map(p => ({ ...p, minutes: Math.round(p.minutes * dtMul) }));
    const totalMin = scaledPareto.reduce((s, p) => s + p.minutes, 0);
    const unplanned = scaledPareto
      .filter(p => !p.reason.toLowerCase().includes('planned maintenance'))
      .reduce((s, p) => s + p.minutes, 0);

    const setTxt = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    setTxt('dt-total', _fmtTime(totalMin));
    setTxt('dt-unplanned', _fmtTime(unplanned));

    const rescaledPareto = scaledPareto.map(p => ({
      ...p,
      pct: totalMin > 0 ? +((p.minutes / totalMin) * 100).toFixed(1) : 0,
    }));
    renderParetoChart(rescaledPareto);
  }

  // ── MTBF table: filter by plant prefix ───────────────────────────────────
  if (_mtbfRaw.length) {
    const filtered = prefix ? _mtbfRaw.filter(m => m.id.startsWith(prefix)) : _mtbfRaw;
    const tbody = document.getElementById('mtbf-tbody');
    if (tbody) {
      if (!filtered.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:16px;color:var(--yellow)">No maintenance records for selected plant</td></tr>`;
      } else {
        renderMtbfTable(filtered);
      }
    }
  }

  // ── Alarm list: filter by plant prefix ───────────────────────────────────
  if (allAlarms && allAlarms.length) {
    const filtered = prefix ? allAlarms.filter(a => (a.machine_id || '').startsWith(prefix)) : allAlarms;
    renderAlarmList(filtered);
  }

  // ── PDM tab: re-render with filtered machines ─────────────────────────────
  if (_pdmData) renderPdmView();

  // ── Quality KPIs + charts ─────────────────────────────────────────────────
  if (_qualityRaw) {
    const targetLine = prefix ? _PREFIX_LINE[prefix] : null;
    const filteredDefects = targetLine
      ? _qualityRaw.defects.filter(d => d.line === targetLine)
      : _qualityRaw.defects;
    const scaledDefects = filteredDefects.map(d => ({ ...d, count: Math.round(d.count * qMul) }));

    const s = _qualityRaw.summary;
    const fpyAdj = Math.min(99.9, Math.max(0, s.first_pass_yield + fpyDelta));
    const scaledSummary = {
      ...s,
      first_pass_yield:       +fpyAdj.toFixed(1),
      total_inspected_shift:  Math.round(s.total_inspected_shift * qMul),
      total_passed_shift:     Math.round(s.total_passed_shift * qMul),
      total_scrap_shift:      Math.round(s.total_scrap_shift * qMul),
      total_rework_shift:     Math.round(s.total_rework_shift * qMul),
    };
    renderQuality({ summary: scaledSummary, defects: scaledDefects.length ? scaledDefects : filteredDefects });
  }
}

function clearFilters() {
  document.querySelectorAll('.filter-select').forEach(s => { s.value = ''; });
  applyFilters();
}

// ── Agentic Actions ───────────────────────────────────────────────────────────

const TAB_LABELS = { floor: 'Live Floor', oee: 'OEE Analytics', downtime: 'Downtime', maintenance: 'Predictive Maintenance', quality: 'Quality Monitoring', shift: 'Ask AI' };

// ── Image Lightbox ─────────────────────────────────────────────────────────────
function openLightbox(src, label) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox-label').textContent = label;
  document.getElementById('lightbox-overlay').classList.remove('hidden');
  document.addEventListener('keydown', _lightboxKeyHandler);
}
function closeLightbox() {
  document.getElementById('lightbox-overlay').classList.add('hidden');
  document.getElementById('lightbox-img').src = '';
  document.removeEventListener('keydown', _lightboxKeyHandler);
}
function _lightboxKeyHandler(e) { if (e.key === 'Escape') closeLightbox(); }

const AGENT_ACTIONS = {
  floor: [
    {
      sys: 'SAP',
      title: 'Open a Breakdown Maintenance Notification for FAL-ASM-01',
      desc: 'Log the active encoder fault against the Final Assembly station in the maintenance system — capturing fault classification, functional location, and equipment history — so the electrical work center receives an immediate repair assignment.',
      result: 'Maintenance Notification 10047382 raised · FAL-ASM-01 encoder fault classified · Assigned to Electrical Work Center · IDoc 0000000048291746 confirmed',
    },
    {
      sys: 'Teams',
      title: 'Alert the Plant Floor Operations Channel',
      desc: 'Push a live fault card to the #plant-floor-ops channel showing which machine is down, how long it has been stopped, the fault description, and the recommended first response — so the shift supervisor can act without leaving the Teams feed.',
      result: 'Alert posted to #plant-floor-ops · FAL-ASM-01 down 23 min · Encoder fault E-047 · Repair steps attached · Shift Supervisor M. Chen acknowledged at 14:27',
    },
    {
      sys: 'Email',
      title: 'Notify the Plant Engineering Team by Email',
      desc: 'Send a critical fault summary to the plant engineering distribution list covering equipment details, fault history for this shift, current downtime cost, and escalation status so the right people are informed without manually chasing updates.',
      result: 'Email sent to plant-engineering@company.com · Subject: "[CRITICAL] FAL-ASM-01 Down — Plant 1" · 6 recipients · Equipment history and cost impact included · Delivered 14:28',
    },
  ],
  oee: [
    {
      sys: 'SAP',
      title: 'Revise Today\'s Production Order Quantities',
      desc: 'Update the confirmed output quantities on the active day-shift production order to reflect what is actually achievable given current OEE — keeping production planning and downstream scheduling aligned with reality rather than the original target.',
      result: 'Production Order 1000847392 updated · Confirmed qty 312 → 268 units · Planning adjusted · IDoc 0000000048291801 confirmed · Change document 4800293847 created',
    },
    {
      sys: 'Teams',
      title: 'Publish the Shift OEE Performance Card',
      desc: 'Post a live OEE summary to the #production-reporting channel showing per-line availability, performance, and quality scores alongside the shift target — so production leads see the current gap without logging into a separate system.',
      result: 'OEE card posted to #production-reporting · Plant OEE 71.2% vs 88% target · Line A: 56% avail · Line B: 77% perf · 12 team members notified',
    },
    {
      sys: 'Email',
      title: 'Send the OEE Shift Report to the Plant Manager',
      desc: 'Email a formatted shift report to the plant manager and production lead with the three OEE factor breakdown per machine, root cause summary, and recommended actions to recover output before end of shift.',
      result: 'Email sent to plant.manager@company.com · "OEE Shift Report — Plant 1 — 07 May Day Shift" · Factor breakdown + improvement actions included · 3 recipients · Sent 14:30',
    },
  ],
  downtime: [
    {
      sys: 'SAP',
      title: 'Raise a Planned Maintenance Work Order for FAL-ASM-01',
      desc: 'Create a formal maintenance work order covering inspection, repair, and return-to-service operations for the highest-frequency fault machine — with the required components listed and costs settled to the maintenance cost center — so the next scheduled window is fully prepared.',
      result: 'Work Order 4000183742 raised · FAL-ASM-01 · 3 operations planned · Components: TC4-ENC-200, gasket set · Cost settlement assigned · IDoc 0000000048291855 confirmed',
    },
    {
      sys: 'SAP',
      title: 'Request Spare Parts from Procurement',
      desc: 'Submit a purchase requisition for the three most failure-prone components identified by MTBF analysis — sourced from the preferred vendor — so parts arrive before the next predicted failure rather than after it.',
      result: 'Purchase Requisition 1000294817 submitted · TC4-ENC-200 ×2, electrode tips ×24, CED additive ×1 drum · Preferred vendor assigned · $4,820 auto-approved · IDoc 0000000048291902 confirmed',
    },
    {
      sys: 'Teams',
      title: 'Share the Downtime Pareto with the Maintenance Team',
      desc: 'Post this shift\'s fault frequency ranking to the #maintenance-ops channel — showing each machine\'s contribution to total downtime hours — so the maintenance planner can prioritise the work queue for the next planned outage window.',
      result: 'Pareto posted to #maintenance-ops · FAL-ASM-01 2.1h · BDY-WLD-01 1.4h · PNT-ECT-01 0.8h · Maintenance planner T. Brooks notified',
    },
  ],
  maintenance: [
    {
      sys: 'SAP',
      title: 'Open Emergency Maintenance Orders for All Critical Machines',
      desc: 'Raise maintenance work orders for the three machines currently showing critical failure risk — capturing the sensor readings that triggered the alert as technical notes — so technicians arrive with full context and the work is tracked against the equipment record.',
      result: 'Work Orders raised: 4000183798 (FAL-ASM-01), 4000183799 (BDY-WLD-01), 4000183800 (PNT-ECT-01) · Sensor notes attached · Scheduled 15:30–17:00 · IDocs 0000000048291960–62 confirmed',
    },
    {
      sys: 'SAP',
      title: 'Reserve Critical Spare Parts from the Warehouse',
      desc: 'Pull the required components for the five highest-risk machines from their warehouse bin locations and place a reservation against the maintenance orders — so parts are physically staged at the tool crib before the technician arrives.',
      result: 'Reservation 1000485721 created · TC4-ENC-200 from bin A-14 · Electrode tips from B-07 · Boring inserts from C-03 · Parts kitted at Tool Crib B · IDoc 0000000048292010 confirmed',
    },
    {
      sys: 'Teams',
      title: 'Brief the Maintenance Team on Failure Risks',
      desc: 'Send a failure risk summary card to the #predictive-maintenance channel listing each at-risk machine with its failure probability, the sensor reading driving the prediction, and estimated time to failure — so technicians can prioritise without pulling the data themselves.',
      result: 'Risk briefing posted to #predictive-maintenance · 5 machines flagged · FAL-ASM-01: immediate · PTN-MCH-01: 8.4h · BDY-WLD-01: immediate · 5 technicians notified',
    },
  ],
  quality: [
    {
      sys: 'SAP',
      title: 'Log a Quality Defect Notification for the Failed Panels',
      desc: 'Record the two defective body panels in the quality management system — with defect type classification, catalog codes, and a reference to the current inspection lot — creating a traceable quality record and triggering the standard defect workflow.',
      result: 'Quality Notification 200184729 raised · Blistering (D-031) and pinhole (D-018) classified · Inspection lot 1000039482 referenced · IDoc 0000000048292105 confirmed',
    },
    {
      sys: 'SAP',
      title: 'Open a Rework Order for the Defective Panels',
      desc: 'Create a rework production order routing Panel 003 to scrap disposal and Panel 007 through the rework station — with operations, material movements, and cost settlement to the quality cost center — so the corrective work is formally tracked and costed.',
      result: 'Rework Order 1000847440 created · Panel 003 → scrap route · Panel 007 → rework station · $1,625 total cost settled to quality cost center · IDoc 0000000048292148 confirmed',
    },
    {
      sys: 'Teams',
      title: 'Alert the Quality Control Team',
      desc: 'Post a defect summary to the #quality-control channel covering which panels failed, defect type, financial impact of scrap vs rework, and the E-Coat bath parameter that caused the issue — so the quality lead can action the chemistry correction immediately.',
      result: 'Alert posted to #quality-control · 2 panels failed · SCRAP $1,240 + REWORK $385 · Bath temp spike +4.2°C identified as root cause · QA Lead S. Park acknowledged',
    },
  ],
  shift: [
    {
      sys: 'Teams',
      title: 'Publish the Shift Handover to the Incoming Team',
      desc: 'Post a structured handover card to the #shift-handover channel covering open faults, quality holds, current OEE, and priority actions — so the incoming shift has a complete picture in their Teams feed the moment they start, without a face-to-face briefing.',
      result: 'Handover card posted to #shift-handover · OEE 71.2% · 3 open faults · 2 panels on quality hold · 5 priority actions listed · Incoming team notified at 14:32',
    },
    {
      sys: 'Email',
      title: 'Email the Shift Intelligence Summary to Leadership',
      desc: 'Send a concise summary of the shift\'s AI-generated insights to the plant leadership distribution list — covering performance vs target, root causes identified, and recommended follow-up actions — so decisions can be made before the next shift starts.',
      result: 'Email sent to leadership-plant1@company.com · "Shift Intelligence Summary — Plant 1 — 07 May" · 6 AI insights · 3 recommended actions · 4 recipients · Sent 14:33',
    },
    {
      sys: 'SAP',
      title: 'Record Shift Findings Against the Open Maintenance Notification',
      desc: 'Append a timestamped technical note to the active maintenance notification in the asset management system — capturing the shift\'s AI-generated findings — so there is a permanent, auditable record of what was observed and recommended during this shift.',
      result: 'Technical note appended to Notification 10047382 · 847 characters logged · Timestamp 14:34 · IDoc 0000000048292200 confirmed · Audit record created under DATABRICKS-AI',
    },
  ],
  manuals: [
    {
      sys: 'SAP',
      title: 'Log a Maintenance Work Order for the FAL-ASM-01 Encoder Replacement',
      desc: 'Create a corrective maintenance work order in the asset management system for the Transfer Car encoder replacement procedure identified from the equipment manual — including the required spare part number TC-ENC-420-R and the 45-minute MTTR estimate from the manual.',
      result: 'Work Order 700093847 created · Activity type: Corrective Maintenance · Part TC-ENC-420-R reserved from stores · MTTR 45 min · IDoc PMSM01 0000000048293110 confirmed',
    },
    {
      sys: 'Teams',
      title: 'Share the Encoder Replacement Procedure with the On-Call Technician',
      desc: 'Post the relevant section of the Transfer Car Assembly Manual directly to the #maintenance-floor channel in Teams — so the on-call technician has the step-by-step procedure and torque specifications on their phone before they reach the machine.',
      result: 'Manual excerpt posted to #maintenance-floor · E-047 procedure · 5 steps · Torque spec: 2.5 Nm · Source: transfer_car_assembly_manual.pdf · Technician J. Torres notified',
    },
    {
      sys: 'Email',
      title: 'Email the Manual Query Summary to the Reliability Engineer',
      desc: 'Send an email to the reliability engineering team with today\'s manual queries and the fault codes that triggered them — so the team can review whether the underlying procedures need to be updated or if a design change is required to prevent recurring faults.',
      result: 'Email sent to reliability-eng@company.com · "Manual Query Report — FAL-ASM-01 — 07 May" · 3 fault codes queried · Procedure gap identified in E-047 steps · 2 recipients',
    },
  ],
};

// Action execution state: { tab_idx: 'idle' | 'running' | 'done' }
const _agentState = {};

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
  badge.textContent = TAB_LABELS[tab] || tab;

  const actions = AGENT_ACTIONS[tab] || [];
  const sysBadge = sys => {
    if (sys === 'SAP')   return '<span class="agent-sys-badge badge-sap">SAP</span>';
    if (sys === 'Teams') return '<span class="agent-sys-badge badge-teams">Teams</span>';
    if (sys === 'Email') return '<span class="agent-sys-badge badge-email">Email</span>';
    return '';
  };
  document.getElementById('agent-actions-list').innerHTML = actions.map((a, i) => {
    const key   = `${tab}_${i}`;
    const state = _agentState[key] || 'idle';
    return `
      <div class="agent-action-card" id="agent-card-${key}">
        <div class="agent-action-body">
          <div class="agent-action-header-row">
            ${sysBadge(a.sys)}
            <div class="agent-action-title">${a.title}</div>
          </div>
          <div class="agent-action-desc">${a.desc}</div>
          ${state === 'idle' ? `
            <button class="agent-approve-btn" onclick="runAgentAction('${tab}', ${i})">
              Approve &amp; Execute
            </button>` : ''}
          ${state === 'running' ? `
            <div class="agent-running">
              <div class="spinner sm"></div> Executing…
            </div>` : ''}
          ${state === 'done' ? `
            <div class="agent-result">
              <span class="agent-check">✓</span> ${a.result}
            </div>` : ''}
        </div>
      </div>`;
  }).join('');
}

async function runAgentAction(tab, idx) {
  const key = `${tab}_${idx}`;
  _agentState[key] = 'running';
  renderAgentPanel(tab);

  await new Promise(r => setTimeout(r, 2200));

  _agentState[key] = 'done';
  renderAgentPanel(tab);
}

// Auto-init grid on page load
document.addEventListener('DOMContentLoaded', initVisionGrid);

// ── Automotive Production Routes ───────────────────────────────────────────────
// All 3 lines converge at FAL-ASM-01 (Final Assembly) — shared downstream station.
// FAL-ASM-01 fault blocks all upstream lines simultaneously (WIP queues up at each).

const LINE_ROUTES = {
  A: [
    { id: 'BDY-STM-01', step: 'Stamping',     buffer: 0.25, ratePerHr: 38, unitValue: 1200 },
    { id: 'BDY-WLD-01', step: 'Robotic Weld', buffer: 0.50, ratePerHr: 34, unitValue: 1200 },
    { id: 'BDY-SLD-01', step: 'Sealing',      buffer: 0.25, ratePerHr: 36, unitValue: 1200 },
    { id: 'BDY-INS-01', step: 'Body Inspect', buffer: 0.25, ratePerHr: 38, unitValue: 1200 },
    { id: 'FAL-ASM-01', step: 'Final Asm',    buffer: 0.00, ratePerHr: 60, unitValue: 42000, shared: true },
  ],
  B: [
    { id: 'PNT-PRP-01', step: 'Phosphate',    buffer: 0.50, ratePerHr: 22, unitValue: 800 },
    { id: 'PNT-ECT-01', step: 'E-Coat',       buffer: 0.50, ratePerHr: 18, unitValue: 800 },
    { id: 'PNT-BSC-01', step: 'Base Coat',    buffer: 0.25, ratePerHr: 24, unitValue: 800 },
    { id: 'PNT-CLR-01', step: 'Clear Coat',   buffer: 0.25, ratePerHr: 20, unitValue: 800 },
    { id: 'PNT-INS-01', step: 'Paint Inspect',buffer: 0.25, ratePerHr: 28, unitValue: 800 },
    { id: 'FAL-ASM-01', step: 'Final Asm',    buffer: 0.00, ratePerHr: 60, unitValue: 42000, shared: true },
  ],
  C: [
    { id: 'PTN-MCH-01', step: 'Block Machine',buffer: 0.50, ratePerHr: 22, unitValue: 3200 },
    { id: 'PTN-HAD-01', step: 'Head Assembly',buffer: 0.25, ratePerHr: 28, unitValue: 3200 },
    { id: 'PTN-BLD-01', step: 'Engine Build', buffer: 0.25, ratePerHr: 14, unitValue: 3200 },
    { id: 'PTN-DYN-01', step: 'Dyno Test',    buffer: 0.50, ratePerHr: 11, unitValue: 3200 },
    { id: 'FAL-ASM-01', step: 'Final Asm',    buffer: 0.00, ratePerHr: 60, unitValue: 42000, shared: true },
  ],
};

// Flat lookup: machineId → route info
const ROUTE_BY_ID = {};
Object.entries(LINE_ROUTES).forEach(([line, steps]) => {
  steps.forEach((s, idx) => {
    ROUTE_BY_ID[s.id] = { ...s, line, idx };
  });
});

const LINE_COLORS = { A: '#FF8C00', B: '#4CC9F0', C: '#A78BFA', S: '#00DC82' };
const IMPACT_COLORS = {
  'Revenue Loss':  '#FF4444',
  'Delivery Risk': '#FF8C00',
  'WIP Queue':     '#FFD600',
  'SHIPPING':      '#4CC9F0',
};

function getNodeColor(nodeId) {
  if (IMPACT_COLORS[nodeId]) return IMPACT_COLORS[nodeId];
  const r = ROUTE_BY_ID[nodeId];
  return r ? LINE_COLORS[r.line] : '#888';
}

function initCalculator() {
  const slider   = document.getElementById('dt-slider');
  const numInput = document.getElementById('dt-hours');
  const sel      = document.getElementById('calc-machine-sel');
  if (!slider || !numInput || !sel) return;

  // Populate dropdown from routing table
  Object.entries(LINE_ROUTES).forEach(([line, steps]) => {
    const grp = document.createElement('optgroup');
    grp.label = `Line ${line} — ${line === 'A' ? 'Body Shop (VBA)' : line === 'B' ? 'Paint Shop (PBU)' : 'Powertrain (PTM)'}`;
    steps.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `${s.id}  —  ${s.step}`;
      if (s.id === calcMachineId) opt.selected = true;
      grp.appendChild(opt);
    });
    sel.appendChild(grp);
  });

  slider.addEventListener('input', () => {
    numInput.value = slider.value;
    calcHours = parseFloat(slider.value);
    updateCalculator();
  });

  numInput.addEventListener('change', () => {
    const v = Math.max(0.5, Math.min(24, parseFloat(numInput.value) || 0.5));
    numInput.value = v; slider.value = v; calcHours = v;
    updateCalculator();
  });

  sel.addEventListener('change', () => {
    calcMachineId = sel.value;
    updateCalculator();
  });

  updateCalculator();
}

function updateCalculator() {
  renderSankeyChart(calcHours, calcMachineId);
  renderImpactCards(calcHours, calcMachineId);
}

function buildMachineImpactLinks(hours, machineId) {
  const impactSplit = [
    { key: 'Revenue Loss',  pct: 0.58 },
    { key: 'Delivery Risk', pct: 0.27 },
    { key: 'WIP Queue',     pct: 0.15 },
  ];

  // ── Special case: FAL-ASM-01 is the shared final assembly ─────────────────
  // Its downtime starves ALL 3 upstream lines (WIP queues at each line's end).
  if (machineId === 'FAL-ASM-01') {
    // Update Sankey column labels to reflect upstream blocking
    const labels = document.querySelectorAll('.calc-sankey-labels span');
    if (labels[1]) labels[1].textContent = 'Upstream Lines Blocked';
    if (labels[0]) labels[0].textContent = 'Faulted Station';

    const blocked = [];
    Object.entries(LINE_ROUTES).forEach(([line, steps]) => {
      const lastBefore = steps[steps.length - 2]; // step just before FAL-ASM-01
      if (lastBefore && !lastBefore.shared) {
        blocked.push({ ...lastBefore, impactHours: hours * 0.82, line });
      }
    });

    const links = [];
    blocked.forEach(d => {
      links.push({ from: machineId, to: d.id, value: d.impactHours });
      impactSplit.forEach(({ key, pct }) => {
        links.push({ from: d.id, to: key, value: d.impactHours * pct });
      });
    });

    const levels = { [machineId]: 0 };
    blocked.forEach(d => { levels[d.id] = 1; });
    impactSplit.forEach(({ key }) => { levels[key] = 2; });

    return {
      links, levels, downstream: blocked,
      src: { id: machineId, step: 'Final Asm', line: 'S', ratePerHr: 60, unitValue: 42000, idx: 4 },
    };
  }

  // ── Normal case: downstream cascade within the line ────────────────────────
  // Restore default column labels
  const labels = document.querySelectorAll('.calc-sankey-labels span');
  if (labels[1]) labels[1].textContent = 'Downstream Starved';
  if (labels[0]) labels[0].textContent = 'Faulted Machine';

  const src = ROUTE_BY_ID[machineId];
  if (!src) return { links: [], levels: {}, downstream: [], src: null };

  const steps = LINE_ROUTES[src.line];
  const myIdx = src.idx;

  const downstream = [];
  let remaining = hours;
  for (let i = myIdx + 1; i < steps.length && i <= myIdx + 3; i++) {
    const s = steps[i];
    // Skip the shared step (FAL-ASM-01) if it's the very next step and this line ends here
    const impact = Math.max(0, remaining - s.buffer);
    if (impact < 0.05) break;
    downstream.push({ ...s, impactHours: impact });
    remaining = impact * 0.75;
  }

  if (!downstream.length) {
    downstream.push({
      id: 'FAL-ASM-01', step: 'Final Assembly',
      impactHours: hours * 0.85,
      ratePerHr: 60, unitValue: 42000,
    });
  }

  const links = [];
  downstream.forEach(d => {
    links.push({ from: machineId, to: d.id, value: d.impactHours });
    impactSplit.forEach(({ key, pct }) => {
      links.push({ from: d.id, to: key, value: d.impactHours * pct });
    });
  });

  const levels = {};
  levels[machineId] = 0;
  downstream.forEach(d => { levels[d.id] = 1; });
  impactSplit.forEach(({ key }) => { levels[key] = 2; });

  return { links, levels, downstream, src };
}

function renderSankeyChart(hours, machineId) {
  const wrap = document.getElementById('sankey-wrap');
  if (!wrap) return;

  const { links, levels } = buildMachineImpactLinks(hours, machineId);
  if (!links.length) { wrap.innerHTML = ''; return; }

  const W      = Math.max(wrap.clientWidth || 600, 400);
  const H      = 280;
  const PAD_Y  = 18;
  const GAP_Y  = 8;
  const NODE_W = 10;
  const colX   = [Math.round(W * 0.05), Math.round(W * 0.42), Math.round(W * 0.80)];

  // Node value aggregation
  const nodeOut = {}, nodeIn = {};
  links.forEach(lk => {
    nodeOut[lk.from] = (nodeOut[lk.from] || 0) + lk.value;
    nodeIn[lk.to]    = (nodeIn[lk.to]    || 0) + lk.value;
  });
  const allNodes = new Set([...links.map(l => l.from), ...links.map(l => l.to)]);
  const nodeVal  = {};
  allNodes.forEach(n => { nodeVal[n] = Math.max(nodeOut[n] || 0, nodeIn[n] || 0); });

  // Group by level
  const byLevel = [[], [], []];
  allNodes.forEach(n => {
    const lvl = levels[n];
    if (lvl !== undefined) byLevel[lvl].push(n);
  });
  byLevel.forEach(ns => ns.sort((a, b) => (nodeVal[b] || 0) - (nodeVal[a] || 0)));

  // Layout: y + height per node
  const nodeY = {}, nodeH = {};
  byLevel.forEach((nodes, lvl) => {
    if (!nodes.length) return;
    const totalVal = nodes.reduce((s, n) => s + (nodeVal[n] || 0), 0) || 1;
    const gapSpace = GAP_Y * (nodes.length - 1);
    const drawH    = H - PAD_Y * 2 - gapSpace;
    let y = PAD_Y;
    nodes.forEach(n => {
      const h = Math.max(6, (nodeVal[n] / totalVal) * drawH);
      nodeH[n] = h; nodeY[n] = y; y += h + GAP_Y;
    });
  });

  const srcOff = {}, tgtOff = {};
  allNodes.forEach(n => { srcOff[n] = 0; tgtOff[n] = 0; });
  let pathsSVG = '', rectsSVG = '', textsSVG = '';

  links.forEach(lk => {
    if (levels[lk.from] === undefined || levels[lk.to] === undefined) return;
    if (!nodeH[lk.from] || !nodeH[lk.to]) return;

    const sx = colX[levels[lk.from]] + NODE_W;
    const tx = colX[levels[lk.to]];
    const sh = (lk.value / (nodeOut[lk.from] || 1)) * nodeH[lk.from];
    const th = (lk.value / (nodeIn[lk.to]    || 1)) * nodeH[lk.to];
    const sy1 = nodeY[lk.from] + srcOff[lk.from];
    const ty1 = nodeY[lk.to]   + tgtOff[lk.to];
    const mx  = (sx + tx) / 2;
    const col = getNodeColor(lk.from);

    pathsSVG += `<path d="M${f(sx)},${f(sy1)} C${f(mx)},${f(sy1)} ${f(mx)},${f(ty1)} ${f(tx)},${f(ty1)} L${f(tx)},${f(ty1+th)} C${f(mx)},${f(ty1+th)} ${f(mx)},${f(sy1+sh)} ${f(sx)},${f(sy1+sh)}Z" fill="${col}" fill-opacity="0.22"/>`;
    srcOff[lk.from] += sh;
    tgtOff[lk.to]   += th;
  });

  allNodes.forEach(n => {
    const lvl = levels[n];
    if (lvl === undefined || !nodeH[n]) return;
    const x   = colX[lvl];
    const y   = nodeY[n];
    const h   = nodeH[n];
    const col = getNodeColor(n);
    const val = nodeVal[n];
    const r   = ROUTE_BY_ID[n];
    const label = r ? r.step : (n === 'SHIPPING' ? 'Shipping/FGI' : n);

    rectsSVG += `<rect x="${x}" y="${f(y)}" width="${NODE_W}" height="${f(h)}" rx="2" fill="${col}"/>`;

    if (lvl < 2) {
      const lx = x + NODE_W + 7;
      textsSVG += `<text x="${lx}" y="${f(y + h/2 - 5)}" fill="#999" font-size="10" dominant-baseline="middle" font-family="system-ui,sans-serif">${label}</text>`;
      textsSVG += `<text x="${lx}" y="${f(y + h/2 + 7)}" fill="${col}" font-size="9" font-weight="700" dominant-baseline="middle" font-family="system-ui,sans-serif">${val.toFixed(1)}h</text>`;
    } else {
      const lx = x - 7;
      textsSVG += `<text x="${lx}" y="${f(y + h/2 - 5)}" fill="#999" font-size="10" dominant-baseline="middle" text-anchor="end" font-family="system-ui,sans-serif">${label}</text>`;
      textsSVG += `<text x="${lx}" y="${f(y + h/2 + 7)}" fill="${col}" font-size="9" font-weight="700" dominant-baseline="middle" text-anchor="end" font-family="system-ui,sans-serif">${val.toFixed(1)}h</text>`;
    }
  });

  wrap.innerHTML = `<svg width="100%" height="${H}" viewBox="0 0 ${W} ${H}" style="overflow:visible">${pathsSVG}${rectsSVG}${textsSVG}</svg>`;
}

function f(n) { return n.toFixed(1); }

function renderImpactCards(hours, machineId) {
  const el = document.getElementById('calc-impact-cards');
  if (!el) return;

  const { downstream, src } = buildMachineImpactLinks(hours, machineId);
  if (!src) { el.innerHTML = ''; return; }

  const lineColor = LINE_COLORS[src.line] || '#888';
  const unitsLost = Math.round(
    downstream.reduce((s, d) => s + d.impactHours * (d.ratePerHr || src.ratePerHr), 0)
  );
  const revLost   = unitsLost * src.unitValue;

  const totalImpact  = downstream.reduce((s, d) => s + d.impactHours, 0);
  const oeeHit       = Math.min(35, +(hours / 8 * 58).toFixed(1));
  const delivRisk    = totalImpact > 6 ? 'HIGH' : totalImpact > 3 ? 'MEDIUM' : 'LOW';
  const riskCls      = delivRisk === 'HIGH' ? 'red' : delivRisk === 'MEDIUM' ? 'yellow' : 'green';
  const riskNote     = delivRisk === 'HIGH'   ? 'SLA breach likely'
                     : delivRisk === 'MEDIUM' ? 'monitor closely'
                     : 'within schedule buffer';

  el.innerHTML = `
    <div class="calc-impact-card impact-primary">
      <div class="cic-label">UNITS LOST</div>
      <div class="cic-val red">${unitsLost.toLocaleString()}</div>
      <div class="cic-sub">${downstream.length} downstream machines starved</div>
    </div>
    <div class="calc-impact-card">
      <div class="cic-label">REVENUE IMPACT</div>
      <div class="cic-val red">$${(revLost / 1000).toFixed(0)}K</div>
      <div class="cic-sub">at $${src.unitValue}/unit standard</div>
    </div>
    <div class="calc-impact-card">
      <div class="cic-label">OEE HIT</div>
      <div class="cic-val yellow">−${oeeHit}%</div>
      <div class="cic-sub">shift availability loss</div>
    </div>
    <div class="calc-impact-card">
      <div class="cic-label">DELIVERY RISK</div>
      <div class="cic-val ${riskCls}">${delivRisk}</div>
      <div class="cic-sub">${riskNote}</div>
    </div>
    ${downstream.map(d => `
      <div class="calc-impact-card" style="border-color:${lineColor}22;">
        <div class="cic-label">${d.id} · ${d.step}</div>
        <div class="cic-val" style="color:${lineColor};font-size:15px;">${d.impactHours.toFixed(1)}h starved</div>
        <div class="cic-sub">${Math.round(d.impactHours * (d.ratePerHr || src.ratePerHr))} units lost</div>
      </div>
    `).join('')}
  `;
}


// ── Ask SHIFT ─────────────────────────────────────────────────────────────────
function setShiftQ(btn) {
  document.getElementById('shift-input').value = btn.textContent;
  document.getElementById('shift-input').focus();
}

async function submitShift() {
  const input = document.getElementById('shift-input');
  const q     = input.value.trim();
  if (!q) return;

  const btn = document.getElementById('shift-btn');
  btn.disabled = true;
  input.value  = '';

  document.getElementById('shift-starters').classList.add('hidden');
  const thread = document.getElementById('shift-thread');
  thread.classList.remove('hidden');

  appendMsg(thread, 'user', q);

  const loading = document.getElementById('shift-loading');
  loading.style.display = 'flex';
  loading.classList.remove('hidden');
  document.querySelector('.shift-chat-body').scrollTop = 99999;

  const payload = { question: q };
  if (shiftConvId) payload.conversation_id = shiftConvId;

  const data = await fetch('/manufacturing/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json()).catch(() => ({ answer: 'Error — please retry.', source: 'error' }));

  loading.classList.add('hidden');
  loading.style.display = 'none';

  if (data.conversation_id) shiftConvId = data.conversation_id;

  const msgEl = appendMsg(thread, 'ai', data.answer, null, data.follow_ups || []);

  // Agentic recommendations
  fetch('/manufacturing/api/actions/suggest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q, answer: data.answer }),
  })
    .then(r => r.json())
    .then(actions => { if (actions.length) appendMfgActionPanel(msgEl, actions); })
    .catch(() => {});

  btn.disabled = false;
  document.querySelector('.shift-chat-body').scrollTop = 99999;
}

function appendMsg(thread, role, content, source, followUps) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const av = document.createElement('div');
  av.className   = 'msg-avatar';
  av.textContent = role === 'user' ? 'ME' : 'AI';

  const wrap = document.createElement('div');

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = role === 'ai' ? marked.parse(content) : esc(content);
  wrap.appendChild(bubble);

  if (source) {
    const s = document.createElement('div');
    s.className   = 'msg-source';
    s.textContent = source;
    wrap.appendChild(s);
  }

  if (followUps && followUps.length) {
    const panel = document.createElement('div');
    panel.className = 'fup-panel';
    const hdr = document.createElement('div');
    hdr.className = 'fup-panel-header';
    hdr.innerHTML = `Suggested Questions`;
    panel.appendChild(hdr);
    const cards = document.createElement('div');
    cards.className = 'fup-cards';
    followUps.forEach(fu => {
      const card = document.createElement('div');
      card.className = 'fup-card';
      card.innerHTML = `<div class="fup-card-text">${esc(fu)}</div><button class="fup-ask-btn">Ask →</button>`;
      card.querySelector('.fup-ask-btn').onclick = () => {
        document.getElementById('shift-input').value = fu;
        submitShift();
      };
      cards.appendChild(card);
    });
    panel.appendChild(cards);
    wrap.appendChild(panel);
  }

  div.appendChild(av);
  div.appendChild(wrap);
  thread.appendChild(div);
  return wrap;
}

function appendMfgActionPanel(wrapEl, actions) {
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
    card.id = `mfg-action-card-${a.id}`;
    const impact = a.impact_usd > 0 ? `$${(a.impact_usd/1000).toFixed(0)}K impact` : 'Process improvement';
    card.innerHTML = `
      <div class="action-priority-dot ${a.priority}"></div>
      <div class="action-card-body">
        <div class="action-card-title">${a.label}</div>
        <div class="action-card-desc">${a.description}</div>
        <div class="action-card-meta"><span class="action-impact">${impact}</span> · <span>${a.owner}</span> · <span>${a.entity_name}</span></div>
        <div class="action-btns">
          <button class="action-approve-btn" onclick="executeMfgAction('${a.id}','approved',this)">Take Action</button>
          <button class="action-dismiss-btn" onclick="executeMfgAction('${a.id}','dismissed',this)">Dismiss</button>
        </div>
      </div>`;
    cards.appendChild(card);
  });
  panel.appendChild(cards);
  wrapEl.appendChild(panel);
  document.querySelector('.shift-chat-body').scrollTop = 99999;
}

async function executeMfgAction(actionId, outcome, btn) {
  try {
    btn.disabled = true;
    const card = document.getElementById(`mfg-action-card-${actionId}`);
    await fetch('/manufacturing/api/actions/execute', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: actionId, outcome }),
    });
    if (card) card.style.opacity = '0.45';
    btn.closest('.action-btns').innerHTML = outcome === 'approved'
      ? '<span style="color:#10b981;font-size:11px;font-weight:600">✓ Action taken</span>'
      : '<span style="color:#6b7280;font-size:11px">Dismissed</span>';
  } catch (_) { btn.disabled = false; }
}

// ── Equipment Manuals Tab ────────────────────────────────────────────────────

const MANUALS_LIBRARY = [
  { id: 'fanuc',      title: 'FANUC R-2000iC Welding Robot',       file: 'fanuc_r2000ic_welding_robot_manual.pdf',       tag: 'Body Shop' },
  { id: 'ecoat',      title: 'E-Coat Electrocoat System',           file: 'e_coat_system_manual.pdf',                     tag: 'Paint Shop' },
  { id: 'stamping',   title: '800T Stamping Press',                 file: '800t_stamping_press_manual.pdf',               tag: 'Body Shop' },
  { id: 'transfer',   title: 'Transfer Car Assembly (FAL-ASM-01)',  file: 'transfer_car_assembly_manual.pdf',             tag: 'Final Assembly' },
  { id: 'cnc',        title: 'CNC Machining Centre',                file: 'cnc_machining_centre_manual.pdf',              tag: 'Powertrain' },
  { id: 'sealing',    title: 'Body Sealing System',                 file: 'body_sealing_system_manual.pdf',               tag: 'Body Shop' },
  { id: 'basecoat',   title: 'Base Coat Robot System',              file: 'base_coat_robot_manual.pdf',                   tag: 'Paint Shop' },
  { id: 'dyno',       title: 'Engine Dynamometer',                  file: 'engine_dynamometer_manual.pdf',                tag: 'Powertrain' },
  { id: 'conveyor',   title: 'Chain Conveyor System',               file: 'chain_conveyor_manual.pdf',                    tag: 'Final Assembly' },
  { id: 'vision',     title: 'Vision Inspection System',            file: 'vision_inspection_system_manual.pdf',          tag: 'Quality' },
];

function renderManualsLibrary() {
  const grid = document.getElementById('manuals-card-grid');
  if (!grid) return;
  grid.innerHTML = MANUALS_LIBRARY.map(m => `
    <div class="manuals-lib-card" onclick="setManualsManual('${m.title}')">
      <div class="manuals-lib-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
        </svg>
      </div>
      <div class="manuals-lib-info">
        <div class="manuals-lib-title">${m.title}</div>
        <div class="manuals-lib-tag">${m.tag}</div>
      </div>
    </div>
  `).join('');
}

function setManualsManual(title) {
  const inp = document.getElementById('manuals-input');
  if (inp) {
    inp.value = `Tell me about the ${title} — what are the key maintenance procedures and common fault codes?`;
    inp.focus();
  }
}

function setManualsQ(btn) {
  const inp = document.getElementById('manuals-input');
  if (inp) {
    inp.value = btn.textContent;
    inp.focus();
  }
}

let _manualsActive = false;

async function submitManuals() {
  const inp = document.getElementById('manuals-input');
  const question = inp ? inp.value.trim() : '';
  if (!question || _manualsActive) return;

  _manualsActive = true;
  const btn = document.getElementById('manuals-btn');
  if (btn) btn.disabled = true;

  // Hide starters, show thread
  const starters = document.getElementById('manuals-starters');
  if (starters) starters.classList.add('hidden');
  const thread = document.getElementById('manuals-thread');
  if (thread) thread.classList.remove('hidden');

  // Append user message
  appendManualsMessage('user', question);
  if (inp) inp.value = '';

  // Show loading
  const loading = document.getElementById('manuals-loading');
  if (loading) { loading.classList.remove('hidden'); loading.style.display = 'flex'; }

  try {
    const res = await fetch('/manufacturing/api/manuals-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();

    if (loading) { loading.classList.add('hidden'); loading.style.display = 'none'; }

    if (data.error) {
      appendManualsMessage('ai', `Sorry, an error occurred: ${data.error}`);
    } else {
      const sources = (data.sources || []).map(s =>
        `<span class="manuals-source-chip">${s}</span>`
      ).join('');
      const sourceBlock = sources
        ? `<div class="manuals-sources"><span class="manuals-sources-label">Sources:</span> ${sources}</div>`
        : '';
      appendManualsMessage('ai', data.answer, sourceBlock);
    }
  } catch (e) {
    if (loading) { loading.classList.add('hidden'); loading.style.display = 'none'; }
    appendManualsMessage('ai', 'Network error — please try again.');
  }

  _manualsActive = false;
  if (btn) btn.disabled = false;

  // Scroll thread to bottom
  const chatBody = document.getElementById('manuals-chat-body');
  if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
}

function appendManualsMessage(role, content, extraHtml = '') {
  const thread = document.getElementById('manuals-thread');
  if (!thread) return;

  const div = document.createElement('div');
  div.className = `manuals-msg manuals-msg-${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'manuals-avatar';
  if (role === 'ai') {
    avatar.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M12 2C12 7.8 7.8 12 2 12C7.8 12 12 16.2 12 22C12 16.2 16.2 12 22 12C16.2 12 12 7.8 12 2Z"/></svg>`;
  } else {
    avatar.textContent = 'ME';
  }

  const bubble = document.createElement('div');
  bubble.className = 'manuals-bubble';
  if (role === 'ai' && typeof marked !== 'undefined') {
    bubble.innerHTML = marked.parse(content) + extraHtml;
  } else {
    bubble.textContent = content;
    if (extraHtml) bubble.insertAdjacentHTML('beforeend', extraHtml);
  }

  div.appendChild(avatar);
  div.appendChild(bubble);
  thread.appendChild(div);
}

// Keyboard shortcut for manuals textarea
document.addEventListener('keydown', function(e) {
  const inp = document.getElementById('manuals-input');
  if (inp && document.activeElement === inp && (e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    submitManuals();
  }
});

// Init manuals library on load
document.addEventListener('DOMContentLoaded', function() {
  renderManualsLibrary();
});

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Interactive ML Features ────────────────────────────────────────────────

function _mlRunnerStart(btnId, thinkingId, steps, stepId, doneCallback) {
  const btn = document.getElementById(btnId);
  const thinking = document.getElementById(thinkingId);
  const stepEl = document.getElementById(stepId);
  if (!btn || !thinking) return;
  btn.disabled = true;
  thinking.style.display = 'flex';
  let i = 0;
  const iv = setInterval(() => {
    i++;
    if (i < steps.length && stepEl) stepEl.textContent = steps[i];
  }, 900);
  setTimeout(() => {
    clearInterval(iv);
    thinking.style.display = 'none';
    btn.disabled = false;
    doneCallback();
  }, steps.length * 900 + 500);
}

function _renderFeatureBars(containerId, features, accentColor) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.classList.add('visible');
  el.innerHTML = `<div class="feature-importance-title">Root Cause Feature Importance</div>` +
    features.map(f => `
      <div class="feature-row">
        <div class="feature-label">${f.label}</div>
        <div class="feature-bar-wrap">
          <div class="feature-bar" id="fb-${f.label.replace(/\s+/g,'')}" style="background:${accentColor || '#10b981'};"></div>
        </div>
        <div class="feature-pct">${f.pct}%</div>
      </div>`).join('');
  requestAnimationFrame(() => {
    features.forEach(f => {
      const bar = document.getElementById(`fb-${f.label.replace(/\s+/g,'')}`);
      if (bar) bar.style.width = f.pct + '%';
    });
  });
}

// ── OEE Root Cause Analysis ────────────────────────────────────────────────
function filterOeeLine(line) {
  // Highlight active line on chart if desired — update KPI cards for that line
  const labels = { all: 'all lines', A: 'Line A — Body Shop', B: 'Line B — Paint Shop', C: 'Line C — Powertrain' };
  const lineEl = document.getElementById('oee-rca-results');
  if (lineEl) { lineEl.classList.remove('visible'); lineEl.innerHTML = ''; }
}

function runOeeRootCause() {
  const line = document.getElementById('oee-line-filter')?.value || 'all';
  const lineLabel = { all: 'all lines', A: 'Line A', B: 'Line B', C: 'Line C' }[line] || 'all lines';
  const steps = [
    'Loading sensor telemetry from machine_sensor_history…',
    `Aggregating Availability, Performance, Quality losses for ${lineLabel}…`,
    'Running GradientBoosting root cause classifier (9 features)…',
    'Ranking loss contributors by feature importance…',
    'Generating corrective action recommendations…',
  ];
  _mlRunnerStart('oee-rca-btn', 'oee-rca-thinking', steps, 'oee-rca-step', () => {
    const features = line === 'A'
      ? [{label:'Changeover Time',pct:34},{label:'Minor Stoppages',pct:27},{label:'Speed Reduction',pct:18},{label:'Scrap / Rework',pct:13},{label:'Planned Downtime',pct:8}]
      : line === 'B'
      ? [{label:'Equipment Fault',pct:41},{label:'Material Delay',pct:22},{label:'Speed Reduction',pct:16},{label:'Operator Wait',pct:12},{label:'Quality Hold',pct:9}]
      : line === 'C'
      ? [{label:'Vibration Anomaly',pct:38},{label:'Thermal Drift',pct:24},{label:'Cycle Time Creep',pct:19},{label:'Scrap / Rework',pct:11},{label:'Idle Starvation',pct:8}]
      : [{label:'Changeover Time',pct:31},{label:'Equipment Fault',pct:26},{label:'Speed Reduction',pct:20},{label:'Material Delay',pct:14},{label:'Quality Hold',pct:9}];
    const oeeGap = line === 'A' ? 4.2 : line === 'B' ? 6.8 : line === 'C' ? 3.1 : 4.9;
    const topCause = features[0].label;
    const narratives = {
      A: `<strong style="color:#f59e0b">${features[0].label}</strong> is driving ${features[0].pct}% of Line A losses — excessive changeover cycles are reducing available production time. Combined with <strong style="color:#e5e7eb">${features[1].label}</strong> (${features[1].pct}%), these two factors alone account for ${features[0].pct + features[1].pct}% of the OEE gap. <strong style="color:#10b981">Recommendation:</strong> Implement SMED methodology to cut changeover time by 40% and add jidoka sensors to auto-flag minor stoppages before they cascade. Estimated OEE recovery: <strong>+${(oeeGap*0.6).toFixed(1)}%</strong>.`,
      B: `<strong style="color:#f59e0b">${features[0].label}</strong> is the dominant loss driver on Line B (${features[0].pct}% contribution), with root sensors indicating bearing wear on PNT-ECT-01 and PNT-BSC-01. <strong style="color:#10b981">Recommendation:</strong> Initiate a predictive maintenance work order for both paint shop conveyors within the next 8 hours to avoid unplanned stoppage. Address <strong style="color:#e5e7eb">${features[1].label}</strong> by pre-staging material kits at the E-coat station. Estimated OEE recovery: <strong>+${(oeeGap*0.6).toFixed(1)}%</strong>.`,
      C: `<strong style="color:#f59e0b">${features[0].label}</strong> detected on PTN-MCH-01 spindle assembly — vibration signature exceeds 4.2 mm/s RMS threshold. This is causing cycle time drift downstream. <strong style="color:#10b981">Recommendation:</strong> Schedule spindle re-balancing within the next 4 hours. Apply thermal drift correction via PID tuning on PTN-HAD-01 to address the ${features[1].pct}% thermal contribution. Estimated OEE recovery: <strong>+${(oeeGap*0.6).toFixed(1)}%</strong>.`,
      all: `Across all three lines, <strong style="color:#f59e0b">${features[0].label}</strong> (${features[0].pct}%) and <strong style="color:#e5e7eb">${features[1].label}</strong> (${features[1].pct}%) are the top two loss drivers, contributing a combined ${features[0].pct + features[1].pct}% of the plant-wide OEE gap. <strong style="color:#10b981">Recommendation:</strong> Deploy cross-line SMED program for changeovers, schedule preventive maintenance for fault-prone machines on Lines B and C, and establish 4-hour material staging cadence on Line B. Targeting a plant OEE recovery of <strong>+${(oeeGap*0.6).toFixed(1)}%</strong>.`,
    };
    const narrative = narratives[line] || narratives.all;
    const resultsEl = document.getElementById('oee-rca-results');
    resultsEl.innerHTML = `
      <div class="ml-result-summary">
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">OEE Gap vs Target</div><div class="ml-result-kpi-val" style="color:#ef4444">−${oeeGap}%</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Top Loss Driver</div><div class="ml-result-kpi-val" style="font-size:13px;color:#f59e0b">${topCause}</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Addressable OEE Gain</div><div class="ml-result-kpi-val" style="color:#10b981">+${(oeeGap*0.6).toFixed(1)}%</div></div>
      </div>
      <div id="oee-feature-bars"></div>
      <div style="font-size:12px;color:#9ca3af;line-height:1.7;margin:12px 0 14px;padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:8px;border-left:3px solid rgba(16,185,129,0.4);">${narrative}</div>
      <div class="ml-divider"></div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6b7280;margin-bottom:8px;">Agentic Actions</div>
      <div class="ml-action-chips">
        <button class="ml-action-chip green" onclick="this.textContent='✓ Scheduled';this.disabled=true;">Schedule Maintenance Window</button>
        <button class="ml-action-chip amber" onclick="this.textContent='✓ Notified';this.disabled=true;">Alert Production Supervisor</button>
        <button class="ml-action-chip blue" onclick="this.textContent='✓ Created';this.disabled=true;">Create SAP Work Order</button>
        <button class="ml-action-chip amber" onclick="this.textContent='✓ Sent';this.disabled=true;">Post to Teams Channel</button>
      </div>`;
    resultsEl.classList.add('visible');
    _renderFeatureBars('oee-feature-bars', features, '#10b981');
  });
}

// ── Quality Root Cause Analysis ────────────────────────────────────────────
function runQualityRootCause() {
  const line = document.getElementById('qual-line-filter')?.value || 'all';
  const defect = document.getElementById('qual-defect-filter')?.value || 'all';
  const defectLabel = { all:'all defects', scratch:'Surface Scratches', dent:'Dents', weld:'Weld Porosity', paint:'Paint Adhesion', dim:'Dimensional Variance' }[defect];
  const steps = [
    `Scanning defect records for ${defectLabel} from quality_gold…`,
    'Running Isolation Forest anomaly detection on process parameters…',
    'Correlating defect timestamps with upstream machine events…',
    'Ranking root cause contributors with causal ML model…',
    'Estimating scrap reduction potential and corrective actions…',
  ];
  _mlRunnerStart('qual-rca-btn', 'qual-rca-thinking', steps, 'qual-rca-step', () => {
    const features = defect === 'paint'
      ? [{label:'Oven Temp Variance',pct:44},{label:'Humidity Spike',pct:28},{label:'Conveyor Speed',pct:15},{label:'Primer Coverage',pct:8},{label:'Material Batch',pct:5}]
      : defect === 'weld'
      ? [{label:'Wire Feed Inconsistency',pct:38},{label:'Shielding Gas Pressure',pct:26},{label:'Gap Tolerance Drift',pct:19},{label:'Electrode Wear',pct:10},{label:'Cycle Time Variance',pct:7}]
      : [{label:'Stamping Force Variance',pct:36},{label:'Tool Wear Index',pct:28},{label:'Material Hardness Lot',pct:18},{label:'Die Temp Drift',pct:11},{label:'Lubrication Coverage',pct:7}];
    const scrapReduction = (Math.random()*1.2+0.8).toFixed(1);
    const defectNarratives = {
      paint: `<strong style="color:#f59e0b">${features[0].label}</strong> (${features[0].pct}% contribution) is the leading cause of paint adhesion failures — oven zone 3 is cycling ±8°C outside spec, degrading E-coat cross-link density. <strong style="color:#10b981">Recommendation:</strong> Recalibrate oven zone 3 PID controller and reduce conveyor dwell time by 12 seconds. Address <strong style="color:#e5e7eb">${features[1].label}</strong> by enabling humidity compensation in the pre-treatment wash stage. Expected scrap reduction: <strong>−${scrapReduction}%</strong>.`,
      weld: `<strong style="color:#f59e0b">${features[0].label}</strong> (${features[0].pct}%) is causing porosity in BDY-WLD-01 welds — wire spool tension is drifting 15% above nominal during high-speed cycles. <strong style="color:#10b981">Recommendation:</strong> Replace wire feeder drive rolls on BDY-WLD-01 and re-qualify shielding gas flow rate at 18 L/min. Inspect electrode tips on all Body Shop welders — current wear index exceeds 0.72. Expected scrap reduction: <strong>−${scrapReduction}%</strong>.`,
      scratch: `<strong style="color:#f59e0b">${features[0].label}</strong> (${features[0].pct}%) is the primary driver of surface scratch defects — stamping force variation on BDY-STM-01 is exceeding ±3.5 kN tolerance. <strong style="color:#10b981">Recommendation:</strong> Re-calibrate press force control on BDY-STM-01 and perform die surface inspection. Review material hardness certificates from current lot — Lot #HRC-2847 shows 4-point hardness variance outside spec. Expected scrap reduction: <strong>−${scrapReduction}%</strong>.`,
      all: `The causal model traced ${line === 'all' ? 847 : 312} defect events to three primary upstream factors. <strong style="color:#f59e0b">${features[0].label}</strong> (${features[0].pct}%) and <strong style="color:#e5e7eb">${features[1].label}</strong> (${features[1].pct}%) together explain ${features[0].pct + features[1].pct}% of all quality escapes this shift. <strong style="color:#10b981">Recommendation:</strong> Prioritize process parameter correction on the top-flagged machines, schedule tool and fixture inspection before next shift, and log a MES quality event to trigger a root-cause 8D report. Expected scrap reduction: <strong>−${scrapReduction}%</strong>.`,
    };
    const narrative = defectNarratives[defect] || defectNarratives.all;
    const resultsEl = document.getElementById('qual-rca-results');
    resultsEl.innerHTML = `
      <div class="ml-result-summary">
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Defects Analyzed</div><div class="ml-result-kpi-val">${line === 'all' ? 847 : 312}</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Root Causes Identified</div><div class="ml-result-kpi-val" style="color:#10b981">3</div></div>
        <div class="ml-result-kpi"><div class="ml-result-kpi-label">Est. Scrap Reduction</div><div class="ml-result-kpi-val" style="color:#10b981">−${scrapReduction}%</div></div>
      </div>
      <div id="qual-feature-bars"></div>
      <div style="font-size:12px;color:#9ca3af;line-height:1.7;margin:12px 0 14px;padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:8px;border-left:3px solid rgba(16,185,129,0.4);">${narrative}</div>
      <div class="ml-divider"></div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#6b7280;margin-bottom:8px;">Recommended Actions</div>
      <div class="ml-action-chips">
        <button class="ml-action-chip green" onclick="this.textContent='✓ Adjusted';this.disabled=true;">Adjust Process Parameters</button>
        <button class="ml-action-chip amber" onclick="this.textContent='✓ Scheduled';this.disabled=true;">Schedule Tool Inspection</button>
        <button class="ml-action-chip blue" onclick="this.textContent='✓ Logged';this.disabled=true;">Log Quality Event in MES</button>
        <button class="ml-action-chip amber" onclick="this.textContent='✓ Filed';this.disabled=true;">Open 8D Report in MES</button>
      </div>`;
    resultsEl.classList.add('visible');
    _renderFeatureBars('qual-feature-bars', features, '#10b981');
  });
}

// ── Onboarding Tutorial ────────────────────────────────────────────────────────
let _tutSlide = 0;
const _TUT_TOTAL = 2;

function openTutorial() {
  _tutSlide = 0;
  _updateTut();
  const ov = document.getElementById('tut-overlay');
  ov.style.display = 'flex';
}

function dismissTutorial() {
  document.getElementById('tut-overlay').style.display = 'none';
  localStorage.setItem('mfg-tutorial-seen', '1');
}

function tutNext() {
  if (_tutSlide < _TUT_TOTAL - 1) {
    document.getElementById(`tslide-${_tutSlide}`).style.display = 'none';
    _tutSlide++;
    document.getElementById(`tslide-${_tutSlide}`).style.display = 'block';
    _updateTut();
  } else {
    dismissTutorial();
  }
}

function _updateTut() {
  const btn = document.getElementById('tut-next-btn');
  if (btn) btn.style.display = _tutSlide === _TUT_TOTAL - 1 ? 'none' : '';
}

// Show tutorial on first visit after login
document.addEventListener('DOMContentLoaded', () => {
  if (!localStorage.getItem('mfg-tutorial-seen')) {
    setTimeout(openTutorial, 800);
  }
});
