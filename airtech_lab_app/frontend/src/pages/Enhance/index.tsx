import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import * as api from '../../api'
import type { Reading, Enhancement, Technician, Machine, ManualMeasurement } from '../../types'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'

// ── Confidence stars ───────────────────────────────────────────────────────────
function ConfidenceSelector({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map(n => (
        <button key={n} onClick={() => onChange(n)}
          className={`w-8 h-8 rounded text-sm font-mono transition-colors ${
            n <= value ? 'bg-brand-600 text-slate-900' : 'bg-surface-600 text-slate-500 hover:bg-surface-500'
          }`}>
          {n}
        </button>
      ))}
      <span className="text-xs text-slate-500 self-center ml-2">
        {value === 1 ? 'Very Low' : value === 2 ? 'Low' : value === 3 ? 'Medium' : value === 4 ? 'High' : 'Very High'}
      </span>
    </div>
  )
}

// ── Manual measurement row ─────────────────────────────────────────────────────
function MeasurementRow({ m, onChange, onRemove }: {
  m: ManualMeasurement
  onChange: (v: Partial<ManualMeasurement>) => void
  onRemove: () => void
}) {
  return (
    <div className="flex gap-2 items-center">
      <input className="input flex-1" placeholder="Key (e.g. seal_temp)"
        value={m.key} onChange={e => onChange({ key: e.target.value })} />
      <input className="input flex-1" placeholder="Label"
        value={m.label} onChange={e => onChange({ label: e.target.value })} />
      <input className="input w-28" placeholder="Value" type="number"
        value={String(m.value ?? '')} onChange={e => onChange({ value: parseFloat(e.target.value) || e.target.value })} />
      <input className="input w-20" placeholder="Unit"
        value={m.unit ?? ''} onChange={e => onChange({ unit: e.target.value })} />
      <button onClick={onRemove}
        className="text-slate-500 hover:text-red-600 transition-colors p-1">
        <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd"
            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
            clipRule="evenodd" />
        </svg>
      </button>
    </div>
  )
}

