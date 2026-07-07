import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

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
  piece_15th: string
  piece_20th: string
  piece_25th: string
  piece_30th: string
  piece_35th: string
  piece_iqa: string
}

interface Record {
  id: number
  product: string
  wo_number: string
  inspection_date: string
  part_number: string
  serial_number: string
  operation: string
  equipment: string
  machinist: string
  status: string
  rows: InspRow[]
}

function pieceBadge(v: string) {
  const s = (v || '').toLowerCase()
  if (s === 'fail' || s === 'f') return 'bg-red-100 text-red-700 font-bold'
  if (s === 'pass' || s === 'p') return 'bg-green-100 text-green-700'
  return ''
}

const PIECES = ['piece_1st','piece_5th','piece_10th','piece_15th','piece_20th','piece_25th','piece_30th','piece_35th','piece_iqa'] as const
const PIECE_LABELS = ['1st','5th','10th','15th','20th','25th','30th','35th','IQA']

export default function InspectionRecordDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [rec, setRec] = useState<Record | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`/api/inspection/records/${id}`)
      .then(r => r.json())
      .then(data => setRec(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="p-5 min-h-screen bg-surface-900 flex items-center justify-center">
      <div className="w-7 h-7 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  if (!rec) return (
    <div className="p-5"><div className="text-sm text-red-600">Record not found.</div></div>
  )

  const hasFail = rec.rows.some(r =>
    PIECES.some(p => ['fail','f'].includes((r[p] || '').toLowerCase()))
  )

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
          <h1 className="text-lg font-bold text-slate-900">{rec.product || 'Inspection Record'}</h1>
          <p className="text-xs text-slate-500 mt-0.5">Record #{rec.id} · {rec.wo_number || '—'} · {rec.inspection_date || '—'}</p>
        </div>
        <span className={`mt-6 px-3 py-1.5 rounded-lg text-xs font-bold border
          ${hasFail ? 'bg-red-100 text-red-800 border-red-200' : 'bg-green-100 text-green-800 border-green-200'}`}>
          {hasFail ? 'FAIL' : 'PASS'}
        </span>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          ['Machinist',   rec.machinist   || '—'],
          ['Operation',   rec.operation   || '—'],
          ['Part Number', rec.part_number || '—'],
          ['Equipment',   rec.equipment   || '—'],
        ].map(([label, value]) => (
          <div key={label} className="bg-white border border-slate-200 rounded-xl px-4 py-3">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wide mb-0.5">{label}</div>
            <div className="text-sm font-semibold text-slate-800 truncate" title={value}>{value}</div>
          </div>
        ))}
      </div>

      {/* Rows table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
        <div className="px-4 py-3 border-b border-slate-100">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide">
            Inspection Rows — {rec.rows.length} characteristic{rec.rows.length !== 1 ? 's' : ''}
          </h3>
        </div>
        <table className="w-full text-xs">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide">Row</th>
              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide">Char</th>
              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide">Requirement</th>
              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide">Tool</th>
              <th className="px-3 py-2 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide">Sample Rate</th>
              {PIECE_LABELS.map(l => (
                <th key={l} className="px-2 py-2 text-center text-[10px] font-bold text-slate-400 uppercase tracking-wide">{l}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rec.rows.map(row => {
              const rowFail = PIECES.some(p => ['fail','f'].includes((row[p] || '').toLowerCase()))
              return (
                <tr key={row.id} className={`border-t border-slate-100 ${rowFail ? 'bg-red-50/40' : ''}`}>
                  <td className="px-3 py-2 font-mono text-slate-500">{row.row_number}</td>
                  <td className="px-3 py-2 font-semibold text-slate-700">{row.char_designator || '—'}</td>
                  <td className="px-3 py-2 text-slate-600 max-w-[160px] truncate" title={row.requirement}>{row.requirement || '—'}</td>
                  <td className="px-3 py-2 text-slate-500">{row.tool || '—'}</td>
                  <td className="px-3 py-2 text-slate-400">{row.sample_rate || '—'}</td>
                  {PIECES.map(p => {
                    const v = row[p] || ''
                    return (
                      <td key={p} className="px-2 py-2 text-center">
                        {v ? (
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${pieceBadge(v)}`}>{v}</span>
                        ) : (
                          <span className="text-slate-200">—</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
            {rec.rows.length === 0 && (
              <tr><td colSpan={14} className="text-center py-8 text-slate-400">No inspection rows recorded</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
