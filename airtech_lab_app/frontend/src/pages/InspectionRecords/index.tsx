import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'

interface RecordRow {
  id: number
  product: string
  wo_number: string
  inspection_date: string
  part_number: string
  serial_number: string
  operation: string
  machinist: string
  status: string
  has_fail: boolean
  row_count: number
}

interface InspRow {
  id: number
  row_number: number
  char_designator: string
  requirement: string
  tool: string
  sample_rate: string
  piece_1st: string
  piece_5th: string
  piece_10th: string
}

function failBadge(v: string) {
  const s = (v || '').toLowerCase()
  if (s === 'fail' || s === 'f') return 'bg-red-100 text-red-700 font-bold'
  if (s === 'pass' || s === 'p') return 'bg-green-100 text-green-700'
  return 'bg-slate-100 text-slate-500'
}

export default function InspectionRecordsPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const product   = searchParams.get('product')   ?? ''
  const machinist = searchParams.get('machinist') ?? ''
  const date      = searchParams.get('date')      ?? ''
  const status    = searchParams.get('status')    ?? ''

  const [records, setRecords]   = useState<RecordRow[]>([])
  const [loading, setLoading]   = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [rows, setRows]         = useState<Record<number, InspRow[]>>({})
  const [loadingRow, setLoadingRow] = useState<number | null>(null)

  useEffect(() => {
    setLoading(true)
    const p = new URLSearchParams()
    if (product)   p.set('product',   product)
    if (machinist) p.set('machinist', machinist)
    if (date)      p.set('date',      date)
    if (status)    p.set('status',    status)
    p.set('limit', '200')
    fetch(`/api/inspection/records?${p}`)
      .then(r => r.json())
      .then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [product, machinist, date, status])

  async function toggle(id: number) {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    if (rows[id]) return
    setLoadingRow(id)
    try {
      const data = await fetch(`/api/inspection/records/${id}`).then(r => r.json())
      setRows(prev => ({ ...prev, [id]: data.rows || [] }))
    } finally {
      setLoadingRow(null)
    }
  }

  // Build title from active filters
  const filters: string[] = []
  if (status === 'failed') filters.push('Failed Only')
  if (product)   filters.push(product)
  if (machinist) filters.push(machinist)
  if (date)      filters.push(date)
  const title    = status === 'failed' ? 'Failed Inspections' : 'Inspection Records'
  const subtitle = loading ? 'Loading…' : `${records.length} record${records.length !== 1 ? 's' : ''}`

  return (
    <div className="p-5 min-h-screen bg-surface-900">

      {/* Header */}
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
          <h1 className="text-lg font-bold text-slate-900">{title}</h1>
          <p className="text-xs text-slate-500 mt-0.5">{subtitle} · click a row to expand details</p>
          {filters.length > 0 && (
            <div className="flex gap-1.5 mt-2 flex-wrap">
              {filters.map(f => (
                <span key={f} className="px-2 py-0.5 bg-brand-100 text-brand-700 text-[10px] font-semibold rounded-full">
                  {f}
                </span>
              ))}
              <Link to="/inspection/records" className="px-2 py-0.5 bg-slate-100 text-slate-500 text-[10px] font-semibold rounded-full hover:bg-slate-200">
                Clear filters ×
              </Link>
            </div>
          )}
        </div>
        <Link
          to="/dashboard"
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm mt-6"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Dashboard
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {['#', 'Date', 'Product', 'W.O.', 'Machinist', 'Operation', 'Chars', 'Result', ''].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map(r => (
                <>
                  <tr
                    key={r.id}
                    className={`border-t border-slate-100 cursor-pointer transition-colors
                      ${expanded === r.id ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
                    onClick={() => toggle(r.id)}
                  >
                    <td className="px-3 py-2.5 font-bold text-slate-700">#{r.id}</td>
                    <td className="px-3 py-2.5 text-slate-600 font-mono text-[10px]">{r.inspection_date || '—'}</td>
                    <td className="px-3 py-2.5 font-medium text-slate-800">{r.product || '—'}</td>
                    <td className="px-3 py-2.5 font-mono text-[10px] text-slate-500">{r.wo_number || '—'}</td>
                    <td className="px-3 py-2.5 text-slate-600">{r.machinist || '—'}</td>
                    <td className="px-3 py-2.5 text-slate-500 text-[10px]">{r.operation || '—'}</td>
                    <td className="px-3 py-2.5 text-slate-400 text-center">{r.row_count ?? '—'}</td>
                    <td className="px-3 py-2.5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold
                        ${r.has_fail ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                        {r.has_fail ? 'FAIL' : 'PASS'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-slate-400">
                      <svg
                        className={`w-3.5 h-3.5 transition-transform inline-block ${expanded === r.id ? 'rotate-90' : ''}`}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </td>
                  </tr>

                  {/* Expanded detail */}
                  {expanded === r.id && (
                    <tr key={`${r.id}-detail`} className="bg-brand-50/50 border-t border-brand-100">
                      <td colSpan={9} className="px-4 py-3">
                        {loadingRow === r.id ? (
                          <div className="flex items-center gap-2 text-xs text-slate-500">
                            <div className="w-4 h-4 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
                            Loading inspection rows…
                          </div>
                        ) : (rows[r.id] || []).length === 0 ? (
                          <div className="text-xs text-slate-400 italic">No inspection rows recorded.</div>
                        ) : (
                          <table className="w-full text-[11px] border border-slate-200 rounded-lg overflow-hidden">
                            <thead className="bg-white border-b border-slate-200">
                              <tr>
                                {['Row', 'Char', 'Requirement', 'Tool', 'Sample Rate', '1st', '5th', '10th'].map(h => (
                                  <th key={h} className="px-2.5 py-1.5 text-left text-[9px] font-bold text-slate-400 uppercase tracking-wide">{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="bg-white">
                              {(rows[r.id] || []).map(ir => (
                                <tr key={ir.id} className="border-t border-slate-100">
                                  <td className="px-2.5 py-1.5 text-slate-500 font-mono">{ir.row_number}</td>
                                  <td className="px-2.5 py-1.5 font-semibold text-slate-700">{ir.char_designator || '—'}</td>
                                  <td className="px-2.5 py-1.5 text-slate-600 max-w-[180px] truncate" title={ir.requirement}>{ir.requirement || '—'}</td>
                                  <td className="px-2.5 py-1.5 text-slate-500">{ir.tool || '—'}</td>
                                  <td className="px-2.5 py-1.5 text-slate-400">{ir.sample_rate || '—'}</td>
                                  {[ir.piece_1st, ir.piece_5th, ir.piece_10th].map((v, idx) => (
                                    <td key={idx} className="px-2.5 py-1.5">
                                      {v ? (
                                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${failBadge(v)}`}>{v}</span>
                                      ) : (
                                        <span className="text-slate-300">—</span>
                                      )}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {records.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-12 text-slate-400">No inspection records found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
