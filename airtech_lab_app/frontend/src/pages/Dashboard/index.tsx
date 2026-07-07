import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

// ── Types ──────────────────────────────────────────────────────────────────────
interface Totals {
  total: number
  passed: number
  failed: number
  pass_rate: number
  avg_rows: number
  distinct_products: number
}
interface ProductRow   { product: string;   total: number; passed: number; failed: number; pass_rate: number }
interface MachinistRow { machinist: string; total: number; passed: number; failed: number; pass_rate: number }
interface OpRow        { operation: string; total: number; failed: number }
interface TrendDay     { day: string;       total: number; passed: number; failed: number }

interface DashData {
  totals:       Totals
  by_product:   ProductRow[]
  by_machinist: MachinistRow[]
  by_operation: OpRow[]
  trend:        TrendDay[]
}

interface RunProcRow { procedure_id: number; procedure_name: string; product_type: string; total: number; passed: number; failed: number; pass_rate: number }
interface RunSummary { totals: { total: number; passed: number; failed: number; pass_rate: number }; by_product: RunProcRow[] }

// ── Helpers ────────────────────────────────────────────────────────────────────
function rateColor(r: number) {
  if (r >= 90) return 'text-green-700'
  if (r >= 75) return 'text-amber-600'
  return 'text-red-600'
}
function rateBg(r: number) {
  if (r >= 90) return 'bg-green-500'
  if (r >= 75) return 'bg-amber-400'
  return 'bg-red-400'
}

