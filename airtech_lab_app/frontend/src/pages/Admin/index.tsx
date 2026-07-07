import { useEffect, useRef, useState } from 'react'
import * as XLSX from 'xlsx'

// ── Types ──────────────────────────────────────────────────────────────────────
interface MasterData {
  charDesignators: string[]
  tools: string[]
  sampleRates: string[]
  machinists: string[]
}

interface WoEntry {
  id: number
  wo_number: string
  product: string
  part_number: string | null
  description: string | null
  is_active: boolean
}

interface Template {
  id: number
  name: string
  product: string | null
  part_number: string | null
  description: string | null
  operation: string | null
  is_active: boolean
  row_count?: number
}

interface TmplRow {
  rowKey: number
  charDesig: string
  requirement: string
  tool: string
  sampleRate: string
}

const FALLBACK_MASTER: MasterData = {
  charDesignators: ['OD','ID','FLAT','//','TRUE','DIM','Major OD','Minor OD','Major ID','Minor ID','Roundness','Overall Height','Face Depth 1','Face Depth 2','Hole Diameter','THRD','O','TIR','VISUAL'],
  tools: ['Pins','Mics','Drop Gauge','T. Gauge','Dial Indicator','Verified by Machine Tool','Visual','Comparitor','Wires','Bore Mics','Thread Gauge','Calipers','Cannot Measure','Need to Define'],
  sampleRates: ['100%','Every 5th','None'],
  machinists: ['M. Kesel','R. Reid','T. Wagner','R. Appleton','M. Behrens'],
}

const emptyTmplRow = (key: number): TmplRow => ({
  rowKey: key, charDesig: '', requirement: '', tool: '', sampleRate: '',
})

// ── Import Tab ────────────────────────────────────────────────────────────────
interface InspRow {
  char_designator: string; requirement: string; tool: string; sample_rate: string
  piece_1st: string; piece_5th: string; piece_10th: string; piece_15th: string
  piece_20th: string; piece_25th: string; piece_30th: string; piece_35th: string
  piece_iqa: string
}
interface ImportRecord {
  product: string; wo_number: string; inspection_date: string
  part_number: string; serial_number: string; operation: string
  equipment: string; machinist: string; rows: InspRow[]
}

const IMPORT_COLS = [
  'Record Group', 'Product', 'W.O. Number', 'Date', 'Part Number',
  'Serial Number', 'Operation', 'Equipment', 'Machinist',
  'Char Designator', 'Requirement', 'Tool', 'Sample Rate',
  '1st Piece', '5th Piece', '10th Piece', '15th Piece', '20th Piece',
  '25th Piece', '30th Piece', '35th Piece', 'IQA',
]
const EXAMPLE_ROWS = [
  [1, 'HOUSING, 5X', 'WO-2025-1001', '2025-06-01', 'AT-10051', '', 'Final Inspection', 'HAAS VF-2', 'M. Kesel',
   'OD', '3.750 ±0.001', 'Mics', '100%', 'Pass', '', '', '', '', '', '', '', ''],
  [1, 'HOUSING, 5X', 'WO-2025-1001', '2025-06-01', 'AT-10051', '', 'Final Inspection', 'HAAS VF-2', 'M. Kesel',
   'ID', '2.500 +0.0005/-0.0000', 'Bore Mics', '100%', 'Pass', '', '', '', '', '', '', '', ''],
]

