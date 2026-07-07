import { useEffect, useRef, useState } from 'react'

// ── Types ───────────────────────────────────────────────────────────────────
type StepType = 'instruction' | 'text' | 'radio' | 'number' | 'ok_check' | 'pass_fail' | 'auto_number' | 'photo'
type SectionType = 'manual' | 'instruction' | 'auto'

interface Tolerance {
  nominal?: number | ''
  lower?: number | ''
  upper?: number | ''
  unit?: string
}

interface StepRefImage { id: number; filename: string; mime_type: string; data_b64: string }

interface StepDraft {
  _key: string   // local identity
  id?: number    // DB id (set when editing existing procedure)
  step_type: StepType
  label: string
  options_json: string[]
  tolerances_json: Tolerance
  is_mandatory: boolean
  is_critical: boolean
  hint_text: string
  refImages?: StepRefImage[]
}

interface SectionDraft {
  _key: string
  id?: number    // DB id (set when editing existing procedure)
  title: string
  section_type: SectionType
  steps: StepDraft[]
}

interface ProcDraft {
  name: string
  doc_id: string
  version: string
  product_type: string
  description: string
  sections: SectionDraft[]
}

interface ProcSummary {
  id: number
  name: string
  doc_id: string
  version: string
  product_type: string
  created_at: string
}

// ── Default step template ────────────────────────────────────────────────────
const STEP_TYPE_LABELS: Record<StepType, string> = {
  instruction:  'Instruction (read-only)',
  text:         'Text Input',
  radio:        'Radio / Select',
  number:       'Number (manual)',
  ok_check:     'OK / Not OK',
  pass_fail:    'Pass / Fail',
  auto_number:  'Number (auto-captured)',
  photo:        'Photo Upload',
}

const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  manual:      'Manual',
  instruction: 'Instructions',
  auto:        'Automated',
}

const SECTION_COLORS: Record<SectionType, string> = {
  manual:      'bg-brand-600 text-white',
  instruction: 'bg-slate-500 text-white',
  auto:        'bg-emerald-600 text-white',
}

let _keyCounter = 1
function nextKey() { return String(_keyCounter++) }

function imageToJpeg(file: File): Promise<{ data_b64: string; mime_type: string; filename: string }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
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
      } catch (err) { URL.revokeObjectURL(url); reject(err) }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('This image format cannot be displayed in your browser. Please convert it to JPEG or PNG first (HEIC/HEIF files from iPhone are not supported in Chrome).'))
    }
    img.src = url
  })
}

function emptyStep(type: StepType = 'text'): StepDraft {
  return {
    _key: nextKey(),
    step_type: type,
    label: '',
    options_json: ['Option A', 'Option B'],
    tolerances_json: {},
    is_mandatory: true,
    is_critical: false,
    hint_text: '',
  }
}

function emptySection(): SectionDraft {
  return {
    _key: nextKey(),
    title: 'New Section',
    section_type: 'manual',
    steps: [],
  }
}

function emptyProc(): ProcDraft {
  return {
    name: '',
    doc_id: '',
    version: '1.0',
    product_type: '',
    description: '',
    sections: [],
  }
}

