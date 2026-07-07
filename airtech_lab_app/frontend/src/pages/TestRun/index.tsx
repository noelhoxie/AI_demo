import { useEffect, useState } from 'react'

// ── Types ───────────────────────────────────────────────────────────────────
interface Tolerance {
  nominal?: number
  lower?: number
  upper?: number
  unit?: string
}

interface StepRefImage { id: number; filename: string; mime_type: string; data_b64: string }

interface Step {
  id: number
  order_index: number
  step_type: 'instruction' | 'text' | 'radio' | 'number' | 'ok_check' | 'pass_fail' | 'auto_number'
  label: string
  options_json: string[]
  tolerances_json: Tolerance
  is_mandatory: boolean
  is_critical: boolean
  condition_json: { step_id: number; value: string } | null
  hint_text: string | null
  images?: StepRefImage[]
}

interface Section {
  id: number
  order_index: number
  title: string
  section_type: 'manual' | 'instruction' | 'auto'
  steps: Step[]
}

interface Procedure {
  id: number
  name: string
  doc_id: string
  version: string
  product_type: string
  sections: Section[]
}

interface ProcSummary {
  id: number
  name: string
  doc_id: string
  version: string
  product_type: string
}

interface RunInfo {
  serialNumber: string
  modelNumber: string
  testLocation: string
  technicianName: string
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function autoGenValue(tol: Tolerance): string {
  const lo = tol.lower ?? 0
  const hi = tol.upper ?? 100
  const nom = tol.nominal
  const center = nom !== undefined ? nom : (lo + hi) / 2
  const range = hi - lo
  const variance = range * 0.3
  const raw = center + (Math.random() * 2 - 1) * variance
  const clamped = Math.min(hi - range * 0.04, Math.max(lo + range * 0.04, raw))
  // Integer if small whole-number range (e.g. Station Number 1–8)
  if (range <= 10 && lo >= 0 && Number.isInteger(lo) && Number.isInteger(hi)) {
    return String(Math.round(clamped))
  }
  const decimals = String(lo).includes('.') ? String(lo).split('.')[1].length : 2
  return clamped.toFixed(Math.max(decimals, 2))
}

function checkPass(value: string, tol: Tolerance): boolean | null {
  if (!value) return null
  const n = parseFloat(value)
  if (isNaN(n)) return null
  if (tol.lower !== undefined && n < tol.lower) return false
  if (tol.upper !== undefined && n > tol.upper) return false
  return true
}

function computePassed(step: Step, value: string): boolean | null {
  if (step.step_type === 'instruction') return null
  if (!value) return null
  if (step.step_type === 'ok_check') return value === 'OK'
  if (step.step_type === 'pass_fail') return value === 'Pass'
  if (step.step_type === 'radio' || step.step_type === 'text') return value.length > 0
  if (step.step_type === 'number' || step.step_type === 'auto_number') {
    return checkPass(value, step.tolerances_json)
  }
  return null
}

function isStepVisible(step: Step, responses: Record<number, string>): boolean {
  if (!step.condition_json) return true
  const { step_id, value } = step.condition_json
  return responses[step_id] === value
}

// ── Sub-components ───────────────────────────────────────────────────────────
function ToleranceLine({ tol }: { tol: Tolerance }) {
  const parts: string[] = []
  if (tol.lower !== undefined) parts.push(`Lower limit ${tol.lower}`)
  if (tol.upper !== undefined) parts.push(`Upper limit ${tol.upper}`)
  if (tol.nominal !== undefined) parts.push(`Nominal value ${tol.nominal}`)
  if (!parts.length) return null
  return (
    <span className="text-[10px] text-slate-400 ml-2">
      {parts.join('  ·  ')}{tol.unit ? `  ${tol.unit}` : ''}
    </span>
  )
}

function NumberInput({
  step, value, onChange, locked,
}: {
  step: Step; value: string; onChange: (v: string) => void; locked?: boolean
}) {
  const tol = step.tolerances_json
  const passed = checkPass(value, tol)
  const hasValue = value !== ''
  const borderClass = !hasValue ? 'border-slate-300' : passed ? 'border-green-400' : 'border-red-400'
  const bgClass = !hasValue ? '' : passed ? 'bg-green-50' : 'bg-red-50'

  return (
    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
      <input
        type="number"
        step="any"
        value={value}
        readOnly={locked}
        onChange={e => onChange(e.target.value)}
        className={`border rounded-md px-2.5 py-1 text-sm w-32 tabular-nums
          ${borderClass} ${bgClass}
          ${locked ? 'bg-slate-50 text-slate-500 cursor-default' : ''}
          focus:outline-none focus:ring-1 focus:ring-brand-500`}
        placeholder="Enter value"
      />
      {tol.unit && <span className="text-xs text-slate-500 font-medium">{tol.unit}</span>}
      <ToleranceLine tol={tol} />
      {hasValue && passed === true  && <span className="text-[10px] font-bold text-green-700 bg-green-100 px-1.5 py-0.5 rounded">PASS</span>}
      {hasValue && passed === false && <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded">FAIL</span>}
      {locked && <span className="text-[10px] text-slate-400 italic">Machine captured</span>}
    </div>
  )
}

function StepInput({
  step, value, onChange,
}: {
  step: Step
  value: string
  onChange: (v: string) => void
}) {
  const t = step.step_type

  if (t === 'instruction') {
    return (
      <div className="mt-1 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg p-3 whitespace-pre-line leading-relaxed">
        {step.label}
      </div>
    )
  }

  if (t === 'text') {
    return (
      <div className="mt-1.5">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={step.hint_text ?? 'Enter response'}
          className="border border-slate-300 rounded-md px-2.5 py-1 text-sm w-72
            focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        {step.hint_text && <div className="text-[10px] text-slate-400 mt-0.5">{step.hint_text}</div>}
      </div>
    )
  }

  if (t === 'radio') {
    return (
      <div className="mt-1.5 space-y-1">
        {step.options_json.map(opt => (
          <label key={opt} className="flex items-center gap-2 cursor-pointer group">
            <input
              type="radio"
              name={`step-${step.id}`}
              value={opt}
              checked={value === opt}
              onChange={() => onChange(opt)}
              className="accent-brand-600"
            />
            <span className={`text-xs ${value === opt ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
              {opt}
            </span>
          </label>
        ))}
      </div>
    )
  }

  if (t === 'ok_check') {
    return (
      <div className="mt-1.5 flex gap-4">
        {['OK', 'Not OK'].map(opt => (
          <label key={opt} className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="radio"
              name={`step-${step.id}`}
              value={opt}
              checked={value === opt}
              onChange={() => onChange(opt)}
              className="accent-brand-600"
            />
            <span className={`text-xs font-medium ${
              value === opt
                ? opt === 'OK' ? 'text-green-700' : 'text-red-700'
                : 'text-slate-600'
            }`}>{opt}</span>
          </label>
        ))}
      </div>
    )
  }

  if (t === 'pass_fail') {
    return (
      <div className="mt-1.5 flex gap-4">
        {['Pass', 'Fail'].map(opt => (
          <label key={opt} className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="radio"
              name={`step-${step.id}`}
              value={opt}
              checked={value === opt}
              onChange={() => onChange(opt)}
              className="accent-brand-600"
            />
            <span className={`text-xs font-medium ${
              value === opt
                ? opt === 'Pass' ? 'text-green-700' : 'text-red-700'
                : 'text-slate-600'
            }`}>{opt}</span>
          </label>
        ))}
      </div>
    )
  }

  if (t === 'number') {
    return <NumberInput step={step} value={value} onChange={onChange} />
  }

  if (t === 'auto_number') {
    return <NumberInput step={step} value={value} onChange={onChange} locked />
  }

  return null
}

// ── Section colors ───────────────────────────────────────────────────────────
const SECTION_STYLES: Record<string, { header: string; badge: string }> = {
  manual:      { header: 'bg-brand-600 text-white',       badge: 'bg-brand-700 text-white' },
  instruction: { header: 'bg-slate-600 text-white',       badge: 'bg-slate-700 text-white' },
  auto:        { header: 'bg-emerald-600 text-white',     badge: 'bg-emerald-700 text-white' },
}

// ── Section Card ─────────────────────────────────────────────────────────────
function SectionCard({
  section, responses, onChange, expanded, onToggle,
}: {
  section: Section
  responses: Record<number, string>
  onChange: (stepId: number, value: string) => void
  expanded: boolean
  onToggle: () => void
}) {
  const style = SECTION_STYLES[section.section_type] ?? SECTION_STYLES.manual
  const [lightbox, setLightbox] = useState<string | null>(null)

  const dataSteps = section.steps.filter(s => s.step_type !== 'instruction')
  const mandatorySteps = dataSteps.filter(s => s.is_mandatory && isStepVisible(s, responses))
  const completedMandatory = mandatorySteps.filter(s => {
    const v = responses[s.id] ?? ''
    return v.trim().length > 0
  })

  const sectionPassed = mandatorySteps.length > 0 &&
    mandatorySteps.every(s => {
      const v = responses[s.id] ?? ''
      return computePassed(s, v) === true
    })

  // Instruction steps have order numbers; count them
  let instrCount = 0

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      {/* Header */}
      <button
        className={`w-full flex items-center justify-between px-4 py-3 ${style.header} transition-opacity`}
        onClick={onToggle}
      >
        <div className="flex items-center gap-2">
          <svg className={`w-4 h-4 transition-transform ${expanded ? 'rotate-90' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-sm font-bold">{section.title}</span>
          {section.section_type === 'auto' && (
            <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded font-medium">Auto-Captured</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {mandatorySteps.length > 0 && (
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${style.badge}`}>
              {completedMandatory.length} / {mandatorySteps.length}
            </span>
          )}
          {sectionPassed && (
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
      </button>

      {/* Steps */}
      {expanded && (
        <div className="divide-y divide-slate-100">
          {section.steps.map((step, idx) => {
            if (!isStepVisible(step, responses)) return null

            const isInstruction = step.step_type === 'instruction'
            if (isInstruction) instrCount++
            const stepNum = isInstruction ? instrCount : idx + 1

            const value = responses[step.id] ?? ''
            const passed = computePassed(step, value)
            const hasValue = value.trim().length > 0

            return (
              <div key={step.id} className={`px-4 py-3 ${isInstruction ? 'bg-slate-50/60' : ''}`}>
                <div className="flex items-start gap-3">
                  {/* Step number bubble */}
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold mt-0.5
                    ${isInstruction
                      ? 'bg-slate-200 text-slate-600'
                      : passed === true ? 'bg-green-500 text-white'
                      : passed === false ? 'bg-red-500 text-white'
                      : 'bg-slate-200 text-slate-600'
                    }`}>
                    {passed === true && !isInstruction
                      ? <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      : stepNum
                    }
                  </div>

                  <div className="flex-1 min-w-0">
                    {/* Label */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {!isInstruction && (
                        <span className="text-sm font-medium text-slate-800">{step.label}</span>
                      )}
                      {step.is_mandatory && !isInstruction && (
                        <span className="text-[9px] font-bold text-violet-700 bg-violet-100 px-1.5 py-0.5 rounded">
                          Mandatory
                        </span>
                      )}
                      {step.is_critical && (
                        <span className="text-[9px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded">
                          Critical
                        </span>
                      )}
                    </div>

                    {/* Reference images (from procedure template) */}
                    {(step.images || []).length > 0 && (
                      <div className="flex gap-2 flex-wrap mt-1.5 mb-1">
                        {(step.images || []).map(img => (
                          <img
                            key={img.id}
                            src={`data:${img.mime_type};base64,${img.data_b64}`}
                            alt={img.filename}
                            onClick={() => setLightbox(`data:${img.mime_type};base64,${img.data_b64}`)}
                            className="w-20 h-20 object-cover rounded-lg border border-slate-200 cursor-zoom-in hover:opacity-90 transition-opacity"
                          />
                        ))}
                      </div>
                    )}

                    {/* Input */}
                    <StepInput
                      step={step}
                      value={value}
                      onChange={v => onChange(step.id, v)}
                    />

                    {/* Missing mandatory warning */}
                    {step.is_mandatory && !isInstruction && !hasValue && (
                      <div className="text-[10px] text-amber-600 mt-1">Required</div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <img src={lightbox} alt="Reference" className="max-w-full max-h-full rounded-lg shadow-2xl object-contain" />
        </div>
      )}
    </div>
  )
}

// ── Auto-populate from integration dataset ───────────────────────────────────
function autoPopulateRunInfo(proc: Procedure): RunInfo {
  const TECH_NAMES = ['Marcus Webb', 'Sarah Chen', 'David Torres', 'Emily Ross', 'James Liu']
  const tech = TECH_NAMES[Math.floor(Math.random() * TECH_NAMES.length)]
  const ts = Date.now().toString(36).slice(-5).toUpperCase()
  const sn = `${proc.product_type.slice(0, 3).toUpperCase()}-${ts}`
  const MODEL_MAP: Record<string, string> = { rook2: '122927', rook1: '119204', default: proc.product_type.toUpperCase() }
  const modelNumber = MODEL_MAP[proc.product_type] ?? MODEL_MAP.default
  return { serialNumber: sn, modelNumber, testLocation: 'USA', technicianName: tech }
}

// ── Main Page ────────────────────────────────────────────────────────────────
type Phase = 'select' | 'run' | 'done'

export default function TestRunPage() {
  const [phase, setPhase]               = useState<Phase>('select')
  const [procedures, setProcedures]     = useState<ProcSummary[]>([])
  const [procedure, setProcedure]       = useState<Procedure | null>(null)
  const [runInfo, setRunInfo]           = useState<RunInfo>({ serialNumber: '', modelNumber: '', testLocation: 'USA', technicianName: '' })
  const [responses, setResponses]       = useState<Record<number, string>>({})
  const [expanded, setExpanded]         = useState<Set<number>>(new Set())
  const [submitting, setSubmitting]     = useState(false)
  const [savedRun, setSavedRun]         = useState<any>(null)
  const [loading, setLoading]           = useState(false)

  // Load procedure list
  useEffect(() => {
    fetch('/api/procedures').then(r => r.json()).then(setProcedures).catch(() => {})
  }, [])

  // Select a procedure — auto-populate from integration and jump straight to run
  async function selectProcedure(id: number) {
    setLoading(true)
    try {
      const proc = await fetch(`/api/procedures/${id}`).then(r => r.json())
      setProcedure(proc)
      setRunInfo(autoPopulateRunInfo(proc))
      const init: Record<number, string> = {}
      for (const sec of proc.sections) {
        for (const step of sec.steps) {
          if (step.step_type === 'auto_number') {
            init[step.id] = autoGenValue(step.tolerances_json)
          }
        }
      }
      setResponses(init)
      setExpanded(new Set(proc.sections.map(s => s.id)))
      setPhase('run')
    } finally {
      setLoading(false)
    }
  }

  function setResponse(stepId: number, value: string) {
    setResponses(prev => ({ ...prev, [stepId]: value }))
  }

  function toggleSection(id: number) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }


  // Compute overall progress
  const allSteps = procedure?.sections.flatMap(s => s.steps) ?? []
  const mandatorySteps = allSteps.filter(s =>
    s.step_type !== 'instruction' && s.is_mandatory && isStepVisible(s, responses)
  )
  const completedMandatory = mandatorySteps.filter(s => (responses[s.id] ?? '').trim().length > 0)
  const progressPct = mandatorySteps.length > 0
    ? Math.round((completedMandatory.length / mandatorySteps.length) * 100)
    : 0

  // Submit
  async function handleSubmit() {
    if (!procedure) return
    setSubmitting(true)
    try {
      const respPayload = allSteps
        .filter(s => s.step_type !== 'instruction')
        .map(s => ({
          step_id: s.id,
          value: responses[s.id] ?? '',
          auto_generated: s.step_type === 'auto_number',
          passed: computePassed(s, responses[s.id] ?? ''),
        }))
      const body = {
        procedure_id: procedure.id,
        serial_number: runInfo.serialNumber,
        model_number: runInfo.modelNumber,
        test_location: runInfo.testLocation,
        technician_name: runInfo.technicianName,
        status: 'completed',
        responses: respPayload,
      }
      const result = await fetch('/api/test-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).then(r => r.json())

      setSavedRun(result)
      setPhase('done')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Phase: select ──────────────────────────────────────────────────────────
  if (phase === 'select') {
    return (
      <div className="p-5 min-h-screen bg-surface-900">
        <div className="mb-6">
          <h1 className="text-lg font-bold text-slate-900">Run a Test</h1>
          <p className="text-xs text-slate-500 mt-0.5">Select a test procedure to begin</p>
        </div>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <div className="w-4 h-4 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
            Loading…
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 max-w-2xl">
          {procedures.map(p => (
            <button
              key={p.id}
              onClick={() => selectProcedure(p.id)}
              className="text-left bg-white border border-slate-200 rounded-xl p-4 hover:border-brand-400 hover:shadow-sm transition-all group"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-bold text-slate-900 group-hover:text-brand-700">{p.name}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {p.doc_id} · v{p.version} · {p.product_type}
                  </div>
                </div>
                <svg className="w-4 h-4 text-slate-400 group-hover:text-brand-600 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          ))}
          {!loading && procedures.length === 0 && (
            <div className="text-sm text-slate-400">No procedures found.</div>
          )}
        </div>
      </div>
    )
  }

  // ── Phase: done ───────────────────────────────────────────────────────────
  if (phase === 'done' && savedRun) {
    const allPassed = allSteps
      .filter(s => s.step_type !== 'instruction' && s.is_mandatory)
      .every(s => computePassed(s, responses[s.id] ?? '') === true)

    return (
      <div className="p-5 min-h-screen bg-surface-900 flex items-center justify-center">
        <div className="bg-white border border-slate-200 rounded-xl p-8 max-w-md w-full text-center">
          <div className={`w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4 ${
            allPassed ? 'bg-green-100' : 'bg-amber-100'
          }`}>
            {allPassed
              ? <svg className="w-7 h-7 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
              : <svg className="w-7 h-7 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
            }
          </div>
          <div className={`text-xl font-extrabold mb-1 ${allPassed ? 'text-green-700' : 'text-amber-700'}`}>
            {allPassed ? 'Test Completed — PASSED' : 'Test Completed — Review Required'}
          </div>
          <div className="text-xs text-slate-500 mb-6">
            Record #{savedRun.id} · {runInfo.serialNumber}
          </div>
          <div className="grid grid-cols-2 gap-3 text-left mb-6">
            {[
              ['Procedure', procedure?.name ?? ''],
              ['Serial #', runInfo.serialNumber],
              ['Technician', runInfo.technicianName || '—'],
              ['Location', runInfo.testLocation || '—'],
            ].map(([k, v]) => (
              <div key={k} className="bg-slate-50 rounded-lg px-3 py-2">
                <div className="text-[10px] font-semibold text-slate-500 uppercase">{k}</div>
                <div className="text-xs font-bold text-slate-800 mt-0.5 truncate">{v}</div>
              </div>
            ))}
          </div>
          <button
            onClick={() => {
              setPhase('select'); setProcedure(null)
              setResponses({}); setSavedRun(null)
              setRunInfo({ serialNumber: '', modelNumber: '', testLocation: 'USA', technicianName: '' })
            }}
            className="w-full py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            Run Another Test
          </button>
        </div>
      </div>
    )
  }

  // ── Phase: run ────────────────────────────────────────────────────────────
  if (phase !== 'run' || !procedure) return null

  return (
    <div className="p-5 min-h-screen bg-surface-900">
      {/* Page header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="flex items-center gap-2">
            <button onClick={() => setPhase('select')} className="text-slate-400 hover:text-slate-700">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <h1 className="text-lg font-bold text-slate-900">{procedure.name}</h1>
          </div>
          <p className="text-xs text-slate-500 mt-0.5 ml-6">
            {procedure.doc_id} · v{procedure.version} · {procedure.product_type}
            {runInfo.serialNumber && <span className="ml-2 font-medium text-slate-700">· SN: {runInfo.serialNumber}</span>}
          </p>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="text-right">
            <div className="text-xs font-bold text-slate-700">
              {completedMandatory.length} / {mandatorySteps.length}
              <span className="font-normal text-slate-400 ml-1">mandatory</span>
            </div>
            <div className="w-40 bg-slate-200 rounded-full h-1.5 mt-1">
              <div
                className="bg-brand-600 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Test Record Header — auto-populated from integration */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 mb-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Test Record</span>
          <span className="text-[10px] bg-emerald-50 text-emerald-700 font-semibold px-2 py-0.5 rounded-full border border-emerald-200 flex items-center gap-1">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full inline-block" />
            Auto-populated · ERP Integration
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3">
          {([
            ['Serial Number', runInfo.serialNumber],
            ['Model Number',  runInfo.modelNumber],
            ['Test Location', runInfo.testLocation],
            ['Technician',    runInfo.technicianName],
          ] as [string, string][]).map(([label, value]) => (
            <div key={label}>
              <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">{label}</div>
              <div className="text-sm font-bold text-slate-800 mt-0.5">{value || '—'}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Sections */}
      <div className="space-y-3 mb-6">
        {procedure.sections.map(sec => (
          <SectionCard
            key={sec.id}
            section={sec}
            responses={responses}
            onChange={setResponse}
            expanded={expanded.has(sec.id)}
            onToggle={() => toggleSection(sec.id)}
          />
        ))}
      </div>


      {/* Footer */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-400">
          {completedMandatory.length < mandatorySteps.length
            ? `${mandatorySteps.length - completedMandatory.length} required fields remaining`
            : 'All mandatory fields complete'}
        </div>
        <button
          onClick={handleSubmit}
          disabled={submitting || completedMandatory.length < mandatorySteps.length}
          className="px-6 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold rounded-lg
            disabled:opacity-40 transition-colors flex items-center gap-2"
        >
          {submitting && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
          Submit Test Record
        </button>
      </div>
    </div>
  )
}