function formatDate(val: unknown): string {
  if (!val) return ''
  if (val instanceof Date) return val.toISOString().split('T')[0]
  if (typeof val === 'number') {
    const d = new Date(Math.round((val - 25569) * 86400 * 1000))
    return d.toISOString().split('T')[0]
  }
  const s = String(val).trim()
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toISOString().split('T')[0]
}
function strVal(val: unknown): string {
  return val === null || val === undefined ? '' : String(val).trim()
}
function parseSheet(rawRows: Record<string, unknown>[]): ImportRecord[] {
  const groups = new Map<string, ImportRecord>()
  rawRows.forEach((row, idx) => {
    const key = strVal(row['Record Group'] ?? row['Record#'] ?? row['Record #'] ?? idx)
    if (!groups.has(key)) {
      groups.set(key, {
        product:         strVal(row['Product']),
        wo_number:       strVal(row['W.O. Number'] ?? row['WO Number'] ?? row['WO#']),
        inspection_date: formatDate(row['Date']),
        part_number:     strVal(row['Part Number']),
        serial_number:   strVal(row['Serial Number']),
        operation:       strVal(row['Operation']),
        equipment:       strVal(row['Equipment']),
        machinist:       strVal(row['Machinist']),
        rows: [],
      })
    }
    const rec = groups.get(key)!
    rec.rows.push({
      char_designator: strVal(row['Char Designator']),
      requirement:     strVal(row['Requirement']),
      tool:            strVal(row['Tool']),
      sample_rate:     strVal(row['Sample Rate']),
      piece_1st:       strVal(row['1st Piece']),
      piece_5th:       strVal(row['5th Piece']),
      piece_10th:      strVal(row['10th Piece']),
      piece_15th:      strVal(row['15th Piece']),
      piece_20th:      strVal(row['20th Piece']),
      piece_25th:      strVal(row['25th Piece']),
      piece_30th:      strVal(row['30th Piece']),
      piece_35th:      strVal(row['35th Piece']),
      piece_iqa:       strVal(row['IQA']),
    })
  })
  return Array.from(groups.values())
}
function downloadImportTemplate() {
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet([IMPORT_COLS, ...EXAMPLE_ROWS])
  ws['!cols'] = IMPORT_COLS.map((_, i) => ({ wch: i === 0 ? 14 : i <= 8 ? 20 : 16 }))
  XLSX.utils.book_append_sheet(wb, ws, 'Inspections')
  XLSX.writeFile(wb, 'inspection_import_template.xlsx')
}

