import { useEffect, useRef, useState } from 'react'

// ── Types ──────────────────────────────────────────────────────────────────────
interface MasterData {
  charDesignators: string[]
  tools: string[]
  sampleRates: string[]
  machinists: string[]
}

interface WoEntry {
  wo_number: string
  product: string
  part_number: string | null
}

interface TemplateItem {
  id: number
  name: string
  product: string | null
  part_number: string | null
  row_count: number
}

interface InspRow {
  id: number
  charDesig: string
  requirement: string
  tool: string
  sampleRate: string
  insp: string[]  // 9 values
  sn: string[]    // 2 serial numbers
}

interface FormHeader {
  product: string
  woNumber: string
  date: string
  partNumber: string
  serialNumber: string
  operation: string
  equipment: string
  machinist: string
}

interface ToolChangeRow {
  cells: string[]
  snCells: string[]
}

const INSP_COLS = ['1st Piece', '5th', '10th', '15th', '20th', '25th', '30th', '35th', 'IQA']

const DEFAULT_HEADER: FormHeader = {
  product: '', woNumber: '', date: new Date().toISOString().split('T')[0],
  partNumber: '', serialNumber: '', operation: '', equipment: '', machinist: '',
}

const emptyRow = (id: number): InspRow => ({
  id, charDesig: '', requirement: '', tool: '', sampleRate: '',
  insp: Array(9).fill(''), sn: ['', ''],
})