// ── Step Row Editor ──────────────────────────────────────────────────────────
function StepEditor({
  step, onChange, onDelete, index,
}: {
  step: StepDraft
  onChange: (s: StepDraft) => void
  onDelete: () => void
  index: number
}) {
  const [open, setOpen] = useState(false)
  const [uploadingImg, setUploadingImg] = useState(false)
  const [imgError, setImgError] = useState<string | null>(null)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const imgInputRef = useRef<HTMLInputElement>(null)

  function set<K extends keyof StepDraft>(k: K, v: StepDraft[K]) {
    onChange({ ...step, [k]: v })
  }
  function setTol(k: keyof Tolerance, v: string | number) {
    onChange({ ...step, tolerances_json: { ...step.tolerances_json, [k]: v } })
  }
  function addOption() { set('options_json', [...step.options_json, '']) }
  function setOption(i: number, v: string) {
    const next = [...step.options_json]; next[i] = v; set('options_json', next)
  }
  function removeOption(i: number) {
    set('options_json', step.options_json.filter((_, j) => j !== i))
  }

  const hasTol = ['number', 'auto_number'].includes(step.step_type)
  const hasOpts = step.step_type === 'radio'

  return (
    <div className="border border-slate-200 rounded-lg bg-white">
      {/* Compact header row */}
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="text-[10px] font-bold text-slate-400 w-5 text-center">{index + 1}</span>

        {/* Type badge */}
        <span className="text-[10px] font-semibold bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded flex-shrink-0">
          {step.step_type}
        </span>

        {/* Label preview */}
        <span className="flex-1 text-xs text-slate-700 truncate min-w-0">
          {step.label || <span className="text-slate-300 italic">Untitled step</span>}
        </span>

        <div className="flex items-center gap-1 flex-shrink-0">
          {step.is_mandatory && (
            <span className="text-[9px] font-bold text-violet-600 bg-violet-50 px-1 py-0.5 rounded">M</span>
          )}
          {step.is_critical && (
            <span className="text-[9px] font-bold text-red-600 bg-red-50 px-1 py-0.5 rounded">C</span>
          )}
          <button onClick={() => setOpen(o => !o)} className="p-1 text-slate-400 hover:text-slate-700 rounded">
            <svg className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
          <button onClick={onDelete} className="p-1 text-slate-300 hover:text-red-500 rounded">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Expanded editor */}
      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-slate-100 space-y-3">
          {/* Type + flags */}
          <div className="flex gap-3 flex-wrap">
            <div className="flex-1 min-w-40">
              <label className="block text-[10px] font-semibold text-slate-500 mb-1">Step Type</label>
              <select
                value={step.step_type}
                onChange={e => set('step_type', e.target.value as StepType)}
                className="border border-slate-300 rounded px-2 py-1 text-xs w-full focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {(Object.entries(STEP_TYPE_LABELS) as [StepType, string][]).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div className="flex items-end gap-3 pb-0.5">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={step.is_mandatory}
                  onChange={e => set('is_mandatory', e.target.checked)}
                  className="accent-brand-600 w-3.5 h-3.5" />
                <span className="text-xs text-slate-600">Mandatory</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={step.is_critical}
                  onChange={e => set('is_critical', e.target.checked)}
                  className="accent-red-500 w-3.5 h-3.5" />
                <span className="text-xs text-slate-600">Critical</span>
              </label>
            </div>
          </div>

          {/* Label */}
          <div>
            <label className="block text-[10px] font-semibold text-slate-500 mb-1">
              {step.step_type === 'instruction' ? 'Instruction Text' : 'Label / Question'}
            </label>
            <textarea
              value={step.label}
              onChange={e => set('label', e.target.value)}
              rows={step.step_type === 'instruction' ? 3 : 2}
              placeholder={step.step_type === 'instruction' ? 'Enter instruction text…' : 'Enter field label…'}
              className="border border-slate-300 rounded px-2.5 py-1.5 text-xs w-full resize-none
                focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {/* Hint text */}
          {step.step_type !== 'instruction' && (
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 mb-1">Hint / Subtext (optional)</label>
              <input
                type="text"
                value={step.hint_text}
                onChange={e => set('hint_text', e.target.value)}
                placeholder="Helper text shown under the input"
                className="border border-slate-300 rounded px-2.5 py-1 text-xs w-full
                  focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          )}

          {/* Radio options */}
          {hasOpts && (
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 mb-1">Options</label>
              <div className="space-y-1.5">
                {step.options_json.map((opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={opt}
                      onChange={e => setOption(i, e.target.value)}
                      className="flex-1 border border-slate-300 rounded px-2 py-1 text-xs
                        focus:outline-none focus:ring-1 focus:ring-brand-500"
                      placeholder={`Option ${i + 1}`}
                    />
                    <button onClick={() => removeOption(i)} className="text-slate-300 hover:text-red-500">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
                <button onClick={addOption}
                  className="text-[10px] text-brand-600 hover:text-brand-800 font-medium">
                  + Add option
                </button>
              </div>
            </div>
          )}

          {/* Tolerances */}
          {hasTol && (
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 mb-1.5">Tolerances</label>
              <div className="grid grid-cols-4 gap-2">
                {(['nominal', 'lower', 'upper'] as const).map(k => (
                  <div key={k}>
                    <div className="text-[9px] text-slate-400 mb-0.5 capitalize">{k}</div>
                    <input
                      type="number"
                      step="any"
                      value={step.tolerances_json[k] ?? ''}
                      onChange={e => setTol(k, e.target.value === '' ? '' : parseFloat(e.target.value))}
                      placeholder="—"
                      className="border border-slate-300 rounded px-2 py-1 text-xs w-full
                        focus:outline-none focus:ring-1 focus:ring-brand-500"
                    />
                  </div>
                ))}
                <div>
                  <div className="text-[9px] text-slate-400 mb-0.5">Unit</div>
                  <input
                    type="text"
                    value={step.tolerances_json.unit ?? ''}
                    onChange={e => setTol('unit', e.target.value)}
                    placeholder="mm, psi…"
                    className="border border-slate-300 rounded px-2 py-1 text-xs w-full
                      focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Reference Images */}
          <div>
            <label className="block text-[10px] font-semibold text-slate-500 mb-1.5">Reference Images</label>
            {step.id ? (
              <>
                {(step.refImages || []).length > 0 && (
                  <div className="flex gap-2 flex-wrap mb-2">
                    {(step.refImages || []).map(img => (
                      <div key={img.id} className="relative group">
                        <img
                          src={`data:${img.mime_type};base64,${img.data_b64}`}
                          alt={img.filename}
                          onClick={() => setLightboxSrc(`data:${img.mime_type};base64,${img.data_b64}`)}
                          className="w-16 h-16 object-cover rounded-lg border border-slate-200 cursor-zoom-in hover:opacity-90 transition-opacity"
                        />
                        <button
                          onClick={async () => {
                            await fetch(`/api/proc-step-images/${img.id}`, { method: 'DELETE' })
                            onChange({ ...step, refImages: (step.refImages || []).filter(i => i.id !== img.id) })
                          }}
                          className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full text-[9px] font-bold hidden group-hover:flex items-center justify-center"
                        >×</button>
                      </div>
                    ))}
                  </div>
                )}
                <button
                  onClick={() => imgInputRef.current?.click()}
                  disabled={uploadingImg}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 border border-dashed border-slate-300 rounded-lg text-[10px] font-medium text-slate-500 hover:border-brand-400 hover:text-brand-600 transition-colors disabled:opacity-50"
                >
                  {uploadingImg ? (
                    <div className="w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  )}
                  Add Reference Image
                </button>
                <input
                  ref={imgInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={async e => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    setImgError(null)
                    setUploadingImg(true)
                    try {
                      const { data_b64, mime_type, filename } = await imageToJpeg(file)
                      const res = await fetch(`/api/proc-steps/${step.id}/images`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ filename, mime_type, data_b64 }),
                      }).then(r => r.json())
                      if (!res.error) {
                        onChange({ ...step, refImages: [...(step.refImages || []), res] })
                      }
                    } catch (err: any) {
                      setImgError(err?.message || 'Upload failed')
                    } finally {
                      setUploadingImg(false)
                      if (imgInputRef.current) imgInputRef.current.value = ''
                    }
                  }}
                />
              {imgError && (
                <p className="mt-1.5 text-[10px] text-red-600 bg-red-50 border border-red-200 rounded-lg px-2 py-1.5">{imgError}</p>
              )}
              </>
            ) : (
              <p className="text-[10px] text-slate-400 italic">Save the procedure first to add reference images.</p>
            )}
          </div>
        </div>
      )}
      {lightboxSrc && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setLightboxSrc(null)}
        >
          <img src={lightboxSrc} alt="Reference" className="max-w-full max-h-full rounded-lg shadow-2xl object-contain" />
        </div>
      )}
    </div>
  )
}

