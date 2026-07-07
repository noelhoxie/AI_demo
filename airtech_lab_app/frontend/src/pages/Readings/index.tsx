import { useCallback, useEffect, useState } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import * as api from '../../api'
import type { Reading, Machine, Enhancement, Technician, ManualMeasurement } from '../../types'
import Badge from '../../components/ui/Badge'
import Modal from '../../components/ui/Modal'
import Spinner from '../../components/ui/Spinner'

// ── Enhancement modal (inline form) ───────────────────────────────────────────
function EnhancementModal({ reading, techs, onClose, onSaved }: {
  reading: Reading
  techs: Technician[]
  onClose: () => void
  onSaved: () => void
}) {
  const [existing, setExisting] = useState<Enhancement | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const [techId, setTechId] = useState<number | ''>('')
  const [visual, setVisual] = useState('')
  const [anomalies, setAnomalies] = useState('')
  const [corrective, setCorrective] = useState('')
  const [confidence, setConfidence] = useState(3)
  const [notes, setNotes] = useState('')
  const [overrideResult, setOverrideResult] = useState<'' | 'PASS' | 'FAIL'>('')
  const [measurements, setMeasurements] = useState<ManualMeasurement[]>([])

  useEffect(() => {
    api.getEnhancement(reading.reading_id)
      .then(enh => {
        setExisting(enh)
        setTechId(enh.technician_id ?? '')
        setVisual(enh.visual_inspection ?? '')
        setAnomalies(enh.anomalies_noted ?? '')
        setCorrective(enh.corrective_actions ?? '')
        setConfidence(enh.confidence_in_data ?? 3)
        setNotes(enh.notes ?? '')
        setMeasurements(enh.manual_measurements ?? [])
        const ov = enh.override_values?.result
        if (ov === 'PASS' || ov === 'FAIL') setOverrideResult(ov)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [reading.reading_id])

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        bronze_reading_id: reading.reading_id,
        machine_id: reading.machine_id,
        technician_id: techId || undefined,
        visual_inspection: visual || undefined,
        anomalies_noted: anomalies || undefined,
        corrective_actions: corrective || undefined,
        confidence_in_data: confidence,
        notes: notes || undefined,
        manual_measurements: measurements.filter(m => m.key),
        override_values: overrideResult ? { result: overrideResult } : {},
      }
      if (existing) {
        await api.updateEnhancement(existing.id, payload)
      } else {
        await api.createEnhancement(payload)
      }
      setSaved(true)
      setTimeout(() => { setSaved(false); onSaved(); onClose() }, 1500)
    } finally {
      setSaving(false)
    }
  }

  const addMeasurement = () =>
    setMeasurements(prev => [...prev, { key: '', label: '', value: '', unit: '' }])

  return (
    <Modal title={existing ? 'Edit Enhancement' : 'Add Enhancement'} onClose={onClose} wide>
      {loading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : (
        <div className="space-y-5">
          {/* Reading context */}
          <div className="flex items-center gap-3 px-3 py-2 bg-surface-700/50 rounded-lg">
            <span className="font-mono text-xs text-slate-500">{reading.reading_id}</span>
            <span className="text-sm text-slate-900">{reading.serial_number} — {reading.model_number}</span>
            <Badge variant={reading.result_raw === 'PASS' ? 'pass' : 'fail'}>{reading.result_raw}</Badge>
            {existing && <Badge variant="info">Editing existing</Badge>}
          </div>

          {/* Technician */}
          <div>
            <label className="label">Technician</label>
            <select className="input" value={techId}
              onChange={e => setTechId(Number(e.target.value) || '')}>
              <option value="">Select technician…</option>
              {techs.map(t => <option key={t.id} value={t.id}>{t.name} — {t.specialty}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {/* Visual inspection */}
            <div>
              <label className="label">Visual Inspection</label>
              <textarea className="input resize-none" rows={2}
                placeholder="Describe visual findings: seal condition, surface quality, component alignment…"
                value={visual} onChange={e => setVisual(e.target.value)} />
            </div>

            {/* Anomalies */}
            <div>
              <label className="label">Anomalies Noted</label>
              <textarea className="input resize-none" rows={2}
                placeholder="Unusual sounds, smells, temperatures, or behavior…"
                value={anomalies} onChange={e => setAnomalies(e.target.value)} />
            </div>

            {/* Corrective actions */}
            <div>
              <label className="label">Corrective Actions Taken</label>
              <textarea className="input resize-none" rows={2}
                placeholder="e.g. Re-torqued inlet fitting, replaced gasket seal…"
                value={corrective} onChange={e => setCorrective(e.target.value)} />
            </div>

            {/* Notes */}
            <div>
              <label className="label">Notes</label>
              <textarea className="input resize-none" rows={2}
                placeholder="Any other observations, context, or follow-up required…"
                value={notes} onChange={e => setNotes(e.target.value)} />
            </div>
          </div>

          {/* Override result */}
          <div>
            <label className="label">Override Machine Result</label>
            <div className="flex gap-2">
              {(['', 'PASS', 'FAIL'] as const).map(v => (
                <button key={v} onClick={() => setOverrideResult(v)}
                  className={`px-4 py-2 text-sm rounded-lg border transition-colors ${
                    overrideResult === v
                      ? v === 'PASS' ? 'bg-emerald-50 border-emerald-400 text-emerald-700'
                        : v === 'FAIL' ? 'bg-red-50 border-red-400 text-red-600'
                        : 'bg-surface-600 border-surface-400 text-slate-900'
                      : 'border-surface-500 text-slate-500 hover:border-surface-400'
                  }`}>
                  {v || 'No Override'}
                </button>
              ))}
            </div>
          </div>

          {/* Additional measurements */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="label m-0">Additional Measurements</label>
              <button onClick={addMeasurement}
                className="text-xs text-brand-700 hover:text-brand-700 transition-colors flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add
              </button>
            </div>
            {measurements.map((m, i) => (
              <div key={i} className="flex gap-2 items-center mb-2">
                <input className="input flex-1" placeholder="Key" value={m.key}
                  onChange={e => setMeasurements(prev => prev.map((x, j) => j === i ? { ...x, key: e.target.value } : x))} />
                <input className="input flex-1" placeholder="Label" value={m.label}
                  onChange={e => setMeasurements(prev => prev.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
                <input className="input w-24" placeholder="Value" value={String(m.value ?? '')}
                  onChange={e => setMeasurements(prev => prev.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
                <input className="input w-20" placeholder="Unit" value={m.unit ?? ''}
                  onChange={e => setMeasurements(prev => prev.map((x, j) => j === i ? { ...x, unit: e.target.value } : x))} />
                <button onClick={() => setMeasurements(prev => prev.filter((_, j) => j !== i))}
                  className="text-slate-500 hover:text-red-600 transition-colors p-1">
                  <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              </div>
            ))}
          </div>

          {/* Confidence */}
          <div>
            <label className="label">Data Confidence (1–5)</label>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map(n => (
                <button key={n} onClick={() => setConfidence(n)}
                  className={`w-8 h-8 rounded text-sm font-mono transition-colors ${
                    n <= confidence ? 'bg-brand-600 text-slate-900' : 'bg-surface-600 text-slate-500 hover:bg-surface-500'
                  }`}>{n}</button>
              ))}
              <span className="text-xs text-slate-500 self-center ml-2">
                {confidence === 1 ? 'Very Low' : confidence === 2 ? 'Low' : confidence === 3 ? 'Medium' : confidence === 4 ? 'High' : 'Very High'}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2 border-t border-surface-600">
            {saved && (
              <span className="text-sm text-emerald-700 flex items-center gap-1">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Saved
              </span>
            )}
            <button className="btn-ghost" onClick={onClose} disabled={saving}>Cancel</button>
            <button className="btn-primary flex items-center gap-2" onClick={handleSave} disabled={saving}>
              {saving && <Spinner className="w-4 h-4" />}
              {existing ? 'Update Enhancement' : 'Save Enhancement'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ── Reading detail modal ───────────────────────────────────────────────────────
function ReadingDetailModal({ reading, onClose, onEnhance, onPredict }: {
  reading: Reading
  onClose: () => void
  onEnhance: () => void
  onPredict: () => void
}) {
  const isPressure = reading.machine_id === 'machine_pressure'

  return (
    <Modal title={`Reading ${reading.reading_id}`} onClose={onClose} wide>
      <div className="space-y-4">
        {/* Header */}
        <div className="grid grid-cols-2 gap-4 p-4 bg-surface-700/50 rounded-lg">
          <div>
            <div className="text-xs text-slate-500">Serial Number</div>
            <div className="font-mono text-slate-900">{reading.serial_number}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Model</div>
            <div className="text-slate-900">{reading.model_number}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Test Type</div>
            <div className="text-slate-700">{reading.test_type}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Recorded</div>
            <div className="text-slate-700 text-sm">{formatDistanceToNow(parseISO(reading.recorded_at), { addSuffix: true })}</div>
          </div>
        </div>

        {/* Machine result */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-500">Machine Result:</span>
          <Badge variant={reading.result_raw === 'PASS' ? 'pass' : 'fail'}>
            {reading.result_raw}
          </Badge>
        </div>

        {/* Measurements */}
        <div>
          <h3 className="text-sm font-medium text-slate-600 mb-3">Raw Measurements</h3>
          <div className="grid grid-cols-2 gap-2">
            {isPressure ? (
              <>
                <Metric label="Pressure" value={reading.pressure_psi} unit="psi"
                  warn={reading.pressure_psi != null && reading.pressure_psi < 130} />
                <Metric label="Hold Time" value={reading.hold_time_sec} unit="sec" />
                <Metric label="Leak Rate" value={reading.leak_rate_psi_min} unit="psi/min"
                  warn={reading.leak_rate_psi_min != null && reading.leak_rate_psi_min >= 0.1} />
                <Metric label="Ambient Temp" value={reading.ambient_temp_c} unit="°C" />
              </>
            ) : (
              <>
                <Metric label="Flow Rate" value={reading.flow_rate_lpm} unit="L/min"
                  warn={reading.flow_rate_lpm != null && reading.flow_rate_lpm < 80} />
                <Metric label="Delta P" value={reading.delta_p_bar} unit="bar" />
                <Metric label="Efficiency" value={reading.efficiency_pct} unit="%"
                  warn={reading.efficiency_pct != null && reading.efficiency_pct < 80} />
                <Metric label="RPM" value={reading.rpm} unit="rpm" />
                <Metric label="Vibration" value={reading.vibration_mm_s} unit="mm/s"
                  warn={reading.vibration_mm_s != null && reading.vibration_mm_s > 3.5} />
              </>
            )}
          </div>
        </div>

        {/* Enhancement summary */}
        {reading.enhancement && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="text-xs font-medium text-blue-700 mb-2">Manual Enhancement</div>
            {reading.enhancement.visual_inspection && (
              <div className="text-sm text-slate-600">
                <span className="text-slate-500">Visual: </span>{reading.enhancement.visual_inspection}
              </div>
            )}
            {reading.enhancement.anomalies_noted && (
              <div className="text-sm text-slate-600 mt-1">
                <span className="text-slate-500">Anomalies: </span>{reading.enhancement.anomalies_noted}
              </div>
            )}
          </div>
        )}

        {/* Prediction summary */}
        {reading.prediction && (
          <div className={`p-3 rounded-lg border ${
            reading.prediction.risk_level === 'low' ? 'bg-emerald-50 border-emerald-200'
            : reading.prediction.risk_level === 'critical' ? 'bg-red-50 border-red-200'
            : 'bg-amber-50 border-amber-200'
          }`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-600">AI Prediction</span>
              <span className="text-lg font-bold font-mono text-slate-900">
                {reading.prediction.success_probability?.toFixed(0)}%
              </span>
            </div>
            <div className="text-xs text-slate-500">{reading.prediction.reasoning}</div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <button onClick={onEnhance} className="btn-primary flex-1">
            {reading.enhancement ? 'Edit Enhancement' : 'Add Enhancement'}
          </button>
          <button onClick={onPredict}
            className="btn-ghost border border-surface-500 flex-1">
            {reading.prediction ? 'Re-run AI' : 'Run AI Prediction'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function Metric({ label, value, unit, warn = false }: {
  label: string
  value?: number | null
  unit: string
  warn?: boolean
}) {
  return (
    <div className="bg-surface-700/50 rounded-lg px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`font-mono text-sm font-medium mt-0.5 ${warn ? 'text-red-600' : 'text-slate-700'}`}>
        {value != null ? `${value} ${unit}` : '—'}
      </div>
    </div>
  )
}

// ── Reading card ───────────────────────────────────────────────────────────────
function ReadingCard({ reading, onClick, onEdit }: {
  reading: Reading
  onClick: () => void
  onEdit: (e: React.MouseEvent) => void
}) {
  const isPressure = reading.machine_id === 'machine_pressure'

  return (
    <div
      onClick={onClick}
      className="card px-4 py-3 cursor-pointer hover:border-brand-200 hover:bg-surface-700/60 transition-all"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <div className="font-mono text-xs text-slate-500">{reading.reading_id}</div>
          <div className="font-medium text-sm text-slate-900 mt-0.5">{reading.serial_number}</div>
          <div className="text-xs text-slate-500">{reading.model_number}</div>
        </div>
        <Badge variant={reading.result_raw === 'PASS' ? 'pass' : 'fail'}>
          {reading.result_raw}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs mt-2">
        {isPressure ? (
          <>
            <div><span className="text-slate-500">Pressure: </span>
              <span className={reading.pressure_psi != null && reading.pressure_psi < 130 ? 'text-red-600' : 'text-slate-600'}>
                {reading.pressure_psi} psi
              </span>
            </div>
            <div><span className="text-slate-500">Leak: </span>
              <span className={reading.leak_rate_psi_min != null && reading.leak_rate_psi_min >= 0.1 ? 'text-red-600' : 'text-slate-600'}>
                {reading.leak_rate_psi_min} psi/min
              </span>
            </div>
          </>
        ) : (
          <>
            <div><span className="text-slate-500">Flow: </span>
              <span className={reading.flow_rate_lpm != null && reading.flow_rate_lpm < 80 ? 'text-red-600' : 'text-slate-600'}>
                {reading.flow_rate_lpm} L/min
              </span>
            </div>
            <div><span className="text-slate-500">Eff: </span>
              <span className={reading.efficiency_pct != null && reading.efficiency_pct < 80 ? 'text-red-600' : 'text-slate-600'}>
                {reading.efficiency_pct}%
              </span>
            </div>
          </>
        )}
      </div>

      {/* Notes preview */}
      {reading.enhancement?.notes && (
        <div className="mt-2 text-xs text-slate-500 italic truncate">
          <span className="text-slate-600">Notes: </span>{reading.enhancement.notes}
        </div>
      )}

      <div className="flex items-center justify-between mt-3 pt-2 border-t border-surface-600">
        <span className="text-xs text-slate-600">
          {formatDistanceToNow(parseISO(reading.recorded_at), { addSuffix: true })}
        </span>
        <div className="flex items-center gap-2">
          {reading.enhancement && <span className="text-xs text-blue-700">Enhanced</span>}
          {reading.prediction && (
            <span className={`text-xs font-mono ${
              reading.prediction.success_probability >= 85 ? 'text-emerald-700'
              : reading.prediction.success_probability >= 65 ? 'text-amber-700'
              : 'text-red-600'
            }`}>
              {reading.prediction.success_probability?.toFixed(0)}%
            </span>
          )}
          {/* Edit button */}
          <button
            onClick={onEdit}
            title="Edit enhancement"
            className="p-1 rounded text-slate-600 hover:text-brand-700 hover:bg-surface-600 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function ReadingsPage() {
  const [readings, setReadings] = useState<Reading[]>([])
  const [machines, setMachines] = useState<Machine[]>([])
  const [techs, setTechs] = useState<Technician[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedMachine, setSelectedMachine] = useState('')
  const [filterResult, setFilterResult] = useState('')
  const [selected, setSelected] = useState<Reading | null>(null)
  const [enhanceTarget, setEnhanceTarget] = useState<Reading | null>(null)
  const [predicting, setPredicting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [r, m, t] = await Promise.all([
        api.getReadings({ machine_id: selectedMachine || undefined, limit: 60 }),
        api.getMachines(),
        api.getTechnicians(),
      ])
      setReadings(r)
      setMachines(m)
      setTechs(t)
    } finally {
      setLoading(false)
    }
  }, [selectedMachine])

  useEffect(() => { load() }, [load])

  const handlePredict = async () => {
    if (!selected) return
    setPredicting(true)
    await api.triggerPrediction(selected.reading_id, selected.machine_id)
    setTimeout(async () => {
      await load()
      setPredicting(false)
    }, 3000)
  }

  const filtered = filterResult
    ? readings.filter(r => r.result_raw === filterResult)
    : readings

  const passRate = readings.length
    ? Math.round(100 * readings.filter(r => r.result_raw === 'PASS').length / readings.length)
    : 0

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Machine Readings</h1>
        <p className="text-sm text-slate-500 mt-1">Live bronze layer feed from lab machines</p>
      </div>

      {/* Machine tabs + stats */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedMachine('')}
            className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
              !selectedMachine ? 'bg-brand-600 text-slate-900' : 'btn-ghost'
            }`}
          >
            All Machines
          </button>
          {machines.map(m => (
            <button
              key={m.id}
              onClick={() => setSelectedMachine(m.id)}
              className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                selectedMachine === m.id ? 'bg-brand-600 text-slate-900' : 'btn-ghost'
              }`}
            >
              {m.location}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-4 text-sm">
          <div className="card px-3 py-1.5">
            <span className="text-slate-500">Pass Rate: </span>
            <span className={`font-mono font-bold ${passRate >= 90 ? 'text-emerald-700' : passRate >= 75 ? 'text-amber-700' : 'text-red-600'}`}>
              {passRate}%
            </span>
          </div>
          <div className="flex gap-2">
            {['', 'PASS', 'FAIL'].map(v => (
              <button key={v} onClick={() => setFilterResult(v)}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                  filterResult === v ? 'bg-surface-600 text-slate-900' : 'text-slate-500 hover:text-slate-900'
                }`}>
                {v || 'All'}
              </button>
            ))}
          </div>
          <button onClick={load} className="btn-ghost text-sm">Refresh</button>
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filtered.map(r => (
            <ReadingCard
              key={r.reading_id}
              reading={r}
              onClick={() => setSelected(r)}
              onEdit={e => { e.stopPropagation(); setEnhanceTarget(r) }}
            />
          ))}
        </div>
      )}

      {/* Detail modal */}
      {selected && (
        <ReadingDetailModal
          reading={selected}
          onClose={() => setSelected(null)}
          onEnhance={() => { setSelected(null); setEnhanceTarget(selected) }}
          onPredict={handlePredict}
        />
      )}

      {/* Enhancement modal */}
      {enhanceTarget && (
        <EnhancementModal
          reading={enhanceTarget}
          techs={techs}
          onClose={() => setEnhanceTarget(null)}
          onSaved={load}
        />
      )}

      {/* Predicting overlay */}
      {predicting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="card p-8 flex flex-col items-center gap-4">
            <Spinner className="w-10 h-10" />
            <div className="text-sm text-slate-600">AI agent analyzing reading…</div>
          </div>
        </div>
      )}
    </div>
  )
}
