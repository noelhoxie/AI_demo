import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

// ── Helpers ────────────────────────────────────────────────────────────────────
function imageToJpeg(file: File): Promise<{ data_b64: string; mime_type: string; filename: string }> {
  return new Promise(resolve => {
    const url = URL.createObjectURL(file)
    const fallback = () => {
      URL.revokeObjectURL(url)
      const reader = new FileReader()
      reader.onload = () => resolve({ data_b64: (reader.result as string).split(',')[1], mime_type: file.type || 'image/jpeg', filename: file.name })
      reader.onerror = () => resolve({ data_b64: '', mime_type: file.type || 'image/jpeg', filename: file.name })
      reader.readAsDataURL(file)
    }
    const img = new Image()
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        const MAX = 1600
        let w = img.naturalWidth, h = img.naturalHeight
        if (w > MAX || h > MAX) { const r = Math.min(MAX / w, MAX / h); w = Math.round(w * r); h = Math.round(h * r) }
        canvas.width = w; canvas.height = h
        canvas.getContext('2d')!.drawImage(img, 0, 0, w, h)
        URL.revokeObjectURL(url)
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85)
        resolve({ data_b64: dataUrl.split(',')[1], mime_type: 'image/jpeg', filename: file.name.replace(/\.[^.]+$/, '.jpg') })
      } catch { fallback() }
    }
    img.onerror = fallback
    img.src = url
  })
}

