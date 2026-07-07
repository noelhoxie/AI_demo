import { useCallback, useEffect, useState } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import * as api from '../../api'
import type { Prediction, Reading, Machine } from '../../types'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'

// ── Pure-CSS gauge ─────────────────────────────────────────────────────────────
function ProbGauge({ value }: { value: number }) {
  const clamp = Math.max(0, Math.min(100, value))
  const color = clamp >= 85 ? '#34d399' : clamp >= 65 ? '#fbbf24' : clamp >= 40 ? '#f97316' : '#f87171'
  // SVG arc gauge
  const r = 54, cx = 64, cy = 64
  const circumference = Math.PI * r          // half-circle
  const stroke = circumference * (clamp / 100)
  return (
    <div className="relative w-32 h-20 mx-auto">
      <svg viewBox="0 0 128 80" className="w-full h-full overflow-visible">
        {/* Background arc */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none" stroke="#1e1e35" strokeWidth="10" strokeLinecap="round"
        />
        {/* Value arc */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${stroke} ${circumference}`}
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex items-end justify-center pb-1">
        <span className="text-2xl font-bold font-mono leading-none" style={{ color }}>
          {clamp.toFixed(0)}%
        </span>
      </div>
    </div>
  )
}

// ── Risk donut (pure SVG) ──────────────────────────────────────────────────────
const RISK_COLORS: Record<string, string> = {
  low: '#34d399', medium: '#fbbf24', high: '#f97316', critical: '#f87171',
}

function RiskDonut({ predictions }: { predictions: Prediction[] }) {
  const dist = predictions.reduce<Record<string, number>>((acc, p) => {
    acc[p.risk_level] = (acc[p.risk_level] ?? 0) + 1
    return acc
  }, {})
  const entries = Object.entries(dist)
  const total = entries.reduce((s, [, v]) => s + v, 0)

  // Build pie slices
  let offset = 0
  const r = 40, cx = 60, cy = 60, circumference = 2 * Math.PI * r
  const slices = entries.map(([level, count]) => {
    const pct = count / total
    const dash = pct * circumference
    const slice = { level, count, dash, offset, color: RISK_COLORS[level] ?? '#6366f1' }
    offset += dash
    return slice
  })

  return (
    <div className="card p-5 flex flex-col items-center gap-3">
      <div className="text-sm font-semibold text-slate-600">Risk Distribution</div>
      <svg viewBox="0 0 120 120" className="w-32 h-32">
        {slices.map(s => (
          <circle key={s.level} cx={cx} cy={cy} r={r}
            fill="none" stroke={s.color} strokeWidth="18"
            strokeDasharray={`${s.dash} ${circumference - s.dash}`}
            strokeDashoffset={-(s.offset - circumference / 4)}
            style={{ transition: 'stroke-dasharray 0.4s' }}
          />
        ))}
        {/* Inner hole */}
        <circle cx={cx} cy={cy} r={28} fill="#16162a" />
        <text x={cx} y={cy + 5} textAnchor="middle" fontSize="14"
          fontWeight="bold" fill="#e2e8f0">{total}</text>
      </svg>
      <div className="flex flex-wrap gap-3 justify-center">
        {slices.map(s => (
          <div key={s.level} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-xs text-slate-500 capitalize">{s.level} ({s.count})</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Average probability card ───────────────────────────────────────────────────
function AvgProbCard({ predictions }: { predictions: Prediction[] }) {
  const avg = predictions.length
    ? predictions.reduce((s, p) => s + p.success_probability, 0) / predictions.length
    : 0
  const color = avg >= 85 ? '#34d399' : avg >= 65 ? '#fbbf24' : '#f87171'
  const fill = avg >= 85 ? 'bg-emerald-500' : avg >= 65 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="card p-5">
      <div className="text-sm font-semibold text-slate-600 mb-3">Average Success Probability</div>
      <div className="text-4xl font-bold font-mono mb-3" style={{ color }}>
        {avg.toFixed(1)}%
      </div>
      <div className="h-2 bg-surface-600 rounded-full overflow-hidden">
        <div className={`h-full ${fill} rounded-full transition-all`} style={{ width: `${avg}%` }} />
      </div>
      <div className="text-xs text-slate-500 mt-2">{predictions.length} readings analyzed</div>
    </div>
  )
}

// ── Prediction card ────────────────────────────────────────────────────────────
const RISK_VARIANT: Record<string, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical', high: 'high', medium: 'medium', low: 'low',
}

function PredictionCard({ pred, onRerun }: { pred: Prediction; onRerun: (p: Prediction) => void }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-xs text-slate-500">{pred.bronze_reading_id}</div>
          <div className="text-sm text-slate-600 mt-0.5">
            {pred.machine_id === 'machine_pressure' ? 'Pressure/Leak Tester' : 'Flow/Performance Tester'}
          </div>
        </div>
        <Badge variant={RISK_VARIANT[pred.risk_level] ?? 'medium'}>{pred.risk_level} risk</Badge>
      </div>

      <ProbGauge value={pred.success_probability} />

      <div className="text-center">
        <div className="text-xs text-slate-500 mb-1">Success Probability</div>
        <div className="text-xs text-slate-500 font-mono">{pred.model_version}</div>
      </div>

      <div className="bg-surface-700/40 rounded-lg p-3">
        <div className="text-xs font-medium text-slate-500 mb-1.5">AI Analysis</div>
        <p className="text-xs text-slate-600 leading-relaxed">{pred.reasoning}</p>
      </div>

      {(pred.risk_factors.length > 0 || pred.recommendations.length > 0) && (
        <div>
          <button onClick={() => setExpanded(v => !v)}
            className="text-xs text-brand-700 hover:text-brand-700 transition-colors flex items-center gap-1">
            {expanded ? 'Hide' : 'Show'} details
            <svg className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {expanded && (
            <div className="mt-3 space-y-3">
              {pred.risk_factors.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-red-600 mb-1.5">Risk Factors</div>
                  <ul className="space-y-1">
                    {pred.risk_factors.map((f, i) => (
                      <li key={i} className="text-xs text-slate-500 flex items-start gap-1.5">
                        <span className="text-red-500 mt-0.5">•</span> {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {pred.recommendations.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-emerald-700 mb-1.5">Recommendations</div>
                  <ul className="space-y-1">
                    {pred.recommendations.map((r, i) => (
                      <li key={i} className="text-xs text-slate-500 flex items-start gap-1.5">
                        <span className="text-emerald-500 mt-0.5">→</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between pt-2 border-t border-surface-600">
        <span className="text-xs text-slate-600">
          {formatDistanceToNow(parseISO(pred.generated_at), { addSuffix: true })}
        </span>
        <button onClick={() => onRerun(pred)}
          className="text-xs text-brand-700 hover:text-brand-700 transition-colors">Re-run</button>
      </div>
    </div>
  )
}

// ── Unanalyzed row ─────────────────────────────────────────────────────────────
function UnanalyzedRow({ reading, onTrigger }: { reading: Reading; onTrigger: (r: Reading) => void }) {
  return (
    <div className="card px-4 py-3 flex items-center justify-between gap-3">
      <div>
        <div className="font-mono text-xs text-slate-500">{reading.reading_id}</div>
        <div className="text-sm text-slate-600">{reading.serial_number} — {reading.model_number}</div>
      </div>
      <div className="flex items-center gap-3">
        <Badge variant={reading.result_raw === 'PASS' ? 'pass' : 'fail'}>{reading.result_raw}</Badge>
        <button onClick={() => onTrigger(reading)} className="btn-primary text-xs py-1.5">Analyze</button>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function PredictionsPage() {
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [unanalyzed, setUnanalyzed] = useState<Reading[]>([])
  const [machines, setMachines] = useState<Machine[]>([])
  const [loading, setLoading] = useState(true)
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set())
  const [filterRisk, setFilterRisk] = useState('')
  const [filterMachine, setFilterMachine] = useState('')

  const load = useCallback(async () => {
    try {
      const [preds, m] = await Promise.all([api.getPredictions(), api.getMachines()])
      setPredictions(preds)
      setMachines(m)
      const readingIds = new Set(preds.map(p => p.bronze_reading_id))
      const readings = await api.getReadings({ limit: 40 })
      setUnanalyzed(readings.filter(r => !readingIds.has(r.reading_id)))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleRerun = async (pred: Prediction) => {
    setRunningIds(s => new Set([...s, pred.bronze_reading_id]))
    await api.triggerPrediction(pred.bronze_reading_id, pred.machine_id)
    setTimeout(() => { setRunningIds(s => { const n = new Set(s); n.delete(pred.bronze_reading_id); return n }); load() }, 4000)
  }

  const handleTrigger = async (reading: Reading) => {
    setRunningIds(s => new Set([...s, reading.reading_id]))
    await api.triggerPrediction(reading.reading_id, reading.machine_id)
    setTimeout(() => { setRunningIds(s => { const n = new Set(s); n.delete(reading.reading_id); return n }); load() }, 4000)
  }

  const filtered = predictions.filter(p =>
    (!filterRisk || p.risk_level === filterRisk) &&
    (!filterMachine || p.machine_id === filterMachine)
  )

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">AI Predictions</h1>
        <p className="text-sm text-slate-500 mt-1">
          Claude (claude-sonnet-4-6) analyzes lab readings and predicts acceptance test success probability
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20"><Spinner /></div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <AvgProbCard predictions={predictions} />
            <RiskDonut predictions={predictions} />
            <div className="card p-5 space-y-3">
              <div className="text-sm font-semibold text-slate-600">Unanalyzed Readings</div>
              <div className="text-4xl font-bold font-mono text-amber-700">{unanalyzed.length}</div>
              <div className="text-xs text-slate-500">recent readings without a prediction</div>
              {unanalyzed.length > 0 && (
                <button onClick={() => unanalyzed.slice(0, 5).forEach(handleTrigger)}
                  className="btn-primary text-sm w-full">Analyze Next 5</button>
              )}
            </div>
          </div>

          {unanalyzed.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-500">Readings Awaiting Analysis</h2>
              {unanalyzed.slice(0, 8).map(r => (
                runningIds.has(r.reading_id) ? (
                  <div key={r.reading_id} className="card px-4 py-3 flex items-center gap-3 opacity-60">
                    <Spinner className="w-4 h-4" /><span className="text-sm text-slate-500">Analyzing {r.reading_id}…</span>
                  </div>
                ) : <UnanalyzedRow key={r.reading_id} reading={r} onTrigger={handleTrigger} />
              ))}
            </div>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-sm font-semibold text-slate-600">Prediction History</div>
            <div className="flex gap-2 ml-4">
              {['', 'low', 'medium', 'high', 'critical'].map(v => (
                <button key={v} onClick={() => setFilterRisk(v)}
                  className={`px-3 py-1 text-xs rounded-lg capitalize transition-colors ${filterRisk === v ? 'bg-surface-600 text-slate-900' : 'text-slate-500 hover:text-slate-900'}`}>
                  {v || 'All Risk'}
                </button>
              ))}
            </div>
            <select className="input w-auto text-sm ml-auto" value={filterMachine}
              onChange={e => setFilterMachine(e.target.value)}>
              <option value="">All Machines</option>
              {machines.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map(pred => (
              runningIds.has(pred.bronze_reading_id) ? (
                <div key={pred.id} className="card p-5 flex flex-col items-center justify-center gap-3 min-h-[200px] opacity-60">
                  <Spinner /><div className="text-sm text-slate-500">Re-analyzing…</div>
                </div>
              ) : <PredictionCard key={pred.id} pred={pred} onRerun={handleRerun} />
            ))}
            {filtered.length === 0 && (
              <div className="col-span-full text-center py-16 text-slate-600">
                No predictions yet. Select readings above and click Analyze.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