// ── Section Editor ────────────────────────────────────────────────────────────
function SectionEditor({
  section, onChange, onDelete, index,
}: {
  section: SectionDraft
  onChange: (s: SectionDraft) => void
  onDelete: () => void
  index: number
}) {
  function set<K extends keyof SectionDraft>(k: K, v: SectionDraft[K]) {
    onChange({ ...section, [k]: v })
  }
  function addStep() {
    onChange({ ...section, steps: [...section.steps, emptyStep()] })
  }
  function updateStep(i: number, s: StepDraft) {
    const next = [...section.steps]; next[i] = s; onChange({ ...section, steps: next })
  }
  function deleteStep(i: number) {
    onChange({ ...section, steps: section.steps.filter((_, j) => j !== i) })
  }

  const colorClass = SECTION_COLORS[section.section_type] ?? SECTION_COLORS.manual

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      {/* Section header */}
      <div className={`flex items-center gap-3 px-4 py-3 ${colorClass}`}>
        <span className="text-xs font-bold opacity-60">{index + 1}</span>
        <input
          type="text"
          value={section.title}
          onChange={e => set('title', e.target.value)}
          className="flex-1 bg-transparent text-sm font-bold placeholder-white/50 border-none outline-none"
          placeholder="Section title"
        />
        <select
          value={section.section_type}
          onChange={e => set('section_type', e.target.value as SectionType)}
          className="bg-white/20 text-white text-[10px] font-semibold rounded px-1.5 py-0.5 border-none outline-none cursor-pointer"
        >
          {(Object.entries(SECTION_TYPE_LABELS) as [SectionType, string][]).map(([k, v]) => (
            <option key={k} value={k} className="bg-slate-800 text-white">{v}</option>
          ))}
        </select>
        <button onClick={onDelete} className="p-1 opacity-60 hover:opacity-100 rounded">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>

      {/* Steps */}
      <div className="p-3 space-y-2 bg-slate-50/50">
        {section.steps.map((step, i) => (
          <StepEditor
            key={step._key}
            step={step}
            index={i}
            onChange={s => updateStep(i, s)}
            onDelete={() => deleteStep(i)}
          />
        ))}
        <button
          onClick={addStep}
          className="w-full py-2 border border-dashed border-slate-300 rounded-lg text-xs font-medium
            text-slate-500 hover:border-brand-400 hover:text-brand-600 transition-colors"
        >
          + Add Step
        </button>
      </div>
    </div>
  )
}