function passFail(v: string) {
  const lv = v.trim().toLowerCase()
  if (lv === 'pass' || lv === 'p') return 'pass'
  if (lv === 'fail' || lv === 'f') return 'fail'
  return ''
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function InspectionFormPage() {
  const [master, setMaster] = useState<MasterData>({
    charDesignators: [], tools: [], sampleRates: [], machinists: [],
  })
  const [woCatalog, setWoCatalog] = useState<WoEntry[]>([])
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [header, setHeader] = useState<FormHeader>(DEFAULT_HEADER)
  const [tcRow, setTcRow] = useState<ToolChangeRow>({
    cells: Array(9).fill(''), snCells: Array(9).fill(''),
  })
  const [rows, setRows] = useState<InspRow[]>(() =>
    Array.from({ length: 10 }, (_, i) => emptyRow(i + 1))
  )
  const [toast, setToast] = useState('')
  const [saving, setSaving] = useState(false)
  const [records, setRecords] = useState<any[]>([])
  const [loadingRecords, setLoadingRecords] = useState(false)
  const nextId = useRef(11)

  // Template picker
  const [showPicker, setShowPicker] = useState(false)
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerSelected, setPickerSelected] = useState<number | null>(null)
  const [pickerPreview, setPickerPreview] = useState<any | null>(null)
  const [pickerLoading, setPickerLoading] = useState(false)

  // ── Load master + catalog + templates ────────────────────────────────────
  useEffect(() => {
    fetch('/api/inspection/master')
      .then(r => r.json())
      .then(d => setMaster(d))
      .catch(() => setMaster({
        charDesignators: ['OD','ID','FLAT','//','TRUE','DIM','Major OD','Minor OD','Major ID','Minor ID','Roundness','Overall Height','Face Depth 1','Face Depth 2','Hole Diameter','THRD','O','TIR','VISUAL'],
        tools: ['Pins','Mics','Drop Gauge','T. Gauge','Dial Indicator','Verified by Machine Tool','Visual','Comparitor','Wires','Bore Mics','Thread Gauge','Calipers','Cannot Measure','Need to Define'],
        sampleRates: ['100%','Every 5th','None'],
        machinists: ['M. Kesel','R. Reid','T. Wagner','R. Appleton','M. Behrens'],
      }))
  }, [])

  useEffect(() => {
    fetch('/api/inspection/wo-catalog')
      .then(r => r.json())
      .then(d => setWoCatalog(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch('/api/inspection/templates')
      .then(r => r.json())
      .then(d => setTemplates(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    setLoadingRecords(true)
    fetch('/api/inspection/records?limit=20')
      .then(r => r.json())
      .then(d => setRecords(Array.isArray(d) ? d : []))
      .catch(() => setRecords([]))
      .finally(() => setLoadingRecords(false))
  }, [])

  // ── Helpers ───────────────────────────────────────────────────────────────
  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }

  function handleWoChange(wo: string) {
    const match = woCatalog.find(w => w.wo_number === wo)
    setHeader(prev => ({
      ...prev,
      woNumber: wo,
      ...(match ? {
        product: match.product,
        partNumber: match.part_number || prev.partNumber,
      } : {}),
    }))
  }

  // ── Row helpers ───────────────────────────────────────────────────────────
  function addRow() {
    setRows(prev => [...prev, emptyRow(nextId.current++)])
  }

  function updateRow(id: number, patch: Partial<InspRow>) {
    setRows(prev => prev.map(r => r.id === id ? { ...r, ...patch } : r))
  }

  function updateInsp(id: number, idx: number, val: string) {
    setRows(prev => prev.map(r => {
      if (r.id !== id) return r
      const insp = [...r.insp]; insp[idx] = val
      return { ...r, insp }
    }))
  }

  function updateSn(id: number, idx: number, val: string) {
    setRows(prev => prev.map(r => {
      if (r.id !== id) return r
      const sn = [...r.sn]; sn[idx] = val
      return { ...r, sn }
    }))
  }

  function updateTcCell(idx: number, val: string) {
    setTcRow(prev => {
      const cells = [...prev.cells]; cells[idx] = val
      return { ...prev, cells }
    })
  }

  function updateSnCell(idx: number, val: string) {
    setTcRow(prev => {
      const snCells = [...prev.snCells]; snCells[idx] = val
      return { ...prev, snCells }
    })
  }

  // ── Template picker ───────────────────────────────────────────────────────
  const filteredTemplates = templates.filter(t => {
    const q = pickerSearch.toLowerCase()
    return !q || t.name.toLowerCase().includes(q) || (t.product || '').toLowerCase().includes(q)
  })

  async function expandTemplate(id: number) {
    if (pickerSelected === id) { setPickerSelected(null); setPickerPreview(null); return }
    setPickerSelected(id)
    setPickerLoading(true)
    try {
      const res = await fetch(`/api/inspection/templates/${id}`)
      const data = await res.json()
      setPickerPreview(data)
    } finally {
      setPickerLoading(false)
    }
  }

  async function applyTemplate() {
    if (!pickerSelected || !pickerPreview) return
    const hasData = rows.some(r => r.charDesig || r.requirement)
    if (hasData && !confirm('This will replace the current rows. Continue?')) return

    const newRows: InspRow[] = (pickerPreview.rows || []).map((r: any, i: number) => ({
      id: i + 1,
      charDesig: r.char_designator || '',
      requirement: r.requirement || '',
      tool: r.tool || '',
      sampleRate: r.sample_rate || '',
      insp: Array(9).fill(''),
      sn: ['', ''],
    }))
    nextId.current = newRows.length + 1
    setRows(newRows.length > 0 ? newRows : Array.from({ length: 10 }, (_, i) => emptyRow(i + 1)))

    // Auto-fill header fields from template if currently empty
    setHeader(prev => ({
      ...prev,
      ...(pickerPreview.product && !prev.product ? { product: pickerPreview.product } : {}),
      ...(pickerPreview.part_number && !prev.partNumber ? { partNumber: pickerPreview.part_number } : {}),
      ...(pickerPreview.operation && !prev.operation ? { operation: pickerPreview.operation } : {}),
    }))

    setShowPicker(false)
    setPickerSelected(null)
    setPickerPreview(null)
    setPickerSearch('')
    showToast(`Template "${pickerPreview.name}" applied`)
  }

  // ── Save ──────────────────────────────────────────────────────────────────
  async function saveRecord() {
    setSaving(true)
    try {
      const payload = {
        header,
        tool_change: tcRow,
        rows: rows.map((r, i) => ({ row_number: i + 1, ...r })),
      }
      const res = await fetch('/api/inspection/records', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const saved = await res.json()
      showToast(`Record #${saved.id} saved`)
      const list = await fetch('/api/inspection/records?limit=20').then(r => r.json())
      setRecords(Array.isArray(list) ? list : [])
    } catch (e: any) {
      showToast('Save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  function clearForm() {
    if (!confirm('Clear all form data?')) return
    setHeader(DEFAULT_HEADER)
    setTcRow({ cells: Array(9).fill(''), snCells: Array(9).fill('') })
    nextId.current = 11
    setRows(Array.from({ length: 10 }, (_, i) => emptyRow(i + 1)))
    showToast('Form cleared')
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="p-5 min-h-screen bg-surface-900">
      {/* Page header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Inspection / Test Record</h1>
          <p className="text-xs text-slate-500 mt-0.5">Data entry · Saved to Lakebase</p>
        </div>
        <button
          onClick={() => setShowPicker(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:border-brand-500 hover:text-brand-700 transition-all shadow-sm"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 6h16M4 10h16M4 14h10" />
          </svg>
          Load Template
          {templates.length > 0 && (
            <span className="ml-1 bg-brand-100 text-brand-700 rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none">{templates.length}</span>
          )}
        </button>
      </div>

      {/* Header fields */}
      <div className="bg-white border border-slate-300 rounded-t mb-0 overflow-hidden">
        <div className="grid grid-cols-8 divide-x divide-slate-200 border-b border-slate-300">
          {/* W.O. Number — with datalist */}
          <div className="px-2 py-1.5">
            <span className="block text-[9px] text-slate-500 uppercase tracking-wide font-medium">W.O. Number:</span>
            <input
              list="wo-datalist"
              value={header.woNumber}
              onChange={e => handleWoChange(e.target.value)}
              placeholder="Select or type…"
              className="w-full border-0 border-b border-slate-200 text-xs font-bold text-slate-900 outline-none bg-transparent py-0.5 focus:border-brand-500"
            />
            <datalist id="wo-datalist">
              {woCatalog.map(w => (
                <option key={w.wo_number} value={w.wo_number}>{w.product}</option>
              ))}
            </datalist>
          </div>
          {/* Product — auto-filled */}
          <div className="px-2 py-1.5">
            <span className="block text-[9px] text-slate-500 uppercase tracking-wide font-medium">Product:</span>
            <input
              type="text"
              value={header.product}
              placeholder="Auto-filled from W.O."
              onChange={e => setHeader(prev => ({ ...prev, product: e.target.value }))}
              className="w-full border-0 border-b border-slate-200 text-xs font-bold text-slate-900 outline-none bg-transparent py-0.5 focus:border-brand-500"
            />
          </div>
          {[
            { label: 'Date:',          id: 'date'         as keyof FormHeader, type: 'date'  },
            { label: 'Part Number:',   id: 'partNumber'   as keyof FormHeader              },
            { label: 'Serial Number:', id: 'serialNumber' as keyof FormHeader              },
            { label: 'Operation:',     id: 'operation'    as keyof FormHeader              },
            { label: 'Equipment:',     id: 'equipment'    as keyof FormHeader              },
          ].map(f => (
            <div key={f.id} className="px-2 py-1.5">
              <span className="block text-[9px] text-slate-500 uppercase tracking-wide font-medium">{f.label}</span>
              <input
                type={f.type || 'text'}
                value={header[f.id]}
                onChange={e => setHeader(prev => ({ ...prev, [f.id]: e.target.value }))}
                className="w-full border-0 border-b border-slate-200 text-xs font-bold text-slate-900 outline-none bg-transparent py-0.5 focus:border-brand-500"
              />
            </div>
          ))}
          {/* Machinist */}
          <div className="px-2 py-1.5">
            <span className="block text-[9px] text-slate-500 uppercase tracking-wide font-medium">Machinist:</span>
            <select
              value={header.machinist}
              onChange={e => setHeader(prev => ({ ...prev, machinist: e.target.value }))}
              className="w-full border-0 border-b border-slate-200 text-xs font-bold text-slate-900 outline-none bg-transparent py-0.5 focus:border-brand-500 cursor-pointer"
            >
              <option value=""></option>
              {master.machinists.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Inspection table */}
      <div className="overflow-x-auto border border-t-0 border-slate-300 rounded-b bg-white">
        <table className="w-full border-collapse text-xs" style={{ minWidth: 1100 }}>
          <thead>
            <tr>
              <th colSpan={5} className="py-1.5 text-center text-xs font-bold border border-slate-300 bg-orange-200 text-slate-800">Characteristic</th>
              <th colSpan={9} className="py-1.5 text-center text-xs font-bold border border-slate-300 bg-orange-100 text-slate-800">Inspection / Test Results</th>
              <th rowSpan={3} className="py-1.5 text-center text-sm font-bold border border-slate-300 bg-blue-100 text-slate-800 w-20">SN LIST</th>
            </tr>
            <tr>
              <td colSpan={5} className="px-3 py-1 text-[10px] italic text-slate-600 border border-slate-300 bg-white">
                Tool Change? — If Yes, place a "Y" above the column
              </td>
              {tcRow.cells.map((v, i) => (
                <td key={i} className="border border-slate-300 bg-slate-100 p-0 w-14">
                  <input
                    value={v}
                    maxLength={1}
                    onChange={e => updateTcCell(i, e.target.value.toUpperCase())}
                    className="w-full h-7 text-center text-xs font-bold bg-transparent outline-none"
                    title={`${INSP_COLS[i]} — Tool Change`}
                  />
                </td>
              ))}
            </tr>
            <tr>
              <td colSpan={2} className="px-2 py-1 text-[10px] font-bold border border-slate-300 bg-white">SN</td>
              <td colSpan={3} className="border border-slate-300 bg-white"></td>
              {tcRow.snCells.map((v, i) => (
                <td key={i} className="border border-slate-300 bg-white p-0 w-14">
                  <input
                    value={v}
                    onChange={e => updateSnCell(i, e.target.value)}
                    className="w-full h-6 text-center text-[10px] bg-transparent outline-none"
                  />
                </td>
              ))}
            </tr>
            <tr className="bg-white">
              <th className="border border-slate-300 px-1 py-2 text-center text-[10px] font-bold text-slate-700 w-8">No.</th>
              <th className="border border-slate-300 px-1 py-2 text-center text-[10px] font-bold text-slate-700 w-24">Characteristic<br />Designator:</th>
              <th className="border border-slate-300 px-1 py-2 text-center text-[10px] font-bold text-slate-700 w-28">Requirement:</th>
              <th className="border border-slate-300 px-1 py-2 text-center text-[10px] font-bold text-slate-700 w-28">Tool</th>
              <th className="border border-slate-300 px-1 py-2 text-center text-[10px] font-bold text-slate-700 w-20">Sample<br />Rate:</th>
              {INSP_COLS.map(c => (
                <th key={c} className="border border-slate-300 px-1 py-2 text-center text-[10px] font-bold text-slate-700 w-14">{c}</th>
              ))}
              <th className="border border-slate-300 px-1 py-2 text-[10px] font-bold text-slate-700"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr key={row.id} className="h-11">
                <td className="border border-slate-300 text-center font-bold text-sm bg-white">{rowIdx + 1}</td>
                <td className="border border-slate-300 bg-white p-1">
                  <select
                    value={row.charDesig}
                    onChange={e => updateRow(row.id, { charDesig: e.target.value })}
                    className="w-full border border-slate-200 rounded text-xs font-bold outline-none cursor-pointer py-1 bg-white"
                  >
                    <option value=""></option>
                    {master.charDesignators.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </td>
                <td className="border border-slate-300 bg-white p-1">
                  <input
                    value={row.requirement}
                    onChange={e => updateRow(row.id, { requirement: e.target.value })}
                    placeholder="e.g. 0.87 ±0.005"
                    className="w-full border border-slate-200 rounded text-xs text-center outline-none py-1 px-1"
                  />
                </td>
                <td className="border border-slate-300 bg-white p-1">
                  <select
                    value={row.tool}
                    onChange={e => updateRow(row.id, { tool: e.target.value })}
                    className="w-full border border-slate-200 rounded text-xs outline-none cursor-pointer py-1 bg-white"
                  >
                    <option value=""></option>
                    {master.tools.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td className="border border-slate-300 bg-white p-1">
                  <select
                    value={row.sampleRate}
                    onChange={e => updateRow(row.id, { sampleRate: e.target.value })}
                    className="w-full border border-slate-200 rounded text-xs outline-none cursor-pointer py-1 bg-white"
                  >
                    <option value=""></option>
                    {master.sampleRates.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                {row.insp.map((v, ci) => {
                  const pf = passFail(v)
                  const bg = ci % 2 === 0 ? 'bg-slate-300' : 'bg-slate-200'
                  const color = pf === 'pass' ? 'text-green-800 font-bold' : pf === 'fail' ? 'text-red-800 font-bold text-[11px]' : 'text-slate-900 font-bold'
                  return (
                    <td key={ci} className={`border border-slate-300 ${bg} p-0 relative`}>
                      <div className="absolute top-0 left-0 w-0 h-0" style={{ borderTop: '8px solid #1565C0', borderRight: '8px solid transparent' }} />
                      <input
                        value={v}
                        onChange={e => updateInsp(row.id, ci, e.target.value)}
                        className={`w-full h-11 text-center text-xs bg-transparent outline-none ${color}`}
                        title={INSP_COLS[ci]}
                      />
                    </td>
                  )
                })}
                <td className="border border-slate-300 bg-white p-1 align-top">
                  <input
                    value={row.sn[0]}
                    onChange={e => updateSn(row.id, 0, e.target.value)}
                    placeholder="SN"
                    className="w-full border-b border-dotted border-slate-300 text-[10px] outline-none py-0.5 bg-transparent block"
                  />
                  <input
                    value={row.sn[1]}
                    onChange={e => updateSn(row.id, 1, e.target.value)}
                    placeholder="SN"
                    className="w-full border-b border-dotted border-slate-300 text-[10px] outline-none py-0.5 bg-transparent block mt-1"
                  />
                </td>
              </tr>
            ))}
            <tr>
              <td colSpan={15} className="bg-slate-50 text-center py-2">
                <button
                  onClick={addRow}
                  className="border border-dashed border-slate-400 rounded px-4 py-1 text-xs text-slate-500 hover:border-brand-500 hover:text-brand-600 transition-colors"
                >+ Add Row</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Action bar */}
      <div className="flex justify-between items-center mt-3">
        <button onClick={clearForm} className="px-3 py-1.5 text-xs font-semibold text-red-700 border border-red-300 rounded hover:bg-red-50 transition-colors">
          Clear Form
        </button>
        <div className="flex gap-2">
          <button onClick={() => window.print()} className="px-3 py-1.5 text-xs font-semibold text-slate-700 border border-slate-300 rounded hover:bg-slate-50 transition-colors">
            Print
          </button>
          <button
            onClick={saveRecord}
            disabled={saving}
            className="px-4 py-1.5 text-xs font-semibold bg-brand-600 text-white rounded hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >{saving ? 'Saving…' : 'Save Record'}</button>
        </div>
      </div>

      {/* Recent records */}
      {records.length > 0 && (
        <div className="mt-5">
          <div className="text-xs font-bold text-slate-700 uppercase tracking-wide mb-2">Recent Records</div>
          <div className="bg-white border border-slate-200 rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-50">
                <tr>
                  {['ID','Product','Part #','W.O.','Date','Machinist','Status'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide border-b border-slate-200">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loadingRecords
                  ? <tr><td colSpan={7} className="text-center py-6 text-slate-400">Loading…</td></tr>
                  : records.map(r => (
                    <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-3 py-2 font-bold text-slate-900">#{r.id}</td>
                      <td className="px-3 py-2 text-slate-700">{r.product || '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{r.part_number || '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{r.wo_number || '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{r.inspection_date || '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{r.machinist || '—'}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${r.status === 'complete' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'}`}>
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Template Picker Modal ── */}
      {showPicker && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => setShowPicker(false)}
        >
          <div
            className="bg-white rounded-xl border border-slate-200 shadow-xl w-[620px] max-h-[80vh] flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Load Inspection Template</h3>
                <p className="text-xs text-slate-500 mt-0.5">Select a template to populate the inspection rows</p>
              </div>
              <button onClick={() => setShowPicker(false)} className="text-slate-400 hover:text-slate-700 text-lg leading-none">✕</button>
            </div>
            {/* Search */}
            <div className="px-5 py-3 border-b border-slate-100">
              <input
                autoFocus
                value={pickerSearch}
                onChange={e => setPickerSearch(e.target.value)}
                placeholder="Search by name or product…"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs outline-none focus:border-brand-500"
              />
            </div>
            {/* List */}
            <div className="flex-1 overflow-y-auto px-5 py-3 space-y-2">
              {filteredTemplates.length === 0 && (
                <div className="text-center text-xs text-slate-400 py-8">
                  {pickerSearch ? 'No templates match your search' : 'No templates available. Create one in Admin → Templates.'}
                </div>
              )}
              {filteredTemplates.map(t => {
                const isSelected = pickerSelected === t.id
                const preview = isSelected ? pickerPreview : null
                return (
                  <div
                    key={t.id}
                    onClick={() => expandTemplate(t.id)}
                    className={`rounded-lg border p-3 cursor-pointer transition-all select-none
                      ${isSelected ? 'border-brand-400 bg-brand-50' : 'border-slate-200 hover:border-brand-300 hover:bg-slate-50'}`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="text-xs font-bold text-slate-900">{t.name}</span>
                        {t.product && (
                          <span className="ml-2 text-[10px] bg-slate-100 text-slate-600 rounded px-1.5 py-0.5 font-medium">{t.product}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-400">{t.row_count} rows</span>
                        <svg
                          className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isSelected ? 'rotate-180' : ''}`}
                          fill="none" viewBox="0 0 24 24" stroke="currentColor"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </div>
                    {/* Row preview */}
                    {isSelected && (
                      <div className="mt-3 border-t border-slate-200 pt-3">
                        {pickerLoading ? (
                          <div className="text-center text-xs text-slate-400 py-3">Loading preview…</div>
                        ) : preview?.rows?.length > 0 ? (
                          <table className="w-full text-[10px]">
                            <thead>
                              <tr className="text-slate-500">
                                <th className="text-left pb-1.5 pr-3 font-semibold w-6">#</th>
                                <th className="text-left pb-1.5 pr-3 font-semibold w-20">Char.</th>
                                <th className="text-left pb-1.5 pr-3 font-semibold">Requirement</th>
                                <th className="text-left pb-1.5 pr-3 font-semibold w-24">Tool</th>
                                <th className="text-left pb-1.5 font-semibold w-20">Sample Rate</th>
                              </tr>
                            </thead>
                            <tbody>
                              {preview.rows.map((r: any, i: number) => (
                                <tr key={i} className="border-t border-slate-100">
                                  <td className="py-1 pr-3 text-slate-400">{r.row_number}</td>
                                  <td className="py-1 pr-3 font-bold text-slate-800">{r.char_designator}</td>
                                  <td className="py-1 pr-3 text-slate-600">{r.requirement}</td>
                                  <td className="py-1 pr-3 text-slate-500">{r.tool}</td>
                                  <td className="py-1 text-slate-500">{r.sample_rate}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <div className="text-center text-xs text-slate-400 py-2">No rows defined</div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {/* Footer */}
            <div className="flex justify-end gap-2 px-5 py-4 border-t border-slate-200">
              <button
                onClick={() => setShowPicker(false)}
                className="px-3 py-1.5 text-xs text-slate-600 border border-slate-300 rounded hover:bg-slate-50 transition-colors"
              >Cancel</button>
              <button
                onClick={applyTemplate}
                disabled={!pickerSelected || pickerLoading}
                className="px-4 py-1.5 text-xs font-bold bg-brand-600 text-white rounded hover:bg-brand-700 disabled:opacity-50 transition-colors"
              >Apply Template</button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-5 right-5 bg-slate-900 text-white text-xs font-bold px-4 py-2.5 rounded-lg shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  )
}
