import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'

interface RunRow {
  id: number
  procedure_id: number
  procedure_name: string
  serial_number: string
  model_number: string
  technician_name: string
  status: string
  created_at: string
}

function statusBadge(s: string) {
  if (s === 'completed') return 'bg-green-100 text-green-800'
  if (s === 'failed')    return 'bg-red-100 text-red-800'
  return 'bg-blue-100 text-blue-800'
}

export default function RunsPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const procedureId = searchParams.get('procedure_id')
  const statusFilter = searchParams.get('status')

  const [runs,        setRuns]        = useState<RunRow[]>([])
  const [loading,     setLoading]     = useState(true)
  const [populating,  setPopulating]  = useState(false)
  const [populatedOk, setPopulatedOk] = useState(false)

  async function loadRuns() {
    const p = new URLSearchParams()
    if (procedureId) p.set('procedure_id', procedureId)
    if (statusFilter) p.set('status', statusFilter)
    return fetch(`/api/test-runs?${p}`)
      .then(r => r.json())
      .then(data => { setRuns(Array.isArray(data) ? data : []) })
  }

  useEffect(() => {
    setLoading(true)
    loadRuns().finally(() => setLoading(false))
  }, [procedureId, statusFilter])

  async function populateAll() {
    setPopulating(true)
    try {
      await fetch('/api/test-runs/generate-all', { method: 'POST' })
      setPopulatedOk(true)
      await loadRuns()
      setTimeout(() => setPopulatedOk(false), 5000)
    } finally {
      setPopulating(false)
    }
  }

  const unpopulated = runs.filter(r => r.status !== 'in_progress').length
  const title = statusFilter === 'failed' ? 'Failed Test Runs' : 'Test Run History'
  const subtitle = runs.length > 0
    ? `${runs.length} run${runs.length !== 1 ? 's' : ''}${statusFilter === 'failed' ? ' failed' : ''}`
    : 'No results'

  return (
    <div className="p-5 min-h-screen bg-surface-900">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-lg font-bold text-slate-900">{title}</h1>
          <p className="text-xs text-slate-500 mt-0.5">{subtitle} · click a row to view details</p>
        </div>
        <div className="flex items-center gap-2">
          {unpopulated > 0 && (
            <button
              onClick={populateAll}
              disabled={populating}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-60 transition-colors shadow-sm"
            >
              {populating ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Populating…
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Populate All
                </>
              )}
            </button>
          )}
          {populatedOk && (
            <span className="text-xs text-green-700 font-medium flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
              All runs populated
            </span>
          )}
          <Link
            to="/dashboard"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Dashboard
          </Link>
        </div>
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
                {['Run #', 'Procedure', 'Serial', 'Model', 'Technician', 'Date', 'Status', ''].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr
                  key={r.id}
                  className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors"
                  onClick={() => navigate(`/runs/${r.id}`)}
                >
                  <td className="px-3 py-2.5 font-bold text-slate-700">#{r.id}</td>
                  <td className="px-3 py-2.5 text-slate-800 font-medium">{r.procedure_name}</td>
                  <td className="px-3 py-2.5 font-mono text-[10px] text-slate-500">{r.serial_number || '—'}</td>
                  <td className="px-3 py-2.5 text-slate-600">{r.model_number || '—'}</td>
                  <td className="px-3 py-2.5 text-slate-600">{r.technician_name || '—'}</td>
                  <td className="px-3 py-2.5 text-slate-500">{r.created_at?.slice(0, 10) || '—'}</td>
                  <td className="px-3 py-2.5">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${statusBadge(r.status)}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-brand-600 font-semibold">View →</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-slate-400">No test runs found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