// ── Types ──────────────────────────────────────────────────────────────────────
interface Tol { nominal?: number; lower?: number; upper?: number; unit?: string }
interface Step {
  id: number
  step_type: string
  label: string
  options_json: string[]
  tolerances_json: Tol
  is_mandatory: boolean
  is_critical: boolean
  order_index: number
  hint_text?: string
}
interface Section { id: number; title: string; section_type: string; steps: Step[]; order_index: number }
interface Response { step_id: number; value: string; auto_generated: boolean; passed: boolean | null }
interface RunImage { id: number; step_id: number | null; section_id: number | null; filename: string; mime_type: string; data_b64: string; caption: string | null; created_at: string }
interface RunDetail {
  id: number
  procedure_id: number
  procedure_name: string
  serial_number: string
  model_number: string
  test_location: string
  technician_name: string
  status: string
  created_at: string
  sections: Section[]
  responses: Response[]
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function statusStyle(s: string) {
  if (s === 'completed') return 'bg-green-100 text-green-800 border-green-200'
  if (s === 'failed')    return 'bg-red-100 text-red-800 border-red-200'
  return 'bg-blue-100 text-blue-800 border-blue-200'
}
function secStyle(t: string) {
  if (t === 'auto')        return 'border-emerald-200 bg-emerald-50'
  if (t === 'instruction') return 'border-slate-200 bg-slate-50'
  return 'border-blue-200 bg-blue-50'
}
function secBadge(t: string) {
  if (t === 'auto')        return 'bg-emerald-200 text-emerald-800'
  if (t === 'instruction') return 'bg-slate-200 text-slate-600'
  return 'bg-blue-200 text-blue-800'
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate  = useNavigate()

  const [run,        setRun]        = useState<RunDetail | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [generating, setGenerating] = useState(false)
  const [flashOk,    setFlashOk]    = useState(false)
  const [images,     setImages]     = useState<RunImage[]>([])
  const [uploading,         setUploading]         = useState<number | null>(null)   // step_id or 0 for run-level
  const [uploadingSection,  setUploadingSection]  = useState<number | null>(null)  // section_id
  const [uploadError,       setUploadError]       = useState<string | null>(null)
  const [lightbox,   setLightbox]   = useState<RunImage | null>(null)
  const [editMeta,   setEditMeta]   = useState({ serial_number: '', model_number: '', test_location: '', technician_name: '' })
  const [savingMeta, setSavingMeta] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadStepRef    = useRef<number | null>(null)   // which step_id to attach upload to
  const uploadSectionRef = useRef<number | null>(null)   // which section_id to attach upload to

  async function load() {
    setLoading(true)
    try {
      const [runData, imgs] = await Promise.all([
        fetch(`/api/test-runs/${runId}`).then(r => r.json()),
        fetch(`/api/test-runs/${runId}/images`).then(r => r.json()),
      ])
      setRun(runData)
      setEditMeta({
        serial_number:   runData.serial_number   || '',
        model_number:    runData.model_number    || '',
        test_location:   runData.test_location   || '',
        technician_name: runData.technician_name || '',
      })
      setImages(Array.isArray(imgs) ? imgs : [])
    } finally {
      setLoading(false)
    }
  }

  async function generate() {
    setGenerating(true)
    try {
      await fetch(`/api/test-runs/${runId}/generate`, { method: 'POST' })
      setFlashOk(true)
      await load()
      setTimeout(() => setFlashOk(false), 4000)
    } finally {
      setGenerating(false)
    }
  }

  function triggerUpload(stepId: number | null, sectionId: number | null = null) {
    uploadStepRef.current = stepId
    uploadSectionRef.current = sectionId
    fileInputRef.current?.click()
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const stepId    = uploadStepRef.current
    const sectionId = uploadSectionRef.current
    setUploadError(null)
    if (sectionId !== null) setUploadingSection(sectionId)
    else setUploading(stepId ?? 0)
    try {
      const { data_b64, mime_type, filename } = await imageToJpeg(file)
      const res = await fetch(`/api/test-runs/${runId}/images`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId, section_id: uploadSectionRef.current, filename, mime_type, data_b64 }),
      })
      if (res.ok) {
        const imgs = await fetch(`/api/test-runs/${runId}/images`).then(r => r.json())
        setImages(Array.isArray(imgs) ? imgs : [])
      }
    } catch (err: any) {
      setUploadError(err?.message || 'Upload failed')
    } finally {
      setUploading(null)
      setUploadingSection(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function deleteImage(imgId: number) {
    await fetch(`/api/test-run-images/${imgId}`, { method: 'DELETE' })
    setImages(prev => prev.filter(i => i.id !== imgId))
  }

  async function saveMeta(field: keyof typeof editMeta, value: string) {
    setSavingMeta(true)
    try {
      await fetch(`/api/test-runs/${runId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      })
      setRun(prev => prev ? { ...prev, [field]: value } : prev)
    } finally {
      setSavingMeta(false)
    }
  }

  useEffect(() => { load() }, [runId])

  // ── Loading / error ──────────────────────────────────────────────────────────
  if (loading) return (
    <div className="p-5 min-h-screen bg-surface-900 flex items-center justify-center">
      <div className="w-7 h-7 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  if (!run) return (
    <div className="p-5"><div className="text-sm text-red-600">Test run not found.</div></div>
  )

  const respMap      = new Map((run.responses || []).map(r => [r.step_id, r]))
  const hasResponses = (run.responses || []).length > 0
  const totalSteps   = (run.sections || []).flatMap(s => s.steps).filter(st => st.step_type !== 'instruction').length
  const passedSteps  = (run.responses || []).filter(r => r.passed === true).length

  return (
    <div className="p-5 min-h-screen bg-surface-900">

      {/* ── Header ── */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 mb-2 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back
          </button>
          <h1 className="text-lg font-bold text-slate-900">{run.procedure_name}</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Run #{run.id} · {run.serial_number || 'No serial'} · {run.model_number || '—'}
          </p>
        </div>
        <div className="flex items-center gap-3 mt-1">
          <span className={`px-3 py-1.5 rounded-lg text-xs font-bold border ${statusStyle(run.status)}`}>
            {run.status}
          </span>
          {!hasResponses && (
            <button
              onClick={generate}
              disabled={generating}
              className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white text-xs font-bold rounded-lg hover:bg-brand-700 disabled:opacity-60 transition-colors shadow-sm"
            >
              {generating ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Generate Data
                </>
              )}
            </button>
          )}
          {hasResponses && (
            <button
              onClick={generate}
              disabled={generating}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-60 transition-colors shadow-sm"
            >
              {generating ? (
                <div className="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              )}
              Regenerate
            </button>
          )}
        </div>
      </div>

      {/* ── Pre-Test Information ── */}
      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 mb-3">
        <div className="flex items-center justify-between mb-2.5">
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">Pre-Test Information</h3>
          {savingMeta && (
            <div className="flex items-center gap-1.5 text-[10px] text-brand-600">
              <div className="w-3 h-3 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
              Saving…
            </div>
          )}
        </div>
        <div className="grid grid-cols-4 gap-3">
          {([
            ['serial_number',   'Serial Number'],
            ['model_number',    'Model Number'],
            ['test_location',   'Test Location'],
            ['technician_name', 'Technician Name'],
          ] as const).map(([field, label]) => (
            <div key={field}>
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1">{label}</label>
              <input
                className="w-full text-sm font-semibold text-slate-800 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-brand-400 focus:bg-white transition-colors"
                value={editMeta[field]}
                onChange={e => setEditMeta(prev => ({ ...prev, [field]: e.target.value }))}
                onBlur={e => saveMeta(field, e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                placeholder={`Enter ${label.toLowerCase()}…`}
              />
            </div>
          ))}
        </div>
      </div>

      {/* ── Run Stats ── */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        {[
          ['Date',     run.created_at?.slice(0, 10) || '—'],
          ['Progress', hasResponses ? `${passedSteps} / ${totalSteps} steps passed` : 'No data yet'],
        ].map(([label, value]) => (
          <div key={label} className="bg-white border border-slate-200 rounded-xl px-4 py-3">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-0.5">{label}</div>
            <div className="text-sm font-semibold text-slate-800">{value}</div>
          </div>
        ))}
      </div>

      {/* ── Success flash ── */}
      {flashOk && (
        <div className="mb-4 flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-xl text-xs text-green-700 font-medium">
          <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
          Data generated — all steps auto-filled with passing values.
        </div>
      )}

      {/* ── Empty state ── */}
      {!hasResponses && !generating && (
        <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-700">
          No response data recorded for this run. Click <strong>Generate Data</strong> to auto-fill all steps with passing values.
        </div>
      )}

      {/* ── Sections ── */}
      <div className="space-y-4">
        {(run.sections || []).map(sec => (
          <div key={sec.id} className={`rounded-xl border p-4 ${secStyle(sec.section_type)}`}>
            {/* Section header */}
            <div className="flex items-center gap-2 mb-3">
              <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${secBadge(sec.section_type)}`}>
                {sec.section_type}
              </span>
              <h3 className="text-sm font-bold text-slate-800 flex-1">{sec.title}</h3>
              <button
                onClick={() => triggerUpload(null, sec.id)}
                disabled={uploadingSection === sec.id}
                title="Add section photo"
                className="flex items-center gap-1 px-2 py-1 bg-white/70 border border-slate-200 text-slate-500 hover:text-brand-600 hover:border-brand-300 text-[10px] font-semibold rounded-lg transition-colors"
              >
                {uploadingSection === sec.id ? (
                  <div className="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                )}
                Add Photo
              </button>
            </div>

            {/* Section photos (shown before steps, like reference images in test docs) */}
            {images.filter(i => i.section_id === sec.id && i.step_id === null).length > 0 && (
              <div className="flex gap-2 flex-wrap mb-3 pb-3 border-b border-white/60">
                {images.filter(i => i.section_id === sec.id && i.step_id === null).map(img => (
                  <div key={img.id} className="relative group">
                    <img
                      src={`data:${img.mime_type};base64,${img.data_b64}`}
                      alt={img.filename}
                      className="w-20 h-20 object-cover rounded-lg border border-white shadow-sm cursor-pointer hover:opacity-90 transition-opacity"
                      onClick={() => setLightbox(img)}
                    />
                    <div className="absolute bottom-0 left-0 right-0 bg-black/40 text-white text-[8px] truncate px-1 py-0.5 rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
                      {img.filename}
                    </div>
                    <button
                      onClick={() => deleteImage(img.id)}
                      className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full text-[9px] font-bold hidden group-hover:flex items-center justify-center shadow"
                    >×</button>
                  </div>
                ))}
              </div>
            )}

            {/* Steps */}
            <div className="space-y-1.5">
              {sec.steps.map(step => {
                if (step.step_type === 'instruction') return (
                  <div key={step.id} className="text-[11px] text-slate-500 italic py-1 px-2 leading-relaxed">
                    {step.label}
                  </div>
                )

                // ── Photo step ─────────────────────────────────────────────
                if (step.step_type === 'photo') {
                  const stepImgs = images.filter(img => img.step_id === step.id)
                  return (
                    <div key={step.id} className="bg-white/70 rounded-lg px-3 py-2.5">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-xs text-slate-700 font-medium">{step.label}</div>
                        <button
                          onClick={() => triggerUpload(step.id)}
                          disabled={uploading === step.id}
                          className="flex items-center gap-1 px-2.5 py-1 bg-brand-600 text-white text-[10px] font-bold rounded-lg hover:bg-brand-700 disabled:opacity-60 transition-colors"
                        >
                          {uploading === step.id ? (
                            <div className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
                          ) : (
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                          )}
                          Add Photo
                        </button>
                      </div>
                      {stepImgs.length > 0 && (
                        <div className="flex gap-2 flex-wrap">
                          {stepImgs.map(img => (
                            <div key={img.id} className="relative group">
                              <img
                                src={`data:${img.mime_type};base64,${img.data_b64}`}
                                alt={img.filename}
                                className="w-16 h-16 object-cover rounded-lg border border-slate-200 cursor-pointer hover:opacity-90"
                                onClick={() => setLightbox(img)}
                              />
                              <button
                                onClick={() => deleteImage(img.id)}
                                className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full text-[9px] font-bold hidden group-hover:flex items-center justify-center"
                              >×</button>
                            </div>
                          ))}
                        </div>
                      )}
                      {stepImgs.length === 0 && (
                        <div className="text-[10px] text-slate-300 italic">No photos uploaded</div>
                      )}
                    </div>
                  )
                }

                // ── Standard step ──────────────────────────────────────────
                const resp = respMap.get(step.id)
                const tol  = step.tolerances_json
                const hasTol = tol && (tol.lower !== undefined || tol.upper !== undefined)
                return (
                  <div key={step.id} className="flex items-center gap-3 bg-white/70 rounded-lg px-3 py-2.5">
                    {/* Label */}
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-slate-700 font-medium truncate">{step.label}</div>
                      {hasTol && (
                        <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                          {tol.lower} – {tol.upper}{tol.unit ? ` ${tol.unit}` : ''}
                        </div>
                      )}
                    </div>
                    {/* Value */}
                    <div className="text-right flex-shrink-0 min-w-[80px]">
                      {resp ? (
                        <span className={`text-xs font-bold ${resp.passed !== false ? 'text-green-700' : 'text-red-600'}`}>
                          {resp.value}{tol?.unit && step.step_type !== 'ok_check' && step.step_type !== 'pass_fail' && step.step_type !== 'radio' && step.step_type !== 'text' ? ` ${tol.unit}` : ''}
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-300 italic">no data</span>
                      )}
                    </div>
                    {/* Pass/fail icon */}
                    <div className="w-5 flex-shrink-0 flex justify-center">
                      {resp && resp.passed === true && (
                        <svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                      {resp && resp.passed === false && (
                        <svg className="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* ── Run-level Photos ── */}
      <div className="mt-4 bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">
            Run Photos ({images.filter(i => i.step_id === null && i.section_id === null).length})
          </h3>
          <button
            onClick={() => triggerUpload(null)}
            disabled={uploading === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-xs font-semibold rounded-lg hover:bg-brand-700 disabled:opacity-60 transition-colors shadow-sm"
          >
            {uploading === 0 ? (
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            )}
            Upload Photo
          </button>
        </div>
        {images.filter(i => i.step_id === null && i.section_id === null).length > 0 ? (
          <div className="flex gap-3 flex-wrap">
            {images.filter(i => i.step_id === null && i.section_id === null).map(img => (
              <div key={img.id} className="relative group">
                <img
                  src={`data:${img.mime_type};base64,${img.data_b64}`}
                  alt={img.filename}
                  className="w-24 h-24 object-cover rounded-xl border border-slate-200 cursor-pointer hover:opacity-90 transition-opacity"
                  onClick={() => setLightbox(img)}
                />
                <button
                  onClick={() => deleteImage(img.id)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-[10px] font-bold hidden group-hover:flex items-center justify-center shadow"
                >×</button>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center py-6 text-slate-400">
            <svg className="w-8 h-8 mb-2 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span className="text-xs">No photos yet — upload images from the test</span>
          </div>
        )}
      </div>

      {/* ── Hidden file input ── */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />
      {uploadError && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 max-w-md w-full mx-4 bg-red-50 border border-red-300 text-red-700 text-xs rounded-xl px-4 py-3 shadow-lg flex items-start gap-2">
          <span className="mt-0.5 shrink-0">⚠</span>
          <span>{uploadError}</span>
          <button onClick={() => setUploadError(null)} className="ml-auto shrink-0 text-red-400 hover:text-red-600 font-bold">×</button>
        </div>
      )}

      {/* ── Lightbox ── */}
      {lightbox && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <div className="relative max-w-3xl w-full" onClick={e => e.stopPropagation()}>
            <img
              src={`data:${lightbox.mime_type};base64,${lightbox.data_b64}`}
              alt={lightbox.filename}
              className="w-full rounded-xl shadow-2xl"
            />
            <div className="flex items-center justify-between mt-3">
              <span className="text-white/70 text-xs">{lightbox.filename}</span>
              <button
                onClick={() => setLightbox(null)}
                className="px-3 py-1.5 bg-white/20 text-white text-xs rounded-lg hover:bg-white/30"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