// ── Reading picker ─────────────────────────────────────────────────────────────
function ReadingPicker({ onSelect, machines }: {
  onSelect: (r: Reading) => void
  machines: Machine[]
}) {
  const [machineId, setMachineId] = useState(machines[0]?.id ?? '')
  const [readings, setReadings] = useState<Reading[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    if (!machineId) return
    setLoading(true)
    try {
      const r = await api.getReadings({ machine_id: machineId, limit: 50 })
      setReadings(r)
    } finally {
      setLoading(false)
    }
  }, [machineId])

  useEffect(() => { load() }, [load])

  const filtered = search
    ? readings.filter(r =>
        r.reading_id.includes(search) ||
        r.serial_number.toLowerCase().includes(search.toLowerCase()) ||
        r.model_number.toLowerCase().includes(search.toLowerCase())
      )
    : readings

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <select className="input w-auto" value={machineId}
          onChange={e => setMachineId(e.target.value)}>
          {machines.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <input className="input flex-1" placeholder="Search by reading ID, serial, model…"
          value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : (
        <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
          {filtered.map(r => (
            <button key={r.reading_id} onClick={() => onSelect(r)}
              className="w-full card px-4 py-3 text-left hover:border-brand-200 transition-all">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-mono text-xs text-slate-500">{r.reading_id}</div>
                  <div className="text-sm text-slate-900">{r.serial_number} — {r.model_number}</div>
                </div>
                <Badge variant={r.result_raw === 'PASS' ? 'pass' : 'fail'}>
                  {r.result_raw}
                </Badge>
              </div>
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="text-center py-8 text-slate-600">No readings found</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function EnhancePage() {
  const [searchParams] = useSearchParams()
  const preReadingId = searchParams.get('reading_id')
  const preMachineId = searchParams.get('machine_id')

  const [machines, setMachines] = useState<Machine[]>([])
  const [techs, setTechs] = useState<Technician[]>([])
  const [reading, setReading] = useState<Reading | null>(null)
  const [existing, setExisting] = useState<Enhancement | null>(null)
  const [step, setStep] = useState<'pick' | 'form'>('pick')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Form state
  const [techId, setTechId] = useState<number | ''>('')
  const [visual, setVisual] = useState('')
  const [anomalies, setAnomalies] = useState('')
  const [corrective, setCorrective] = useState('')
  const [confidence, setConfidence] = useState(3)
  const [notes, setNotes] = useState('')
  const [manualMeasurements, setManualMeasurements] = useState<ManualMeasurement[]>([])
  const [overrideResult, setOverrideResult] = useState<'' | 'PASS' | 'FAIL'>('')

  useEffect(() => {
    Promise.all([api.getMachines(), api.getTechnicians()]).then(([m, t]) => {
      setMachines(m)
      setTechs(t)
    })
  }, [])

  // Pre-load if URL params present
  useEffect(() => {
    if (preReadingId && preMachineId && machines.length > 0) {
      api.getReading(preMachineId, preReadingId).then(r => {
        selectReading(r)
      }).catch(() => {})
    }
  }, [preReadingId, preMachineId, machines])

  const selectReading = async (r: Reading) => {
    setReading(r)
    setStep('form')
    // Try to load existing enhancement
    try {
      const enh = await api.getEnhancement(r.reading_id)
      setExisting(enh)
      setVisual(enh.visual_inspection ?? '')
      setAnomalies(enh.anomalies_noted ?? '')
      setCorrective(enh.corrective_actions ?? '')
      setConfidence(enh.confidence_in_data ?? 3)
      setNotes(enh.notes ?? '')
      setTechId(enh.technician_id ?? '')
      setManualMeasurements(enh.manual_measurements ?? [])
    } catch {
      // No existing enhancement
      setExisting(null)
    }
  }

  const addMeasurement = () => {
    setManualMeasurements(prev => [...prev, { key: '', label: '', value: '', unit: '' }])
  }

  const updateMeasurement = (idx: number, updates: Partial<ManualMeasurement>) => {
    setManualMeasurements(prev => prev.map((m, i) => i === idx ? { ...m, ...updates } : m))
  }

  const removeMeasurement = (idx: number) => {
    setManualMeasurements(prev => prev.filter((_, i) => i !== idx))
  }

  const handleSave = async () => {
    if (!reading) return
    setSaving(true)
    try {
      const payload = {
        bronze_reading_id: reading.reading_id,
        machine_id:         reading.machine_id,
        technician_id:      techId || undefined,
        visual_inspection:  visual || undefined,
        anomalies_noted:    anomalies || undefined,
        corrective_actions: corrective || undefined,
        confidence_in_data: confidence,
        notes:              notes || undefined,
        manual_measurements: manualMeasurements.filter(m => m.key),
        override_values:    overrideResult ? { result: overrideResult } : {},
      }
      if (existing) {
        await api.updateEnhancement(existing.id, payload)
      } else {
        await api.createEnhancement(payload)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Enhance Reading</h1>
        <p className="text-sm text-slate-500 mt-1">Add manual observations to augment machine-captured bronze layer data</p>
      </div>

      {step === 'pick' ? (
        <div className="card p-6 space-y-4">
          <h2 className="text-sm font-semibold text-slate-600">Select a Reading</h2>
          <ReadingPicker onSelect={selectReading} machines={machines} />
        </div>
      ) : reading && (
        <>
          {/* Reading summary bar */}
          <div className="card px-5 py-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <button onClick={() => setStep('pick')}
                className="text-slate-500 hover:text-slate-900 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <div className="font-mono text-xs text-slate-500">{reading.reading_id}</div>
                <div className="text-sm font-medium text-slate-900">{reading.serial_number} — {reading.model_number}</div>
              </div>
              <Badge variant={reading.result_raw === 'PASS' ? 'pass' : 'fail'}>
                Machine: {reading.result_raw}
              </Badge>
              {existing && <Badge variant="info">Enhancement exists — editing</Badge>}
            </div>
          </div>

          {/* Form */}
          <div className="card p-6 space-y-6">
            {/* Technician */}
            <div>
              <label className="label">Technician *</label>
              <select className="input" value={techId}
                onChange={e => setTechId(Number(e.target.value) || '')}>
                <option value="">Select technician…</option>
                {techs.map(t => <option key={t.id} value={t.id}>{t.name} — {t.specialty}</option>)}
              </select>
            </div>

            {/* Visual inspection */}
            <div>
              <label className="label">Visual Inspection</label>
              <textarea className="input resize-none" rows={3}
                placeholder="Describe visual findings: seal condition, surface quality, component alignment…"
                value={visual} onChange={e => setVisual(e.target.value)} />
            </div>

            {/* Anomalies */}
            <div>
              <label className="label">Anomalies Noted</label>
              <textarea className="input resize-none" rows={2}
                placeholder="Any unusual sounds, smells, temperatures, or behavior observed during test…"
                value={anomalies} onChange={e => setAnomalies(e.target.value)} />
            </div>

            {/* Corrective actions */}
            <div>
              <label className="label">Corrective Actions Taken</label>
              <textarea className="input resize-none" rows={2}
                placeholder="e.g. Re-torqued inlet fitting to 22 Nm, replaced gasket seal, cleaned filter…"
                value={corrective} onChange={e => setCorrective(e.target.value)} />
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

            {/* Manual measurements */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="label m-0">Additional Measurements</label>
                <button onClick={addMeasurement}
                  className="text-xs text-brand-700 hover:text-brand-700 transition-colors flex items-center gap-1">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add Measurement
                </button>
              </div>
              {manualMeasurements.length > 0 && (
                <div className="space-y-2">
                  <div className="grid grid-cols-4 gap-2 text-xs text-slate-500 px-1 mb-1">
                    <span>Key</span><span>Label</span><span>Value</span><span>Unit</span>
                  </div>
                  {manualMeasurements.map((m, i) => (
                    <MeasurementRow
                      key={i} m={m}
                      onChange={u => updateMeasurement(i, u)}
                      onRemove={() => removeMeasurement(i)}
                    />
                  ))}
                </div>
              )}
              {manualMeasurements.length === 0 && (
                <div className="text-sm text-slate-600 py-2">
                  No additional measurements. Click "Add Measurement" to record values not captured by the machine.
                </div>
              )}
            </div>

            {/* Confidence */}
            <div>
              <label className="label">Data Confidence Level</label>
              <ConfidenceSelector value={confidence} onChange={setConfidence} />
              <div className="text-xs text-slate-500 mt-1">How confident are you in the data quality for this reading?</div>
            </div>

            {/* Notes */}
            <div>
              <label className="label">General Notes</label>
              <textarea className="input resize-none" rows={2}
                placeholder="Any other observations, context, or follow-up required…"
                value={notes} onChange={e => setNotes(e.target.value)} />
            </div>

            {/* Save */}
            <div className="flex items-center justify-end gap-3 pt-2 border-t border-surface-600">
              {saved && (
                <div className="flex items-center gap-1.5 text-sm text-emerald-700">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Saved — AI prediction queued
                </div>
              )}
              <button onClick={handleSave} disabled={saving || !techId}
                className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                {saving ? <Spinner className="w-4 h-4" /> : null}
                {existing ? 'Update Enhancement' : 'Save Enhancement'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