function ImportTab() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging,   setDragging]   = useState(false)
  const [fileName,   setFileName]   = useState('')
  const [records,    setRecords]    = useState<ImportRecord[]>([])
  const [parseError, setParseError] = useState('')
  const [importing,  setImporting]  = useState(false)
  const [result,     setResult]     = useState<{ imported: number; errors: { record: number; error: string }[] } | null>(null)
  const [toast,      setToast]      = useState('')

  function showToast(msg: string) { setToast(msg); setTimeout(() => setToast(''), 3500) }

  function handleFile(file: File) {
    setParseError(''); setRecords([]); setResult(null); setFileName(file.name)
    const reader = new FileReader()
    reader.onload = e => {
      try {
        const data = new Uint8Array(e.target!.result as ArrayBuffer)
        const wb   = XLSX.read(data, { type: 'array', cellDates: true })
        const ws   = wb.Sheets[wb.SheetNames[0]]
        const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(ws, { defval: '' })
        if (rows.length === 0) { setParseError('The file appears to be empty.'); return }
        const parsed = parseSheet(rows)
        if (parsed.length === 0) { setParseError('No records found. Check column headers match the template.'); return }
        setRecords(parsed)
      } catch (err) { setParseError(`Could not parse file: ${err}`) }
    }
    reader.readAsArrayBuffer(file)
  }

  async function doImport() {
    setImporting(true); setResult(null)
    try {
      const res  = await fetch('/api/inspection/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(records),
      })
      const data = await res.json()
      setResult(data)
      if (data.imported > 0) showToast(`${data.imported} record${data.imported !== 1 ? 's' : ''} imported successfully`)
    } catch { setParseError('Import failed — could not reach the server.') }
    finally { setImporting(false) }
  }

  function reset() {
    setFileName(''); setRecords([]); setParseError(''); setResult(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const totalRows = records.reduce((s, r) => s + r.rows.length, 0)

  return (
    <div>
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-600 text-white text-sm font-semibold px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>
      )}

      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-xs text-slate-500">Upload an Excel or CSV file to bulk-load inspection records into Lakebase</p>
        </div>
        <button
          onClick={downloadImportTemplate}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download Template
        </button>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5">
        <div className="flex gap-3">
          <svg className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-xs text-blue-800 space-y-1">
            <p className="font-semibold">How to import:</p>
            <ol className="list-decimal list-inside space-y-0.5 text-blue-700">
              <li>Download the template and fill it in (Excel .xlsx or .csv)</li>
              <li>Each row = one measurement. Use the same <strong>Record Group</strong> number for rows in the same inspection form</li>
              <li>Required columns: <strong>Record Group, Product, Machinist</strong></li>
              <li>Upload below, review the preview, then click Import</li>
            </ol>
          </div>
        </div>
      </div>

      {records.length === 0 && !parseError && (
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center cursor-pointer transition-all mb-5
            ${dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-slate-50'}`}
        >
          <svg className="w-10 h-10 text-slate-400 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p className="text-sm font-semibold text-slate-700 mb-1">Drop your file here, or click to browse</p>
          <p className="text-xs text-slate-500">Supports Excel (.xlsx, .xls) and CSV (.csv)</p>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
            onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]) }} />
        </div>
      )}

      {parseError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-5 flex items-start gap-3">
          <svg className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-sm font-semibold text-red-700">{parseError}</p>
            <button onClick={reset} className="text-xs text-red-600 underline mt-1">Try another file</button>
          </div>
        </div>
      )}

      {records.length > 0 && !result && (
        <>
          <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div>
                <div className="text-xl font-extrabold text-slate-900">{records.length}</div>
                <div className="text-xs text-slate-500">Inspection Records</div>
              </div>
              <div>
                <div className="text-xl font-extrabold text-slate-900">{totalRows}</div>
                <div className="text-xs text-slate-500">Measurement Rows</div>
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-700 truncate max-w-48">{fileName}</div>
                <div className="text-xs text-slate-500">Source file</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={reset} className="px-3 py-1.5 text-xs font-semibold border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-600">Change File</button>
              <button onClick={doImport} disabled={importing}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-60 transition-colors">
                {importing
                  ? <><div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />Importing…</>
                  : <>Import {records.length} Records</>}
              </button>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">Preview (first 10 records)</h3>
              <span className="text-[10px] text-slate-400">{records.length} total</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50">
                  <tr>{['#','Product','W.O. Number','Date','Part #','Machinist','Operation','Rows'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {records.slice(0, 10).map((r, i) => (
                    <tr key={i} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-3 py-2 font-bold text-slate-500">{i + 1}</td>
                      <td className="px-3 py-2 font-medium text-slate-800">{r.product || '—'}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-slate-600">{r.wo_number || '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{r.inspection_date || '—'}</td>
                      <td className="px-3 py-2 text-slate-500">{r.part_number || '—'}</td>
                      <td className="px-3 py-2 text-slate-700">{r.machinist || '—'}</td>
                      <td className="px-3 py-2 text-slate-500 text-[10px]">{r.operation || '—'}</td>
                      <td className="px-3 py-2"><span className="px-2 py-0.5 bg-slate-100 rounded-full text-[10px] font-bold text-slate-600">{r.rows.length}</span></td>
                    </tr>
                  ))}
                  {records.length > 10 && (
                    <tr className="border-t border-slate-100">
                      <td colSpan={8} className="px-3 py-2 text-center text-xs text-slate-400">+{records.length - 10} more records not shown</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {result && (
        <div className="space-y-4">
          <div className={`rounded-xl border p-5 ${result.errors.length === 0 ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'}`}>
            <div className="flex items-center gap-3 mb-2">
              {result.errors.length === 0
                ? <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                : <svg className="w-5 h-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
              <div>
                <p className={`text-sm font-bold ${result.errors.length === 0 ? 'text-green-800' : 'text-amber-800'}`}>
                  {result.imported} record{result.imported !== 1 ? 's' : ''} imported successfully
                  {result.errors.length > 0 && `, ${result.errors.length} failed`}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">Records are now visible on the Quality Dashboard</p>
              </div>
            </div>
          </div>
          {result.errors.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <h3 className="text-xs font-bold text-red-600 uppercase tracking-wide">Import Errors</h3>
              </div>
              <table className="w-full text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">Record #</th>
                    <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((e, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-3 py-2 font-bold text-slate-700">{e.record}</td>
                      <td className="px-3 py-2 text-red-600">{e.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <button onClick={reset} className="px-4 py-2 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700">
            Import Another File
          </button>
        </div>
      )}
    </div>
  )
}

// ── PIN Lock ───────────────────────────────────────────────────────────────────
function PinLock({ onAuth }: { onAuth: () => void }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState(false)
  const [adminPin, setAdminPin] = useState('')

  useEffect(() => {
    fetch('/api/inspection/master')
      .then(r => r.json())
      .then(d => setAdminPin(d.adminPin || '1234'))
      .catch(() => setAdminPin('1234'))
  }, [])

  function check() {
    if (pin === adminPin) {
      sessionStorage.setItem('airtech_admin', 'true')
      onAuth()
    } else {
      setError(true)
      setTimeout(() => setError(false), 600)
      setPin('')
    }
  }

  return (
    <div className="min-h-screen bg-surface-900 flex items-center justify-center">
      <div className="bg-white rounded-xl border border-slate-200 shadow-lg p-8 w-80">
        <div className="flex justify-center mb-4">
          <div className="w-12 h-12 rounded-full bg-brand-600 flex items-center justify-center">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
        </div>
        <h2 className="text-center text-base font-bold text-slate-900 mb-1">Admin Configuration</h2>
        <p className="text-center text-xs text-slate-500 mb-5">Enter your admin PIN to continue</p>
        <input
          type="password"
          value={pin}
          onChange={e => setPin(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && check()}
          placeholder="PIN"
          maxLength={20}
          className={`w-full border rounded-lg px-3 py-2.5 text-center text-lg tracking-widest font-bold outline-none mb-3 transition-all
            ${error ? 'border-red-400 bg-red-50 text-red-700' : 'border-slate-300 focus:border-brand-500'}`}
        />
        {error && <p className="text-center text-xs text-red-600 mb-2">Incorrect PIN</p>}
        <button
          onClick={check}
          className="w-full bg-brand-600 text-white rounded-lg py-2 text-sm font-bold hover:bg-brand-700 transition-colors"
        >Unlock</button>
        <p className="text-center text-[10px] text-slate-400 mt-3">Default PIN: 1234</p>
      </div>
    </div>
  )
}

// ── Admin Content ──────────────────────────────────────────────────────────────
type AdminTab = 'master' | 'wo' | 'templates' | 'import' | 'security'

function AdminContent({ onLock }: { onLock: () => void }) {
  const [tab, setTab] = useState<AdminTab>('master')
  const [master, setMaster] = useState<MasterData>(FALLBACK_MASTER)
  const [adminPin, setAdminPin] = useState('1234')
  const [woCatalog, setWoCatalog] = useState<WoEntry[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [toast, setToast] = useState('')

  // Master config inputs
  const [configInputs, setConfigInputs] = useState<Record<string, string>>({})

  // WO editing
  const [editingWo, setEditingWo] = useState<number | null>(null)
  const [editWoData, setEditWoData] = useState<Partial<WoEntry>>({})
  const [newWo, setNewWo] = useState({ wo_number: '', product: '', part_number: '' })

  // Template editing
  const [selectedTmpl, setSelectedTmpl] = useState<number | null>(null)
  const [tmplForm, setTmplForm] = useState({ name: '', product: '', part_number: '', description: '', operation: '' })
  const [tmplRows, setTmplRows] = useState<TmplRow[]>(() => Array.from({ length: 5 }, (_, i) => emptyTmplRow(i + 1)))
  const [showingEditor, setShowingEditor] = useState(false)
  const [tmplSaving, setTmplSaving] = useState(false)
  const tmplNextKey = useRef(6)

  // Security
  const [currentPin, setCurrentPin] = useState('')
  const [newPin1, setNewPin1] = useState('')
  const [newPin2, setNewPin2] = useState('')

  useEffect(() => { loadAll() }, [])

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }

  async function loadAll() {
    const [mData, woData, tmplData] = await Promise.all([
      fetch('/api/inspection/master').then(r => r.json()).catch(() => FALLBACK_MASTER),
      fetch('/api/inspection/wo-catalog?active=0').then(r => r.json()).catch(() => []),
      fetch('/api/inspection/templates').then(r => r.json()).catch(() => []),
    ])
    setMaster({ ...FALLBACK_MASTER, ...mData })
    setAdminPin(typeof mData.adminPin === 'string' ? mData.adminPin : '1234')
    setWoCatalog(Array.isArray(woData) ? woData : [])
    setTemplates(Array.isArray(tmplData) ? tmplData : [])
  }

  // ── Master helpers ────────────────────────────────────────────────────────
  async function saveMasterItem(key: keyof MasterData, items: string[]) {
    setMaster(prev => ({ ...prev, [key]: items }))
    await fetch('/api/inspection/master', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: items }),
    }).catch(() => {})
    showToast('Saved')
  }

  // ── WO helpers ────────────────────────────────────────────────────────────
  async function addWo() {
    if (!newWo.wo_number.trim() || !newWo.product.trim()) {
      showToast('WO Number and Product are required'); return
    }
    const res = await fetch('/api/inspection/wo-catalog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newWo),
    })
    if (res.ok) {
      setNewWo({ wo_number: '', product: '', part_number: '' })
      await loadAll()
      showToast('Work order added')
    } else {
      showToast('Error: WO number may already exist')
    }
  }

  async function saveWoEdit() {
    if (!editingWo) return
    await fetch(`/api/inspection/wo-catalog/${editingWo}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editWoData),
    })
    setEditingWo(null)
    await loadAll()
    showToast('Updated')
  }

  async function toggleWoActive(id: number, current: boolean) {
    await fetch(`/api/inspection/wo-catalog/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !current }),
    })
    await loadAll()
  }

  // ── Template helpers ──────────────────────────────────────────────────────
  async function loadTemplate(id: number) {
    const res = await fetch(`/api/inspection/templates/${id}`)
    if (!res.ok) return
    const tmpl = await res.json()
    setSelectedTmpl(id)
    setTmplForm({
      name: tmpl.name || '',
      product: tmpl.product || '',
      part_number: tmpl.part_number || '',
      description: tmpl.description || '',
      operation: tmpl.operation || '',
    })
    const rows: TmplRow[] = (tmpl.rows || []).map((r: any, i: number) => ({
      rowKey: i + 1,
      charDesig: r.char_designator || '',
      requirement: r.requirement || '',
      tool: r.tool || '',
      sampleRate: r.sample_rate || '',
    }))
    tmplNextKey.current = rows.length + 1
    setTmplRows(rows.length > 0 ? rows : Array.from({ length: 5 }, (_, i) => emptyTmplRow(i + 1)))
    setShowingEditor(true)
  }

  function newTemplate() {
    setSelectedTmpl(null)
    setTmplForm({ name: '', product: '', part_number: '', description: '', operation: '' })
    tmplNextKey.current = 6
    setTmplRows(Array.from({ length: 5 }, (_, i) => emptyTmplRow(i + 1)))
    setShowingEditor(true)
  }

  async function saveTemplate() {
    if (!tmplForm.name.trim()) { showToast('Template name is required'); return }
    setTmplSaving(true)
    const payload = {
      ...tmplForm,
      rows: tmplRows
        .filter(r => r.charDesig || r.requirement)
        .map((r, i) => ({
          row_number: i + 1,
          char_designator: r.charDesig,
          requirement: r.requirement,
          tool: r.tool,
          sample_rate: r.sampleRate,
        })),
    }
    try {
      if (selectedTmpl) {
        await fetch(`/api/inspection/templates/${selectedTmpl}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        showToast('Template updated')
      } else {
        const res = await fetch('/api/inspection/templates', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (res.ok) {
          const created = await res.json()
          setSelectedTmpl(created.id)
          showToast('Template saved')
        }
      }
      await loadAll()
    } finally {
      setTmplSaving(false)
    }
  }

  async function deleteTemplate(id: number) {
    if (!confirm('Delete this template?')) return
    await fetch(`/api/inspection/templates/${id}`, { method: 'DELETE' })
    if (selectedTmpl === id) { setShowingEditor(false); setSelectedTmpl(null) }
    await loadAll()
    showToast('Template deleted')
  }

  function addTmplRow() {
    setTmplRows(prev => [...prev, emptyTmplRow(tmplNextKey.current++)])
  }

  function updateTmplRow(idx: number, patch: Partial<TmplRow>) {
    setTmplRows(prev => prev.map((r, i) => i === idx ? { ...r, ...patch } : r))
  }

  function removeTmplRow(idx: number) {
    setTmplRows(prev => prev.filter((_, i) => i !== idx))
  }

  // ── PIN change ────────────────────────────────────────────────────────────
  async function changePin() {
    if (currentPin !== adminPin) { showToast('Current PIN is incorrect'); return }
    if (!newPin1) { showToast('New PIN cannot be empty'); return }
    if (newPin1 !== newPin2) { showToast('New PINs do not match'); return }
    await fetch('/api/inspection/master', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adminPin: newPin1 }),
    })
    setAdminPin(newPin1)
    setCurrentPin(''); setNewPin1(''); setNewPin2('')
    showToast('PIN changed successfully')
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const TABS: { key: AdminTab; label: string }[] = [
    { key: 'master',    label: 'Master Data'    },
    { key: 'wo',        label: 'Work Orders'    },
    { key: 'templates', label: 'Templates'      },
    { key: 'import',    label: 'Import'         },
    { key: 'security',  label: 'Security'       },
  ]

  return (
    <div className="p-5 min-h-screen bg-surface-900">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Admin Configuration</h1>
          <p className="text-xs text-slate-500 mt-0.5">Manage master data, work orders, and inspection templates</p>
        </div>
        <button
          onClick={onLock}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 border border-slate-300 rounded hover:bg-slate-50 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          Lock Admin
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 mb-5 border-b border-slate-200">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors
              ${tab === t.key ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-900'}`}
          >{t.label}</button>
        ))}
      </div>

      {/* ── Master Data ── */}
      {tab === 'master' && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {([
            { key: 'charDesignators' as keyof MasterData, label: 'Characteristic Designators' },
            { key: 'tools'           as keyof MasterData, label: 'Tools' },
            { key: 'sampleRates'     as keyof MasterData, label: 'Sample Rates' },
            { key: 'machinists'      as keyof MasterData, label: 'Machinists' },
          ] as const).map(({ key, label }) => (
            <div key={key} className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="text-xs font-bold text-brand-700 uppercase tracking-wide border-b-2 border-brand-600 pb-2 mb-3">{label}</div>
              <ul className="space-y-1.5 max-h-72 overflow-y-auto mb-3">
                {master[key].map((item, idx) => (
                  <li key={idx} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={item}
                      onChange={e => {
                        const items = [...master[key]]; items[idx] = e.target.value
                        saveMasterItem(key, items)
                      }}
                      className="flex-1 border border-slate-200 rounded px-2 py-1 text-xs outline-none focus:border-brand-500"
                    />
                    <button
                      onClick={() => saveMasterItem(key, master[key].filter((_, i) => i !== idx))}
                      className="text-slate-300 hover:text-red-600 text-sm leading-none flex-shrink-0"
                      title="Remove"
                    >✕</button>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={configInputs[key] || ''}
                  onChange={e => setConfigInputs(prev => ({ ...prev, [key]: e.target.value }))}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const val = (configInputs[key] || '').trim()
                      if (val && !master[key].includes(val)) {
                        saveMasterItem(key, [...master[key], val])
                        setConfigInputs(prev => ({ ...prev, [key]: '' }))
                      }
                    }
                  }}
                  placeholder="Add new…"
                  className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
                />
                <button
                  onClick={() => {
                    const val = (configInputs[key] || '').trim()
                    if (val && !master[key].includes(val)) {
                      saveMasterItem(key, [...master[key], val])
                      setConfigInputs(prev => ({ ...prev, [key]: '' }))
                    }
                  }}
                  className="px-3 py-1.5 bg-brand-600 text-white rounded text-xs font-bold hover:bg-brand-700 transition-colors"
                >Add</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Work Orders ── */}
      {tab === 'wo' && (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          {/* Add row */}
          <div className="grid grid-cols-12 gap-2 p-3 bg-slate-50 border-b border-slate-200">
            <input
              placeholder="WO-2025-XXXX"
              value={newWo.wo_number}
              onChange={e => setNewWo(p => ({ ...p, wo_number: e.target.value }))}
              className="col-span-3 border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
            />
            <input
              placeholder="Product name"
              value={newWo.product}
              onChange={e => setNewWo(p => ({ ...p, product: e.target.value }))}
              className="col-span-5 border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
            />
            <input
              placeholder="Part #"
              value={newWo.part_number}
              onChange={e => setNewWo(p => ({ ...p, part_number: e.target.value }))}
              className="col-span-2 border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
            />
            <button
              onClick={addWo}
              className="col-span-2 bg-brand-600 text-white rounded text-xs font-bold hover:bg-brand-700 transition-colors py-1.5"
            >+ Add</button>
          </div>
          {/* Table */}
          <table className="w-full text-xs">
            <thead className="bg-white border-b border-slate-200">
              <tr>
                {['W.O. Number', 'Product', 'Part #', 'Status', 'Actions'].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {woCatalog.map(wo => (
                <tr key={wo.id} className="border-b border-slate-100 hover:bg-slate-50">
                  {editingWo === wo.id ? (
                    <>
                      <td className="px-2 py-1">
                        <input value={editWoData.wo_number || ''} onChange={e => setEditWoData(p => ({ ...p, wo_number: e.target.value }))}
                          className="border border-slate-300 rounded px-2 py-1 text-xs w-full outline-none" />
                      </td>
                      <td className="px-2 py-1">
                        <input value={editWoData.product || ''} onChange={e => setEditWoData(p => ({ ...p, product: e.target.value }))}
                          className="border border-slate-300 rounded px-2 py-1 text-xs w-full outline-none" />
                      </td>
                      <td className="px-2 py-1">
                        <input value={editWoData.part_number || ''} onChange={e => setEditWoData(p => ({ ...p, part_number: e.target.value }))}
                          className="border border-slate-300 rounded px-2 py-1 text-xs w-full outline-none" />
                      </td>
                      <td className="px-3 py-2 text-slate-400">—</td>
                      <td className="px-3 py-2">
                        <div className="flex gap-2">
                          <button onClick={saveWoEdit} className="text-brand-600 hover:text-brand-800 font-semibold">Save</button>
                          <button onClick={() => setEditingWo(null)} className="text-slate-500 hover:text-slate-700">Cancel</button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 py-2 font-mono font-bold text-slate-900">{wo.wo_number}</td>
                      <td className="px-3 py-2 text-slate-700">{wo.product}</td>
                      <td className="px-3 py-2 text-slate-500">{wo.part_number || '—'}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${wo.is_active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500'}`}>
                          {wo.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-3">
                          <button
                            onClick={() => { setEditingWo(wo.id); setEditWoData({ wo_number: wo.wo_number, product: wo.product, part_number: wo.part_number || '' }) }}
                            className="text-brand-600 hover:text-brand-800 font-semibold"
                          >Edit</button>
                          <button onClick={() => toggleWoActive(wo.id, wo.is_active)} className="text-slate-500 hover:text-slate-700">
                            {wo.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {woCatalog.length === 0 && (
                <tr><td colSpan={5} className="text-center py-6 text-slate-400 text-xs">No work orders. Add one above.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Templates ── */}
      {tab === 'templates' && (
        <div className="flex gap-4">
          {/* List panel */}
          <div className="w-64 flex-shrink-0">
            <button
              onClick={newTemplate}
              className="w-full mb-3 px-3 py-2 bg-brand-600 text-white rounded-lg text-xs font-bold hover:bg-brand-700 transition-colors"
            >+ New Template</button>
            <div className="space-y-1.5">
              {templates.map(t => (
                <div
                  key={t.id}
                  onClick={() => loadTemplate(t.id)}
                  className={`group flex items-start justify-between p-3 rounded-lg border cursor-pointer transition-all
                    ${selectedTmpl === t.id ? 'bg-brand-50 border-brand-400' : 'bg-white border-slate-200 hover:border-brand-300'}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-bold text-slate-900 truncate">{t.name}</div>
                    {t.product && (
                      <div className="text-[10px] text-slate-500 truncate mt-0.5">{t.product}</div>
                    )}
                    <div className="text-[10px] text-slate-400 mt-0.5">{t.row_count || 0} rows</div>
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); deleteTemplate(t.id) }}
                    className="text-slate-300 group-hover:text-red-400 ml-1 text-sm leading-none flex-shrink-0 mt-0.5"
                    title="Delete"
                  >✕</button>
                </div>
              ))}
              {templates.length === 0 && (
                <div className="text-center text-xs text-slate-400 py-8 bg-white rounded-lg border border-dashed border-slate-300">
                  No templates yet.<br />Click "+ New Template" to start.
                </div>
              )}
            </div>
          </div>

          {/* Editor panel */}
          <div className="flex-1 min-w-0">
            {!showingEditor ? (
              <div className="h-64 flex items-center justify-center text-slate-400 text-sm bg-white rounded-lg border border-dashed border-slate-300">
                Select a template to edit, or create a new one
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-lg p-4">
                {/* Metadata */}
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="col-span-2">
                    <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Template Name *</label>
                    <input
                      value={tmplForm.name}
                      onChange={e => setTmplForm(p => ({ ...p, name: e.target.value }))}
                      className="w-full border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
                      placeholder="e.g. Housing 5X — Final Inspection"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Operation</label>
                    <input
                      value={tmplForm.operation}
                      onChange={e => setTmplForm(p => ({ ...p, operation: e.target.value }))}
                      className="w-full border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
                      placeholder="e.g. Final Inspection"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Product</label>
                    <input
                      value={tmplForm.product}
                      onChange={e => setTmplForm(p => ({ ...p, product: e.target.value }))}
                      className="w-full border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
                      placeholder="e.g. HOUSING, 5X"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Part Number</label>
                    <input
                      value={tmplForm.part_number}
                      onChange={e => setTmplForm(p => ({ ...p, part_number: e.target.value }))}
                      className="w-full border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
                      placeholder="e.g. AT-10051"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Description</label>
                    <input
                      value={tmplForm.description}
                      onChange={e => setTmplForm(p => ({ ...p, description: e.target.value }))}
                      className="w-full border border-slate-300 rounded px-2 py-1.5 text-xs outline-none focus:border-brand-500"
                    />
                  </div>
                </div>

                {/* Rows table */}
                <div className="text-xs font-bold text-slate-600 uppercase tracking-wide mb-2">Inspection Rows</div>
                <div className="border border-slate-200 rounded overflow-hidden mb-3">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-2 py-2 text-center text-[10px] font-bold text-slate-500 w-8">#</th>
                        <th className="px-2 py-2 text-left text-[10px] font-bold text-slate-500 w-36">Characteristic</th>
                        <th className="px-2 py-2 text-left text-[10px] font-bold text-slate-500">Requirement</th>
                        <th className="px-2 py-2 text-left text-[10px] font-bold text-slate-500 w-36">Tool</th>
                        <th className="px-2 py-2 text-left text-[10px] font-bold text-slate-500 w-24">Sample Rate</th>
                        <th className="w-8"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {tmplRows.map((row, idx) => (
                        <tr key={row.rowKey} className="border-t border-slate-100">
                          <td className="px-2 py-1 text-center text-slate-400 font-bold">{idx + 1}</td>
                          <td className="px-1 py-1">
                            <select
                              value={row.charDesig}
                              onChange={e => updateTmplRow(idx, { charDesig: e.target.value })}
                              className="w-full border border-slate-200 rounded px-1.5 py-1 text-xs outline-none focus:border-brand-500 bg-white"
                            >
                              <option value=""></option>
                              {master.charDesignators.map(d => <option key={d} value={d}>{d}</option>)}
                            </select>
                          </td>
                          <td className="px-1 py-1">
                            <input
                              value={row.requirement}
                              onChange={e => updateTmplRow(idx, { requirement: e.target.value })}
                              placeholder="e.g. 0.87 ±0.005"
                              className="w-full border border-slate-200 rounded px-1.5 py-1 text-xs outline-none focus:border-brand-500"
                            />
                          </td>
                          <td className="px-1 py-1">
                            <select
                              value={row.tool}
                              onChange={e => updateTmplRow(idx, { tool: e.target.value })}
                              className="w-full border border-slate-200 rounded px-1.5 py-1 text-xs outline-none focus:border-brand-500 bg-white"
                            >
                              <option value=""></option>
                              {master.tools.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                          </td>
                          <td className="px-1 py-1">
                            <select
                              value={row.sampleRate}
                              onChange={e => updateTmplRow(idx, { sampleRate: e.target.value })}
                              className="w-full border border-slate-200 rounded px-1.5 py-1 text-xs outline-none focus:border-brand-500 bg-white"
                            >
                              <option value=""></option>
                              {master.sampleRates.map(r => <option key={r} value={r}>{r}</option>)}
                            </select>
                          </td>
                          <td className="px-1 py-1 text-center">
                            <button onClick={() => removeTmplRow(idx)} className="text-slate-300 hover:text-red-500 text-sm">✕</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex justify-between items-center">
                  <button
                    onClick={addTmplRow}
                    className="text-xs text-brand-600 hover:text-brand-800 font-semibold border border-dashed border-brand-400 rounded px-3 py-1.5 hover:bg-brand-50 transition-colors"
                  >+ Add Row</button>
                  <button
                    onClick={saveTemplate}
                    disabled={tmplSaving}
                    className="px-4 py-1.5 bg-brand-600 text-white rounded text-xs font-bold hover:bg-brand-700 disabled:opacity-50 transition-colors"
                  >{tmplSaving ? 'Saving…' : 'Save Template'}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Import ── */}
      {tab === 'import' && <ImportTab />}

      {/* ── Security ── */}
      {tab === 'security' && (
        <div className="max-w-sm">
          <div className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="text-xs font-bold text-brand-700 uppercase tracking-wide border-b-2 border-brand-600 pb-2 mb-4">Change Admin PIN</div>
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Current PIN</label>
                <input
                  type="password"
                  value={currentPin}
                  onChange={e => setCurrentPin(e.target.value)}
                  className="w-full border border-slate-300 rounded px-3 py-2 text-sm outline-none focus:border-brand-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">New PIN</label>
                <input
                  type="password"
                  value={newPin1}
                  onChange={e => setNewPin1(e.target.value)}
                  className="w-full border border-slate-300 rounded px-3 py-2 text-sm outline-none focus:border-brand-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-500 uppercase tracking-wide font-medium mb-1">Confirm New PIN</label>
                <input
                  type="password"
                  value={newPin2}
                  onChange={e => setNewPin2(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && changePin()}
                  className="w-full border border-slate-300 rounded px-3 py-2 text-sm outline-none focus:border-brand-500"
                />
              </div>
              <button
                onClick={changePin}
                className="w-full bg-brand-600 text-white rounded py-2 text-sm font-bold hover:bg-brand-700 transition-colors"
              >Update PIN</button>
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

// ── Page entry point ───────────────────────────────────────────────────────────
export default function AdminPage() {
  const [authenticated, setAuthenticated] = useState(
    () => sessionStorage.getItem('airtech_admin') === 'true'
  )

  if (!authenticated) return <PinLock onAuth={() => setAuthenticated(true)} />

  return <AdminContent onLock={() => {
    sessionStorage.removeItem('airtech_admin')
    setAuthenticated(false)
  }} />
}