// ── KPI Card ───────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, accent, onClick }: {
  label: string; value: string | number; sub?: string
  accent: 'blue' | 'green' | 'amber' | 'red' | 'purple'
  onClick?: () => void
}) {
  const bg:  Record<string, string> = { blue:'bg-blue-50 border-blue-200', green:'bg-green-50 border-green-200', amber:'bg-amber-50 border-amber-200', red:'bg-red-50 border-red-200', purple:'bg-purple-50 border-purple-200' }
  const val: Record<string, string> = { blue:'text-blue-800', green:'text-green-700', amber:'text-amber-700', red:'text-red-700', purple:'text-purple-800' }
  return (
    <div
      className={`rounded-xl border p-4 ${bg[accent]} ${onClick ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''}`}
      onClick={onClick}
    >
      <div className={`text-2xl font-extrabold mb-0.5 tabular-nums ${val[accent]}`}>{value}</div>
      <div className="text-xs font-semibold text-slate-700">{label}</div>
      {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
      {onClick && <div className="text-[9px] text-slate-400 mt-1">Click to view →</div>}
    </div>
  )
}

// ── Export helpers ──────────────────────────────────────────────────────────────
function downloadSummaryCSV(data: DashData) {
  const lines: string[][] = []
  lines.push(['=== KPI Summary ==='])
  lines.push(['Total Inspections', 'Passed', 'Failed', 'Pass Rate', 'Avg Rows', 'Distinct Products'])
  const t = data.totals
  lines.push([String(t.total), String(t.passed), String(t.failed), `${t.pass_rate}%`, String(t.avg_rows), String(t.distinct_products)])
  lines.push([])
  lines.push(['=== By Product ==='])
  lines.push(['Product', 'Total', 'Passed', 'Failed', 'Pass Rate'])
  data.by_product.forEach(p => lines.push([p.product, String(p.total), String(p.passed), String(p.failed), `${p.pass_rate}%`]))
  lines.push([])
  lines.push(['=== By Machinist ==='])
  lines.push(['Machinist', 'Total', 'Passed', 'Failed', 'Pass Rate'])
  data.by_machinist.forEach(m => lines.push([m.machinist, String(m.total), String(m.passed), String(m.failed), `${m.pass_rate}%`]))
  lines.push([])
  lines.push(['=== 30-Day Trend ==='])
  lines.push(['Date', 'Total', 'Passed', 'Failed'])
  data.trend.forEach(d => lines.push([d.day, String(d.total), String(d.passed), String(d.failed)]))

  const csv = lines.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
  a.download = `quality_summary_${new Date().toISOString().split('T')[0]}.csv`
  a.click()
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const navigate = useNavigate()
  const [exportOpen, setExportOpen] = useState(false)
  const [data,       setData]       = useState<DashData | null>(null)
  const [runData,    setRunData]    = useState<RunSummary | null>(null)
  const [records,    setRecords]    = useState<any[]>([])
  const [loading,    setLoading]    = useState(true)
  const [updated,    setUpdated]    = useState('')

  async function loadAll() {
    setLoading(true)
    try {
      const [dash, recs, runs] = await Promise.all([
        fetch('/api/inspection/dashboard').then(r => r.json()),
        fetch('/api/inspection/records?limit=12').then(r => r.json()),
        fetch('/api/test-runs/summary').then(r => r.json()),
      ])
      setData(dash)
      setRecords(Array.isArray(recs) ? recs : [])
      setRunData(runs && runs.totals ? runs : null)
      setUpdated(new Date().toLocaleTimeString())
    } catch { /* silent */ } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])

  // ── Loading / error states ─────────────────────────────────────────────────
  if (loading) return (
    <div className="p-5 min-h-screen bg-surface-900 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
        <div className="text-sm text-slate-500">Loading dashboard…</div>
      </div>
    </div>
  )

  if (!data) return (
    <div className="p-5 min-h-screen bg-surface-900">
      <div className="text-sm text-red-600">Failed to load dashboard data.</div>
    </div>
  )

  const { totals, by_product, by_machinist, by_operation, trend } = data

  // Fill 30-day trend (ensure every day has a bar)
  const today = new Date()
  const filledTrend: TrendDay[] = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(today); d.setDate(d.getDate() - 29 + i)
    const dayStr = d.toISOString().split('T')[0]
    return trend.find(t => (t.day || '').startsWith(dayStr)) ?? { day: dayStr, total: 0, passed: 0, failed: 0 }
  })
  const maxTrend   = Math.max(...filledTrend.map(d => d.total), 1)
  const maxProduct = Math.max(...by_product.map(p => p.total), 1)
  const passRate   = Number(totals.pass_rate ?? 0)
  const failRate   = totals.total > 0 ? (100 - passRate).toFixed(1) : '0'

  return (
    <div className="p-5 min-h-screen bg-surface-900">

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Quality Dashboard</h1>
          <p className="text-xs text-slate-500 mt-0.5">Live from Lakebase · Updated {updated}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Export dropdown */}
          <div className="relative">
            <button
              onClick={() => setExportOpen(o => !o)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {exportOpen && (
              <div className="absolute right-0 mt-1 w-52 bg-white border border-slate-200 rounded-lg shadow-lg z-20 py-1"
                   onMouseLeave={() => setExportOpen(false)}>
                <a
                  href="/api/inspection/export"
                  download
                  onClick={() => setExportOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50"
                >
                  <svg className="w-3.5 h-3.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  All Records (CSV)
                </a>
                <button
                  onClick={() => { downloadSummaryCSV(data!); setExportOpen(false) }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50"
                >
                  <svg className="w-3.5 h-3.5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  Dashboard Summary (CSV)
                </button>
              </div>
            )}
          </div>
          <button
            onClick={loadAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        <KpiCard
          label="Total Inspections"
          value={totals.total}
          sub={`${totals.distinct_products} distinct products`}
          accent="blue"
          onClick={() => navigate('/inspection/records')}
        />
        <KpiCard
          label="Pass Rate"
          value={`${passRate}%`}
          sub={`${totals.passed} inspections passed`}
          accent={passRate >= 90 ? 'green' : passRate >= 75 ? 'amber' : 'red'}
        />
        <KpiCard
          label="Failed Inspections"
          value={totals.failed}
          sub={`${failRate}% failure rate`}
          accent={totals.failed === 0 ? 'green' : 'red'}
          onClick={() => navigate('/inspection/records?status=failed')}
        />
        <KpiCard
          label="Avg Rows / Inspection"
          value={totals.avg_rows ?? '—'}
          sub="characteristics per form"
          accent="purple"
        />
      </div>

      {/* ── Charts row ── */}
      <div className="grid grid-cols-2 gap-4 mb-4">

        {/* By Product */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-4">Inspections by Product</h3>
          <div className="space-y-2.5">
            {by_product.map(p => (
              <div
                key={p.product}
                className="flex items-center gap-2 -mx-2 px-2 py-1 rounded-lg cursor-pointer hover:bg-slate-50 transition-colors group"
                onClick={() => navigate(`/inspection/records?product=${encodeURIComponent(p.product)}`)}
                title="Click to view inspections"
              >
                <div className="w-32 text-[11px] text-slate-600 text-right truncate flex-shrink-0 font-medium group-hover:text-brand-700" title={p.product}>
                  {p.product}
                </div>
                <div className="flex-1 bg-slate-100 rounded-full h-3.5 overflow-hidden flex">
                  <div
                    className="bg-brand-500 h-full transition-all duration-500"
                    style={{ width: `${(p.passed / maxProduct) * 100}%` }}
                  />
                  {p.failed > 0 && (
                    <div
                      className="bg-red-400 h-full"
                      style={{ width: `${(p.failed / maxProduct) * 100}%` }}
                    />
                  )}
                </div>
                <div className="w-6 text-right text-[11px] font-bold text-slate-800 flex-shrink-0">{p.total}</div>
                <div className={`w-10 text-right text-[10px] font-bold flex-shrink-0 ${rateColor(Number(p.pass_rate))}`}>
                  {p.pass_rate}%
                </div>
                <div className="w-3 flex-shrink-0 text-slate-300 group-hover:text-brand-500 transition-colors">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-4 mt-4 pt-3 border-t border-slate-100">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-brand-500" />
              <span className="text-[10px] text-slate-500">Pass</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-red-400" />
              <span className="text-[10px] text-slate-500">Fail</span>
            </div>
          </div>
        </div>

        {/* By Machinist + Operations */}
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-4">Pass Rate by Machinist</h3>
          <div className="space-y-3">
            {by_machinist.map(m => {
              const mr = Number(m.pass_rate)
              return (
                <div
                  key={m.machinist}
                  className="flex items-center gap-3 -mx-2 px-2 py-1 rounded-lg cursor-pointer hover:bg-slate-50 transition-colors group"
                  onClick={() => navigate(`/inspection/records?machinist=${encodeURIComponent(m.machinist)}`)}
                  title="Click to view inspections"
                >
                  <div className="w-20 text-[11px] font-medium text-slate-700 flex-shrink-0 group-hover:text-brand-700">{m.machinist}</div>
                  <div className="flex-1 bg-slate-100 rounded-full h-3.5 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${rateBg(mr)}`}
                      style={{ width: `${mr}%` }}
                    />
                  </div>
                  <div className={`w-10 text-right text-xs font-bold flex-shrink-0 ${rateColor(mr)}`}>{m.pass_rate}%</div>
                  <div className="w-7 text-right text-[10px] text-slate-400 flex-shrink-0">{m.total}</div>
                  <div className="w-3 flex-shrink-0 text-slate-300 group-hover:text-brand-500 transition-colors">
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Operations breakdown */}
          {by_operation.length > 0 && (
            <div className="mt-5 pt-4 border-t border-slate-100">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-2.5">By Operation</div>
              <div className="flex flex-wrap gap-2">
                {by_operation.map(op => {
                  const opRate = op.total > 0 ? Math.round(((op.total - op.failed) / op.total) * 100) : 100
                  return (
                    <div key={op.operation} className="flex-1 min-w-fit bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                      <div className="text-[10px] font-bold text-slate-700 truncate">{op.operation}</div>
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className="text-sm font-extrabold text-slate-800">{op.total}</span>
                        <span className={`text-[10px] font-semibold ${rateColor(opRate)}`}>{opRate}%</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Trend Chart ── */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">
            Daily Quality Activity — Last 30 Days
          </h3>
          <p className="text-[10px] text-slate-400 mt-0.5">Inspections + Test Runs combined</p>
          <div className="flex gap-4">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-brand-500" />
              <span className="text-[10px] text-slate-500">Pass</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-red-400" />
              <span className="text-[10px] text-slate-500">Fail</span>
            </div>
          </div>
        </div>

        {/* Bars */}
        <div className="flex items-end gap-px" style={{ height: 100 }}>
          {filledTrend.map((d, i) => {
            const totalH = Math.max(Math.round((d.total / maxTrend) * 100), d.total > 0 ? 4 : 0)
            const failH  = d.total > 0 ? Math.round((d.failed  / d.total) * totalH) : 0
            const passH  = totalH - failH
            return (
              <div
                key={i}
                className={`flex-1 flex flex-col justify-end group ${d.total > 0 ? 'cursor-pointer' : 'cursor-default'}`}
                title={d.total > 0 ? `${d.day}: ${d.total} (${d.failed} fail) — click to view` : d.day}
                onClick={() => d.total > 0 && navigate(`/inspection/records?date=${d.day}`)}
              >
                {failH > 0 && (
                  <div
                    className="bg-red-400 group-hover:bg-red-500 transition-colors"
                    style={{ height: failH }}
                  />
                )}
                {passH > 0 && (
                  <div
                    className={`bg-brand-500 group-hover:bg-brand-600 transition-colors ${failH === 0 ? 'rounded-t-sm' : ''}`}
                    style={{ height: passH }}
                  />
                )}
              </div>
            )
          })}
        </div>

        {/* X-axis */}
        <div className="flex mt-2">
          {filledTrend.map((d, i) => (
            <div key={i} className="flex-1 text-center">
              {(i === 0 || i % 5 === 0 || i === filledTrend.length - 1) && (
                <span className="text-[8px] text-slate-400">{d.day.slice(5)}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Test Run Failures ── */}
      {runData && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">Test Run Failures by Lab Product — Last 7 Days</h3>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-[10px] text-slate-400">{runData.totals.total} total runs</span>
              <span className={`text-xs font-bold ${rateColor(Number(runData.totals.pass_rate))}`}>
                {runData.totals.pass_rate}% pass rate
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-5">
            <KpiCard label="Test Runs This Week"  value={runData.totals.total}  sub="across all procedures"  accent="blue" />
            <KpiCard
              label="Pass Rate"
              value={`${runData.totals.pass_rate}%`}
              sub={`${runData.totals.passed} passed`}
              accent={Number(runData.totals.pass_rate) >= 90 ? 'green' : Number(runData.totals.pass_rate) >= 75 ? 'amber' : 'red'}
            />
            <KpiCard
              label="Failed Test Runs"
              value={runData.totals.failed}
              sub="require re-test or review"
              accent={runData.totals.failed === 0 ? 'green' : 'red'}
            />
          </div>

          {runData.by_product.length > 0 && (() => {
            const maxRuns = Math.max(...runData.by_product.map(p => p.total), 1)
            return (
              <div className="space-y-2.5">
                {runData.by_product.map(p => (
                  <div
                    key={p.procedure_name}
                    className="flex items-center gap-2 -mx-2 px-2 py-1 rounded-lg cursor-pointer hover:bg-slate-50 transition-colors group"
                    onClick={() => navigate(`/runs?procedure_id=${p.procedure_id}&status=failed`)}
                    title="Click to view failed runs"
                  >
                    <div className="w-44 text-[11px] text-slate-600 text-right truncate flex-shrink-0 font-medium group-hover:text-brand-700" title={p.procedure_name}>
                      {p.procedure_name}
                    </div>
                    <div className="flex-1 bg-slate-100 rounded-full h-3.5 overflow-hidden flex">
                      <div className="bg-brand-500 h-full transition-all duration-500"
                           style={{ width: `${(p.passed / maxRuns) * 100}%` }} />
                      {p.failed > 0 && (
                        <div className="bg-red-400 h-full"
                             style={{ width: `${(p.failed / maxRuns) * 100}%` }} />
                      )}
                    </div>
                    <div className="w-14 text-right text-[10px] text-slate-500 flex-shrink-0">
                      <span className="font-bold text-red-600 group-hover:underline">{p.failed}</span>
                      <span className="text-slate-400"> / {p.total}</span>
                    </div>
                    <div className={`w-10 text-right text-[10px] font-bold flex-shrink-0 ${rateColor(Number(p.pass_rate))}`}>
                      {p.pass_rate}%
                    </div>
                    <div className="w-4 flex-shrink-0 text-slate-300 group-hover:text-brand-500 transition-colors">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                ))}
              </div>
            )
          })()}

          <div className="flex gap-4 mt-4 pt-3 border-t border-slate-100">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-brand-500" />
              <span className="text-[10px] text-slate-500">Pass</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-red-400" />
              <span className="text-[10px] text-slate-500">Fail</span>
            </div>
          </div>
        </div>
      )}

      {/* ── Recent Records ── */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">Recent Inspections</h3>
          <span className="text-[10px] text-slate-400">Last 12 records</span>
        </div>
        <table className="w-full text-xs">
          <thead className="bg-slate-50">
            <tr>
              {['#','Product','W.O.','Date','Machinist','Operation','Status',''].map(h => (
                <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map(r => (
              <tr
                key={r.id}
                className="border-t border-slate-100 hover:bg-slate-50 transition-colors cursor-pointer"
                onClick={() => navigate(`/inspection/records/${r.id}`)}
              >
                <td className="px-3 py-2 font-bold text-slate-700">#{r.id}</td>
                <td className="px-3 py-2 text-slate-800 font-medium">{r.product || '—'}</td>
                <td className="px-3 py-2 font-mono text-[10px] text-slate-500">{r.wo_number || '—'}</td>
                <td className="px-3 py-2 text-slate-600">{r.inspection_date || '—'}</td>
                <td className="px-3 py-2 text-slate-600">{r.machinist || '—'}</td>
                <td className="px-3 py-2 text-slate-500 text-[10px]">{r.operation || '—'}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold
                    ${r.status === 'complete' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'}`}>
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-brand-600 font-semibold text-[10px]">View →</td>
              </tr>
            ))}
            {records.length === 0 && (
              <tr><td colSpan={8} className="text-center py-8 text-slate-400">No inspection records found</td></tr>
            )}
          </tbody>
        </table>
      </div>

    </div>
  )
}