// ── Serialise draft → API payload ────────────────────────────────────────────
function draftToPayload(draft: ProcDraft) {
  return {
    name: draft.name,
    doc_id: draft.doc_id,
    version: draft.version,
    product_type: draft.product_type,
    description: draft.description,
    sections: draft.sections.map((sec, si) => ({
      id: sec.id,
      title: sec.title,
      section_type: sec.section_type,
      order_index: si + 1,
      steps: sec.steps.map((step, sti) => ({
        id: step.id,
        step_type: step.step_type,
        label: step.label,
        options_json: step.options_json,
        tolerances_json: step.tolerances_json,
        is_mandatory: step.is_mandatory,
        is_critical: step.is_critical,
        condition_json: null,
        hint_text: step.hint_text || null,
        order_index: sti + 1,
      })),
    })),
  }
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function ProcedureBuilderPage() {
  const [procedures, setProcedures] = useState<ProcSummary[]>([])
  const [draft, setDraft]           = useState<ProcDraft | null>(null)
  const [editingId, setEditingId]   = useState<number | 'new' | null>(null)
  const [saving, setSaving]         = useState(false)
  const [saveMsg, setSaveMsg]       = useState<string | null>(null)
  const [loading, setLoading]       = useState(true)

  async function loadList() {
    setLoading(true)
    try {
      const rows = await fetch('/api/procedures').then(r => r.json())
      setProcedures(Array.isArray(rows) ? rows : [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadList() }, [])

  async function selectProcedure(id: number) {
    const proc = await fetch(`/api/procedures/${id}`).then(r => r.json())
    // Map to draft
    const d: ProcDraft = {
      name: proc.name,
      doc_id: proc.doc_id ?? '',
      version: proc.version ?? '',
      product_type: proc.product_type ?? '',
      description: proc.description ?? '',
      sections: (proc.sections ?? []).map((sec: any) => ({
        _key: nextKey(),
        id: sec.id,
        title: sec.title,
        section_type: sec.section_type,
        steps: (sec.steps ?? []).map((step: any) => ({
          _key: nextKey(),
          id: step.id,
          step_type: step.step_type,
          label: step.label,
          options_json: step.options_json ?? [],
          tolerances_json: step.tolerances_json ?? {},
          is_mandatory: step.is_mandatory ?? true,
          is_critical: step.is_critical ?? false,
          hint_text: step.hint_text ?? '',
          refImages: step.images ?? [],
        })),
      })),
    }
    setDraft(d)
    setEditingId(id)
    setSaveMsg(null)
  }

  function newProcedure() {
    setDraft(emptyProc())
    setEditingId('new')
    setSaveMsg(null)
  }

  function setDraftField<K extends keyof ProcDraft>(k: K, v: ProcDraft[K]) {
    setDraft(d => d ? { ...d, [k]: v } : d)
  }

  function addSection() {
    setDraft(d => d ? { ...d, sections: [...d.sections, emptySection()] } : d)
  }
  function updateSection(i: number, sec: SectionDraft) {
    setDraft(d => {
      if (!d) return d
      const next = [...d.sections]; next[i] = sec
      return { ...d, sections: next }
    })
  }
  function deleteSection(i: number) {
    setDraft(d => d ? { ...d, sections: d.sections.filter((_, j) => j !== i) } : d)
  }

  async function saveProcedure() {
    if (!draft) return
    setSaving(true)
    setSaveMsg(null)
    try {
      const payload = draftToPayload(draft)
      const isNew = editingId === 'new'
      const url = isNew ? '/api/procedures' : `/api/procedures/${editingId}`
      const method = isNew ? 'POST' : 'PUT'
      const result = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then(r => r.json())
      if (result.error) {
        setSaveMsg(`Error: ${result.error}`)
      } else {
        const savedId = isNew ? result.id : (editingId as number)
        await loadList()
        await selectProcedure(savedId)  // Re-fetch to populate step IDs for image uploads
        setSaveMsg('Saved successfully') // Re-set after selectProcedure clears it
      }
    } catch (e: any) {
      setSaveMsg(`Error: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  async function deleteProcedure(id: number) {
    if (!confirm('Archive this procedure?')) return
    await fetch(`/api/procedures/${id}`, { method: 'DELETE' })
    if (editingId === id) { setDraft(null); setEditingId(null) }
    loadList()
  }

  const mandatoryCount = draft?.sections.flatMap(s => s.steps)
    .filter(s => s.is_mandatory && s.step_type !== 'instruction').length ?? 0

  return (
    <div className="flex h-full min-h-screen bg-surface-900">
      {/* ── Left: Procedure list ── */}
      <div className="w-72 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-slate-900">Procedures</div>
            <div className="text-[10px] text-slate-400">{procedures.length} defined</div>
          </div>
          <button
            onClick={newProcedure}
            className="flex items-center gap-1 px-2.5 py-1.5 bg-brand-600 hover:bg-brand-700
              text-white text-xs font-semibold rounded-lg transition-colors"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            New
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {loading && (
            <div className="px-4 py-3 text-xs text-slate-400">Loading…</div>
          )}
          {!loading && procedures.length === 0 && (
            <div className="px-4 py-3 text-xs text-slate-400">No procedures yet.</div>
          )}
          {procedures.map(p => (
            <div
              key={p.id}
              className={`group flex items-start gap-2 px-4 py-3 cursor-pointer border-l-2 transition-colors
                ${editingId === p.id
                  ? 'border-brand-600 bg-brand-50'
                  : 'border-transparent hover:bg-slate-50'}`}
              onClick={() => selectProcedure(p.id)}
            >
              <div className="flex-1 min-w-0">
                <div className={`text-xs font-semibold truncate ${editingId === p.id ? 'text-brand-700' : 'text-slate-800'}`}>
                  {p.name}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {p.doc_id} · v{p.version}
                </div>
                {p.product_type && (
                  <span className="text-[9px] bg-slate-100 text-slate-500 px-1 py-0.5 rounded mt-1 inline-block">
                    {p.product_type}
                  </span>
                )}
              </div>
              <button
                onClick={e => { e.stopPropagation(); deleteProcedure(p.id) }}
                className="opacity-0 group-hover:opacity-100 p-1 text-slate-300 hover:text-red-500 transition-all flex-shrink-0"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: Editor ── */}
      {!draft ? (
        <div className="flex-1 flex items-center justify-center text-slate-400">
          <div className="text-center">
            <svg className="w-10 h-10 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <div className="text-sm font-medium">Select a procedure to edit</div>
            <div className="text-xs mt-1 opacity-70">or create a new one</div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-5">
          {/* Metadata bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4">
            <div className="flex items-start justify-between mb-3">
              <div className="text-sm font-bold text-slate-900">
                {editingId === 'new' ? 'New Procedure' : 'Edit Procedure'}
              </div>
              <div className="flex items-center gap-2">
                {saveMsg && (
                  <span className={`text-xs font-medium ${saveMsg.startsWith('Error') ? 'text-red-600' : 'text-green-700'}`}>
                    {saveMsg}
                  </span>
                )}
                <button
                  onClick={saveProcedure}
                  disabled={saving || !draft.name}
                  className="px-4 py-1.5 bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold
                    rounded-lg disabled:opacity-40 transition-colors flex items-center gap-1.5"
                >
                  {saving && <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                  Save
                </button>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-3 sm:col-span-1">
                <label className="block text-[10px] font-semibold text-slate-500 mb-1">Procedure Name *</label>
                <input
                  type="text"
                  value={draft.name}
                  onChange={e => setDraftField('name', e.target.value)}
                  placeholder="e.g. Rook2 Blower Test Record"
                  className="border border-slate-300 rounded-md px-2.5 py-1.5 text-xs w-full
                    focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 mb-1">Document ID</label>
                <input type="text" value={draft.doc_id}
                  onChange={e => setDraftField('doc_id', e.target.value)}
                  placeholder="QA-WI-148"
                  className="border border-slate-300 rounded-md px-2.5 py-1.5 text-xs w-full
                    focus:outline-none focus:ring-1 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 mb-1">Version</label>
                <input type="text" value={draft.version}
                  onChange={e => setDraftField('version', e.target.value)}
                  placeholder="1.0"
                  className="border border-slate-300 rounded-md px-2.5 py-1.5 text-xs w-full
                    focus:outline-none focus:ring-1 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 mb-1">Product Type</label>
                <input type="text" value={draft.product_type}
                  onChange={e => setDraftField('product_type', e.target.value)}
                  placeholder="rook2"
                  className="border border-slate-300 rounded-md px-2.5 py-1.5 text-xs w-full
                    focus:outline-none focus:ring-1 focus:ring-brand-500" />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] font-semibold text-slate-500 mb-1">Description</label>
                <input type="text" value={draft.description}
                  onChange={e => setDraftField('description', e.target.value)}
                  placeholder="Optional description"
                  className="border border-slate-300 rounded-md px-2.5 py-1.5 text-xs w-full
                    focus:outline-none focus:ring-1 focus:ring-brand-500" />
              </div>
            </div>
            {/* Summary badges */}
            <div className="flex items-center gap-3 mt-3 pt-3 border-t border-slate-100">
              <span className="text-[10px] text-slate-500">
                <span className="font-bold text-slate-700">{draft.sections.length}</span> sections
              </span>
              <span className="text-[10px] text-slate-500">
                <span className="font-bold text-slate-700">
                  {draft.sections.reduce((n, s) => n + s.steps.length, 0)}
                </span> total steps
              </span>
              <span className="text-[10px] text-slate-500">
                <span className="font-bold text-slate-700">{mandatoryCount}</span> mandatory
              </span>
            </div>
          </div>

          {/* Sections */}
          <div className="space-y-3 mb-4">
            {draft.sections.map((sec, i) => (
              <SectionEditor
                key={sec._key}
                section={sec}
                index={i}
                onChange={s => updateSection(i, s)}
                onDelete={() => deleteSection(i)}
              />
            ))}
          </div>

          <button
            onClick={addSection}
            className="w-full py-2.5 border-2 border-dashed border-slate-300 rounded-xl text-sm
              font-medium text-slate-500 hover:border-brand-400 hover:text-brand-600 transition-colors"
          >
            + Add Section
          </button>
        </div>
      )}
    </div>
  )
}
