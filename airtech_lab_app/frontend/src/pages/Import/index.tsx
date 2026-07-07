import { useRef, useState } from 'react'
import * as XLSX from 'xlsx'

// ── Types ───────────────────────────────────────────────────────────────────────
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

// ── Constants ───────────────────────────────────────────────────────────────────
const COLS = [
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
  [2, 'SHAFT, 12mm', 'WO-2025-1012', '2025-06-02', 'AT-60012', '', 'Final Inspection', '', 'R. Reid',
   'OD', '12.000 -0.000/-0.009', 'Mics', '100%', 'Pass', '', '', '', '', '', '', '', ''],
]

// ── Helpers ─────────────────────────────────────────────────────────────────────
function formatDate(val: unknown): string {
  if (!val) return ''
  if (val instanceof Date) return val.toISOString().split('T')[0]
  if (typeof val === 'number') {
    // Excel serial date → JS date
    const d = new Date(Math.round((val - 25569) * 86400 * 1000))
    return d.toISOString().split('T')[0]
  }
  const s = String(val).trim()
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toISOString().split('T')[0]
}

function str(val: unknown): string {
  return val === null || val === undefined ? '' : String(val).trim()
}

function parseSheet(rawRows: Record<string, unknown>[]): ImportRecord[] {
  const groups = new Map<string, ImportRecord>()
  rawRows.forEach((row, idx) => {
    const key = str(row['Record Group'] ?? row['Record#'] ?? row['Record #'] ?? idx)
    if (!groups.has(key)) {
      groups.set(key, {
        product:         str(row['Product']),
        wo_number:       str(row['W.O. Number'] ?? row['WO Number'] ?? row['WO#']),
        inspection_date: formatDate(row['Date']),
        part_number:     str(row['Part Number']),
        serial_number:   str(row['Serial Number']),
        operation:       str(row['Operation']),
        equipment:       str(row['Equipment']),
        machinist:       str(row['Machinist']),
        rows: [],
      })
    }
    const rec = groups.get(key)!
    rec.rows.push({
      char_designator: str(row['Char Designator']),
      requirement:     str(row['Requirement']),
      tool:            str(row['Tool']),
      sample_rate:     str(row['Sample Rate']),
      piece_1st:       str(row['1st Piece']),
      piece_5th:       str(row['5th Piece']),
      piece_10th:      str(row['10th Piece']),
      piece_15th:      str(row['15th Piece']),
      piece_20th:      str(row['20th Piece']),
      piece_25th:      str(row['25th Piece']),
      piece_30th:      str(row['30th Piece']),
      piece_35th:      str(row['35th Piece']),
      piece_iqa:       str(row['IQA']),
    })
  })
  return Array.from(groups.values())
}

function downloadTemplate() {
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet([COLS, ...EXAMPLE_ROWS])
  // Column widths
  ws['!cols'] = COLS.map((_, i) => ({ wch: i === 0 ? 14 : i <= 8 ? 20 : 16 }))
  XLSX.utils.book_append_sheet(wb, ws, 'Inspections')
  XLSX.writeFile(wb, 'inspection_import_template.xlsx')
}

// ── Page ────────────────────────────────────────────────────────────────────────
export default function ImportPage() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging,   setDragging]   = useState(false)
  const [fileName,   setFileName]   = useState('')
  const [records,    setRecords]    = useState<ImportRecord[]>([])
  const [parseError, setParseError] = useState('')
  const [importing,  setImporting]  = useState(false)
  const [result,     setResult]     = useState<{ imported: number; errors: { record: number; error: string }[] } | null>(null)
  const [toast,      setToast]      = useState('')

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(''), 3500)
  }

  function handleFile(file: File) {
    setParseError(''); setRecords([]); setResult(null)
    setFileName(file.name)
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
      } catch (err) {
        setParseError(`Could not parse file: ${err}`)
      }
    }
    reader.readAsArrayBuffer(file)
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
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
    } catch {
      setParseError('Import failed — could not reach the server.')
    } finally {
      setImporting(false)
    }
  }

  function reset() {
    setFileName(''); setRecords([]); setParseError(''); setResult(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const totalRows = records.reduce((s, r) => s + r.rows.length, 0)

  return (
    <div className="p-5 min-h-screen bg-surface-900">

      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-600 text-white text-sm font-semibold px-4 py-2.5 rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Import Inspections</h1>
          <p className="text-xs text-slate-500 mt-0.5">Upload an Excel or CSV file to bulk-load inspection records into Lakebase</p>
        </div>
        <button
          onClick={downloadTemplate}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors shadow-sm"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download Template
        </button>
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5">
        <div className="flex gap-3">
          <svg className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-xs text-blue-800 space-y-1">
            <p className="font-semibold">How to import:</p>
            <ol className="list-decimal list-inside space-y-0.5 text-blue-700">
              <li>Download the template above and fill it in (Excel .xlsx or .csv)</li>
              <li>Each row = one inspection measurement. Use the same <strong>Record Group</strong> number for rows belonging to the same inspection form</li>
              <li>Required columns: <strong>Record Group, Product, Machinist</strong>. All others are optional</li>
              <li>Upload your file below, review the preview, then click Import</li>
            </ol>
          </div>
        </div>
      </div>

      {/* Upload zone */}
      {records.length === 0 && !parseError && (
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center cursor-pointer transition-all mb-5
            ${dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-slate-50'}`}
        >
          <svg className="w-10 h-10 text-slate-400 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p className="text-sm font-semibold text-slate-700 mb-1">Drop your file here, or click to browse</p>
          <p className="text-xs text-slate-500">Supports Excel (.xlsx, .xls) and CSV (.csv)</p>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]) }}
          />
        </div>
      )}

      {/* Parse error */}
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

      {/* Preview */}
      {records.length > 0 && !result && (
        <>
          {/* Summary bar */}
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
              <button
                onClick={reset}
                className="px-3 py-1.5 text-xs font-semibold border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-600"
              >
                Change File
              </button>
              <button
                onClick={doImport}
                disabled={importing}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-60 transition-colors"
              >
                {importing ? (
                  <><div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />Importing…</>
                ) : (
                  <><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 11l3-3m0 0l3 3m-3-3v12" />
                  </svg>Import {records.length} Records</>
                )}
              </button>
            </div>
          </div>

          {/* Preview table */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">Preview (first 10 records)</h3>
              <span className="text-[10px] text-slate-400">{records.length} total</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    {['#', 'Product', 'W.O. Number', 'Date', 'Part #', 'Machinist', 'Operation', 'Rows'].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
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
                      <td className="px-3 py-2">
                        <span className="px-2 py-0.5 bg-slate-100 rounded-full text-[10px] font-bold text-slate-600">
                          {r.rows.length}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {records.length > 10 && (
                    <tr className="border-t border-slate-100">
                      <td colSpan={8} className="px-3 py-2 text-center text-xs text-slate-400">
                        +{records.length - 10} more records not shown
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-4">
          <div className={`rounded-xl border p-5 ${result.errors.length === 0 ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'}`}>
            <div className="flex items-center gap-3 mb-2">
              {result.errors.length === 0 ? (
                <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              )}
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

          <button
            onClick={reset}
            className="px-4 py-2 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700"
          >
            Import Another File
          </button>
        </div>
      )}
    </div>
  )
}
