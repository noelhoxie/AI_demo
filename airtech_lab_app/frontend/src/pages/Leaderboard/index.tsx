import { useCallback, useEffect, useState } from 'react'
import { format, formatDistanceToNow, parseISO } from 'date-fns'
import * as api from '../../api'
import type { LeaderboardSummary, TestSlot, Technician, Machine, ShiftDef, BalancePlan } from '../../types'
import Badge from '../../components/ui/Badge'
import Modal from '../../components/ui/Modal'
import Spinner from '../../components/ui/Spinner'

// ── Priority colour map ────────────────────────────────────────────────────────
const PRIORITY_VARIANT: Record<string, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical', high: 'high', normal: 'medium', low: 'low',
}

const RISK_VARIANT: Record<string, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical', high: 'high', medium: 'medium', low: 'low',
}

function probColor(p?: number) {
  if (p == null) return 'text-slate-500'
  if (p >= 85)  return 'text-emerald-700'
  if (p >= 65)  return 'text-amber-700'
  if (p >= 40)  return 'text-orange-600'
  return 'text-red-600'
}

function ProbBar({ value }: { value?: number }) {
  if (value == null) return <span className="text-slate-600 text-xs">—</span>
  const fill = value >= 85 ? 'bg-emerald-500' : value >= 65 ? 'bg-amber-500' : value >= 40 ? 'bg-orange-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="flex-1 h-1.5 bg-surface-600 rounded-full overflow-hidden">
        <div className={`h-full ${fill} rounded-full`} style={{ width: `${value}%` }} />
      </div>
      <span className={`text-xs font-mono font-medium w-8 text-right ${probColor(value)}`}>
        {value.toFixed(0)}%
      </span>
    </div>
  )
}

// ── Schedule row ───────────────────────────────────────────────────────────────
function ScheduleRow({
  slot, techs, onUpdate, onDelete, onView,
}: {
  slot: TestSlot
  techs: Technician[]
  onUpdate: (id: number, data: Partial<TestSlot>) => void
  onDelete: (id: number) => void
  onView: (slot: TestSlot) => void
}) {
  const [assignOpen, setAssignOpen] = useState(false)
  const [updating, setUpdating] = useState(false)

  const handleStatus = async (status: TestSlot['status']) => {
    setUpdating(true)
    await onUpdate(slot.id, { status })
    setUpdating(false)
  }

  const handleAssign = async (techId: number) => {
    setAssignOpen(false)
    await onUpdate(slot.id, { technician_id: techId })
  }

  const statusEl = slot.status === 'in_progress'
    ? <Badge variant="pending">In Progress</Badge>
    : slot.status === 'scheduled'
    ? <Badge variant="info">Scheduled</Badge>
    : <Badge variant="pass">Done</Badge>

  return (
    <tr
      className="border-b border-surface-700 hover:bg-surface-700/40 transition-colors group cursor-pointer"
      onClick={() => onView(slot)}
    >
      {/* Priority */}
      <td className="px-4 py-3">
        <Badge variant={PRIORITY_VARIANT[slot.priority] ?? 'medium'}>
          {slot.priority}
        </Badge>
      </td>

      {/* Title + sample */}
      <td className="px-4 py-3">
        <div className="font-medium text-sm text-slate-900">{slot.title}</div>
        {slot.sample_id && <div className="text-xs text-slate-500 font-mono mt-0.5">{slot.sample_id}</div>}
        {slot.test_type && <div className="text-xs text-slate-600 mt-0.5">{slot.test_type}</div>}
      </td>

      {/* Machine */}
      <td className="px-4 py-3">
        <div className="text-xs text-slate-500">
          {slot.machine_id === 'machine_pressure' ? 'Pressure/Leak — Bay 1'
           : slot.machine_id === 'machine_flow' ? 'Flow/Perf — Bay 2'
           : slot.machine_id ?? '—'}
        </div>
      </td>

      {/* Scheduled time */}
      <td className="px-4 py-3">
        {slot.scheduled_at ? (
          <div>
            <div className="text-sm text-slate-700">{format(parseISO(slot.scheduled_at), 'h:mm a')}</div>
            <div className="text-xs text-slate-500">{formatDistanceToNow(parseISO(slot.scheduled_at), { addSuffix: true })}</div>
          </div>
        ) : <span className="text-slate-600">—</span>}
      </td>

      {/* Duration */}
      <td className="px-4 py-3 text-sm text-slate-500">
        {slot.estimated_duration_min} min
      </td>

      {/* Technician (click to reassign) */}
      <td className="px-4 py-3 relative" onClick={e => e.stopPropagation()}>
        <button
          onClick={() => setAssignOpen(v => !v)}
          className="text-left hover:text-brand-700 transition-colors"
        >
          {slot.technician_name
            ? <div>
                <div className="text-sm text-slate-700">{slot.technician_name}</div>
                <div className="text-xs text-slate-500">{slot.technician_specialty}</div>
              </div>
            : <span className="text-xs text-slate-600 border border-dashed border-slate-700 px-2 py-1 rounded">
                Unassigned
              </span>
          }
        </button>

        {assignOpen && (
          <div className="absolute z-20 left-0 top-full mt-1 w-52 bg-surface-700 border border-surface-500
                          rounded-lg shadow-xl overflow-hidden">
            {techs.map(t => (
              <button key={t.id} onClick={() => handleAssign(t.id)}
                className="w-full text-left px-3 py-2 hover:bg-surface-600 transition-colors">
                <div className="text-sm text-slate-700">{t.name}</div>
                <div className="text-xs text-slate-500">{t.specialty}</div>
              </button>
            ))}
          </div>
        )}
      </td>

      {/* AI Prediction */}
      <td className="px-4 py-3">
        <ProbBar value={slot.success_probability ?? undefined} />
        {slot.risk_level && (
          <Badge variant={RISK_VARIANT[slot.risk_level] ?? 'medium'} className="mt-1">
            {slot.risk_level}
          </Badge>
        )}
      </td>

      {/* Status */}
      <td className="px-4 py-3">{statusEl}</td>

      {/* Actions */}
      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {slot.status === 'scheduled' && (
            <button onClick={() => handleStatus('in_progress')} disabled={updating}
              className="text-xs px-2 py-1 bg-brand-100 text-brand-700 rounded hover:bg-brand-100 transition-colors">
              Start
            </button>
          )}
          {slot.status === 'in_progress' && (
            <button onClick={() => handleStatus('completed')} disabled={updating}
              className="text-xs px-2 py-1 bg-emerald-50 text-emerald-700 rounded hover:bg-emerald-50 transition-colors">
              Complete
            </button>
          )}
          <button onClick={() => onDelete(slot.id)}
            className="text-xs px-2 py-1 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded transition-colors">
            Cancel
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── View Test modal ────────────────────────────────────────────────────────────
function ViewTestModal({ slot, onClose }: { slot: TestSlot; onClose: () => void }) {
  const statusLabel = slot.status === 'in_progress' ? 'In Progress'
    : slot.status === 'scheduled' ? 'Scheduled'
    : slot.status === 'completed' ? 'Completed'
    : 'Cancelled'

  const machineLabel = slot.machine_id === 'machine_pressure' ? 'Pressure/Leak Tester — Bay 1'
    : slot.machine_id === 'machine_flow' ? 'Flow/Performance Tester — Bay 2'
    : slot.machine_id ?? '—'

  function Field({ label, value }: { label: string; value?: string | number | null }) {
    return (
      <div>
        <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">{label}</div>
        <div className="text-sm text-slate-700">{value ?? <span className="text-slate-600">—</span>}</div>
      </div>
    )
  }

  return (
    <Modal title={slot.title} onClose={onClose}>
      <div className="space-y-5">
        {/* Status + Priority row */}
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={PRIORITY_VARIANT[slot.priority] ?? 'medium'}>{slot.priority}</Badge>
          <Badge variant={
            slot.status === 'in_progress' ? 'pending'
            : slot.status === 'scheduled' ? 'info'
            : slot.status === 'completed' ? 'pass'
            : 'low'
          }>{statusLabel}</Badge>
          {slot.risk_level && (
            <Badge variant={RISK_VARIANT[slot.risk_level] ?? 'medium'}>{slot.risk_level} risk</Badge>
          )}
        </div>

        {/* Core details */}
        <div className="grid grid-cols-2 gap-4">
          <Field label="Sample ID" value={slot.sample_id} />
          <Field label="Test Type" value={slot.test_type} />
          <Field label="Machine" value={machineLabel} />
          <Field label="Est. Duration" value={slot.estimated_duration_min ? `${slot.estimated_duration_min} min` : null} />
        </div>

        {/* Scheduling */}
        <div className="grid grid-cols-3 gap-4 border-t border-surface-600 pt-4">
          <Field label="Scheduled At"
            value={slot.scheduled_at ? format(parseISO(slot.scheduled_at), 'MMM d, yyyy h:mm a') : null} />
          <Field label="Started At"
            value={slot.started_at ? format(parseISO(slot.started_at), 'MMM d, yyyy h:mm a') : null} />
          <Field label="Completed At"
            value={slot.completed_at ? format(parseISO(slot.completed_at), 'MMM d, yyyy h:mm a') : null} />
        </div>

        {/* Technician */}
        <div className="grid grid-cols-2 gap-4 border-t border-surface-600 pt-4">
          <Field label="Technician" value={slot.technician_name} />
          <Field label="Specialty" value={slot.technician_specialty} />
        </div>

        {/* AI Prediction */}
        {slot.success_probability != null && (
          <div className="border-t border-surface-600 pt-4">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">AI Prediction</div>
            <ProbBar value={slot.success_probability} />
          </div>
        )}

        {/* Notes */}
        {slot.notes && (
          <div className="border-t border-surface-600 pt-4">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">Notes</div>
            <p className="text-sm text-slate-600 whitespace-pre-wrap">{slot.notes}</p>
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </Modal>
  )
}

// ── Add Test modal ─────────────────────────────────────────────────────────────
function AddTestModal({ techs, machines, onSave, onClose }: {
  techs: Technician[]
  machines: Machine[]
  onSave: (data: Partial<TestSlot>) => Promise<void>
  onClose: () => void
}) {
  const todayStr = format(new Date(), 'yyyy-MM-dd')
  const nowTimeStr = format(new Date(), 'HH:mm')
  const [schedDate, setSchedDate] = useState(todayStr)
  const [schedTime, setSchedTime] = useState(nowTimeStr)
  const [form, setForm] = useState<Partial<TestSlot>>({
    priority: 'normal', estimated_duration_min: 60,
    scheduled_at: `${todayStr}T${nowTimeStr}`,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof TestSlot, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  const handleDateChange = (date: string) => {
    setSchedDate(date)
    set('scheduled_at', `${date}T${schedTime}`)
  }
  const handleTimeChange = (time: string) => {
    setSchedTime(time)
    set('scheduled_at', `${schedDate}T${time}`)
  }

  const handleSave = async () => {
    if (!form.title) return
    setSaving(true)
    setError(null)
    try {
      await onSave(form)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save. Check DB connection.')
      setSaving(false)
    }
  }

  return (
    <Modal title="Schedule New Test" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="label">Test Title *</label>
          <input className="input" placeholder="e.g. Leak Test — P300-HPC SN-1042"
            value={form.title ?? ''} onChange={e => set('title', e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Sample ID</label>
            <input className="input" placeholder="SN-XXXX"
              value={form.sample_id ?? ''} onChange={e => set('sample_id', e.target.value)} />
          </div>
          <div>
            <label className="label">Test Type</label>
            <select className="input" value={form.test_type ?? ''}
              onChange={e => set('test_type', e.target.value)}>
              <option value="">Select…</option>
              <option value="leak_test">Leak Test</option>
              <option value="pressure_test">Pressure Test</option>
              <option value="flow_performance">Flow Performance</option>
              <option value="vibration_test">Vibration Test</option>
              <option value="acceptance">Final Acceptance</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Machine</label>
            <select className="input" value={form.machine_id ?? ''}
              onChange={e => set('machine_id', e.target.value)}>
              <option value="">Select…</option>
              {machines.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Priority</label>
            <select className="input" value={form.priority}
              onChange={e => set('priority', e.target.value)}>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="normal">Normal</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label">Scheduled At</label>
          <div className="grid grid-cols-2 gap-3">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 text-slate-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </span>
              <input type="date" className="input pl-9" value={schedDate}
                onChange={e => handleDateChange(e.target.value)} />
            </div>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </span>
              <input type="time" className="input pl-9" value={schedTime}
                onChange={e => handleTimeChange(e.target.value)} />
            </div>
          </div>
        </div>
        <div>
          <label className="label">Est. Duration (min)</label>
          <input type="number" className="input" value={form.estimated_duration_min}
            onChange={e => set('estimated_duration_min', Number(e.target.value))} />
        </div>
        <div>
          <label className="label">Assign Technician</label>
          <select className="input" value={form.technician_id ?? ''}
            onChange={e => set('technician_id', Number(e.target.value) || undefined)}>
            <option value="">Unassigned</option>
            {techs.map(t => <option key={t.id} value={t.id}>{t.name} — {t.specialty}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Notes</label>
          <textarea className="input resize-none" rows={2}
            value={form.notes ?? ''} onChange={e => set('notes', e.target.value)} />
        </div>
        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-ghost" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving || !form.title}>
            {saving ? 'Saving…' : 'Schedule Test'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function LeaderboardPage() {
  const [summary, setSummary] = useState<LeaderboardSummary | null>(null)
  const [slots, setSlots] = useState<TestSlot[]>([])
  const [techs, setTechs] = useState<Technician[]>([])
  const [machines, setMachines] = useState<Machine[]>([])
  const [loading, setLoading] = useState(true)
  const [filterTech, setFilterTech] = useState<number | ''>('')
  const [filterMachine, setFilterMachine] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [filterStatus, setFilterStatus] = useState<string>('active')
  const [viewSlot, setViewSlot] = useState<TestSlot | null>(null)
  const [showPlanning, setShowPlanning] = useState(false)
  const [shifts, setShifts] = useState<ShiftDef[]>([
    { name: 'Morning',   start_time: '06:00', end_time: '14:00', capacity: 5 },
    { name: 'Afternoon', start_time: '14:00', end_time: '22:00', capacity: 5 },
    { name: 'Night',     start_time: '22:00', end_time: '06:00', capacity: 3 },
  ])
  const [balancePlan, setBalancePlan] = useState<BalancePlan | null>(null)
  const [balancing, setBalancing] = useState(false)
  const [overviewFilter, setOverviewFilter] = useState<{ type: 'priority' | 'machine' | 'all'; val: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const statusParam = filterStatus === 'active' ? undefined : filterStatus
      const [s, sl, t, m] = await Promise.allSettled([
        api.getLeaderboardSummary(),
        api.getSchedule({
          status: statusParam,
          technician_id: filterTech || undefined,
          machine_id: filterMachine || undefined,
        }),
        api.getTechnicians(),
        api.getMachines(),
      ])
      if (s.status === 'fulfilled') setSummary(s.value)
      if (sl.status === 'fulfilled') setSlots(sl.value)
      if (t.status === 'fulfilled') setTechs(t.value)
      if (m.status === 'fulfilled') setMachines(m.value)
    } finally {
      setLoading(false)
    }
  }, [filterTech, filterMachine, filterStatus])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30 s
  useEffect(() => {
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  const handleUpdate = async (id: number, data: Partial<TestSlot>) => {
    await api.updateScheduleSlot(id, data)
    load()
  }

  const handleDelete = async (id: number) => {
    await api.cancelScheduleSlot(id)
    load()
  }

  const handleAdd = async (data: Partial<TestSlot>) => {
    await api.createScheduleSlot(data)
    setShowAdd(false)
    load()
  }

  const handleBalance = async () => {
    setBalancing(true)
    setBalancePlan(null)
    try {
      const plan = await api.balanceSchedule(shifts)
      setBalancePlan(plan)
    } finally {
      setBalancing(false)
    }
  }

  const updateShift = (i: number, key: keyof ShiftDef, val: string | number) =>
    setShifts(prev => prev.map((s, j) => j === i ? { ...s, [key]: val } : s))

  // Counts for planning overview
  const outstandingSlots = slots.filter(s => s.status === 'scheduled' || s.status === 'in_progress')
  const countBy = (key: keyof TestSlot, val: string) => outstandingSlots.filter(s => s[key] === val).length

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Lab Schedule</h1>
          <p className="text-sm text-slate-500 mt-1">Upcoming test queue · technician allocation · AI shift planning</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPlanning(v => !v)}
            className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg border font-medium transition-all ${
              showPlanning
                ? 'bg-brand-100 text-brand-700 border-brand-200'
                : 'btn-ghost border-surface-500'
            }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
            </svg>
            Planning
          </button>
          <button className="btn-primary flex items-center gap-2" onClick={() => setShowAdd(true)}>
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Schedule Test
          </button>
        </div>
      </div>

      {/* Planning panel */}
      {showPlanning && (
        <div className="card p-6 space-y-6 border-brand-200">
          {/* Lab overview */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-600">Outstanding Labs Overview</h2>
              <span className="text-xs text-slate-400">Click a row to see matching labs</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {/* By priority */}
              <div className="space-y-1.5">
                <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">By Priority</div>
                {[
                  { label: 'Critical', val: 'critical', color: 'text-red-600 bg-red-50 border-red-200 hover:bg-red-100' },
                  { label: 'High',     val: 'high',     color: 'text-orange-600 bg-orange-50 border-orange-200 hover:bg-orange-100' },
                  { label: 'Normal',   val: 'normal',   color: 'text-blue-700 bg-blue-50 border-blue-200 hover:bg-blue-100' },
                  { label: 'Low',      val: 'low',      color: 'text-slate-500 bg-surface-700 border-surface-600 hover:bg-surface-600' },
                ].map(({ label, val, color }) => {
                  const isActive = overviewFilter?.type === 'priority' && overviewFilter.val === val
                  return (
                    <button
                      key={val}
                      onClick={() => setOverviewFilter(isActive ? null : { type: 'priority', val })}
                      className={`w-full flex items-center justify-between px-3 py-1.5 rounded border text-xs transition-all ${color} ${isActive ? 'ring-2 ring-offset-1 ring-brand-400 font-semibold' : ''}`}
                    >
                      <span>{label}</span>
                      <span className="font-mono font-bold">{countBy('priority', val)}</span>
                    </button>
                  )
                })}
                <button
                  onClick={() => setOverviewFilter(overviewFilter?.type === 'all' ? null : { type: 'all', val: '' })}
                  className={`w-full flex items-center justify-between px-3 py-1.5 rounded border border-surface-500 bg-surface-700 hover:bg-surface-600 text-xs text-slate-600 font-medium transition-all ${overviewFilter?.type === 'all' ? 'ring-2 ring-offset-1 ring-brand-400' : ''}`}
                >
                  <span>Total outstanding</span>
                  <span className="font-mono font-bold">{outstandingSlots.length}</span>
                </button>
              </div>

              {/* By machine */}
              <div className="space-y-1.5">
                <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">By Machine</div>
                {[
                  { label: 'Pressure/Leak — Bay 1', val: 'machine_pressure' },
                  { label: 'Flow/Perf — Bay 2',     val: 'machine_flow' },
                  { label: 'Unassigned',             val: '__none__' },
                ].map(({ label, val }) => {
                  const count = val === '__none__'
                    ? outstandingSlots.filter(s => !s.machine_id).length
                    : countBy('machine_id', val)
                  const isActive = overviewFilter?.type === 'machine' && overviewFilter.val === val
                  return (
                    <button
                      key={val}
                      onClick={() => setOverviewFilter(isActive ? null : { type: 'machine', val })}
                      className={`w-full flex items-center justify-between px-3 py-1.5 rounded border border-surface-600 bg-surface-700 hover:bg-surface-600 text-xs text-slate-600 transition-all ${isActive ? 'ring-2 ring-offset-1 ring-brand-400 font-semibold' : ''}`}
                    >
                      <span>{label}</span>
                      <span className="font-mono font-bold text-brand-700">{count}</span>
                    </button>
                  )
                })}
                <div className="flex items-center justify-between px-3 py-1.5 rounded border border-surface-600 bg-surface-700 text-xs text-slate-500">
                  <span>Est. total duration</span>
                  <span className="font-mono">
                    {Math.round(outstandingSlots.reduce((sum, s) => sum + (s.estimated_duration_min ?? 0), 0) / 60 * 10) / 10} hrs
                  </span>
                </div>
              </div>
            </div>

            {/* Drill-down list */}
            {overviewFilter && (() => {
              const filtered = overviewFilter.type === 'all'
                ? outstandingSlots
                : overviewFilter.type === 'priority'
                ? outstandingSlots.filter(s => s.priority === overviewFilter.val)
                : overviewFilter.val === '__none__'
                ? outstandingSlots.filter(s => !s.machine_id)
                : outstandingSlots.filter(s => s.machine_id === overviewFilter.val)

              return (
                <div className="mt-4 border-t border-surface-600 pt-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      {filtered.length} matching lab{filtered.length !== 1 ? 's' : ''}
                    </span>
                    <button onClick={() => setOverviewFilter(null)} className="text-xs text-slate-400 hover:text-slate-600 transition-colors">
                      Clear
                    </button>
                  </div>
                  {filtered.length === 0 ? (
                    <div className="text-sm text-slate-400 text-center py-4">No labs match this filter</div>
                  ) : (
                    <div className="space-y-2">
                      {filtered.map(s => (
                        <button
                          key={s.id}
                          onClick={() => setViewSlot(s)}
                          className="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-lg border border-surface-600 bg-white hover:bg-surface-700 hover:border-brand-300 transition-all group"
                        >
                          <Badge variant={PRIORITY_VARIANT[s.priority] ?? 'medium'}>{s.priority}</Badge>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-slate-900 truncate">{s.title}</div>
                            <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                              {s.sample_id && <span className="font-mono">{s.sample_id}</span>}
                              {s.machine_id && <span>{s.machine_id === 'machine_pressure' ? 'Bay 1' : 'Bay 2'}</span>}
                              {s.technician_name && <span>{s.technician_name}</span>}
                              {s.scheduled_at && <span>{format(parseISO(s.scheduled_at), 'MMM d, h:mm a')}</span>}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {s.estimated_duration_min && (
                              <span className="text-xs text-slate-400">{s.estimated_duration_min} min</span>
                            )}
                            <Badge variant={s.status === 'in_progress' ? 'pending' : 'info'}>
                              {s.status === 'in_progress' ? 'In Progress' : 'Scheduled'}
                            </Badge>
                            <svg className="w-3.5 h-3.5 text-slate-300 group-hover:text-brand-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })()}
          </div>

          {/* AI Balance button */}
          <div className="flex items-center gap-3 pt-2 border-t border-surface-600">
            <button
              onClick={handleBalance}
              disabled={balancing || outstandingSlots.length === 0}
              className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {balancing ? <Spinner className="w-4 h-4" /> : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              )}
              {balancing ? 'AI is planning…' : 'AI Balance Schedule'}
            </button>
            {outstandingSlots.length === 0 && (
              <span className="text-xs text-slate-500">No outstanding tests to plan</span>
            )}
            {balancePlan && !balancing && (
              <span className="text-xs text-emerald-700 flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Plan generated
              </span>
            )}
          </div>

          {/* Balance plan results */}
          {balancePlan && (
            <div className="space-y-4 pt-2 border-t border-surface-600">
              <div className="text-sm text-slate-600 bg-brand-100 border border-brand-200 rounded-lg px-4 py-3">
                {balancePlan.overall_summary}
              </div>

              {/* Shifts */}
              <div className="grid grid-cols-1 gap-4">
                {shifts.map(shift => {
                  const assigned = balancePlan.assignments.filter(a => a.shift === shift.name)
                  const summary = balancePlan.shifts_summary?.[shift.name]
                  const totalMin = summary?.total_min ?? assigned.reduce((s, a) => s + (a.estimated_duration_min ?? 0), 0)
                  const utilPct = Math.min(100, Math.round((assigned.length / shift.capacity) * 100))
                  return (
                    <div key={shift.name} className="card p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="text-sm font-semibold text-slate-900">{shift.name} Shift</div>
                          <span className="text-xs text-slate-500">{shift.start_time} – {shift.end_time}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-slate-500">{Math.round(totalMin / 60 * 10) / 10} hrs</span>
                          <span className="text-xs font-mono text-brand-700">{assigned.length}/{shift.capacity} tests</span>
                          <div className="w-24 h-1.5 bg-surface-600 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${utilPct > 80 ? 'bg-amber-500' : 'bg-brand-500'}`}
                              style={{ width: `${utilPct}%` }}
                            />
                          </div>
                        </div>
                      </div>
                      {assigned.length === 0 ? (
                        <div className="text-xs text-slate-600 italic">No tests assigned to this shift</div>
                      ) : (
                        <div className="space-y-1.5">
                          {assigned.map(a => (
                            <div key={a.test_id} className="flex items-start gap-3 text-xs bg-surface-700/50 rounded px-3 py-2">
                              <Badge variant={
                                a.priority === 'critical' ? 'critical' :
                                a.priority === 'high' ? 'high' :
                                a.priority === 'normal' ? 'medium' : 'low'
                              }>{a.priority}</Badge>
                              <div className="flex-1 min-w-0">
                                <div className="text-slate-700 font-medium truncate">{a.title}</div>
                                <div className="text-slate-500 mt-0.5">{a.reason}</div>
                              </div>
                              <span className="text-slate-600 flex-shrink-0">{a.estimated_duration_min} min</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Unassigned */}
              {balancePlan.unassigned && balancePlan.unassigned.length > 0 && (
                <div className="card p-4 border-amber-200">
                  <div className="text-xs font-semibold text-amber-700 mb-2">Could Not Assign ({balancePlan.unassigned.length})</div>
                  <div className="space-y-1">
                    {balancePlan.unassigned.map(u => (
                      <div key={u.test_id} className="text-xs text-slate-500 flex gap-2">
                        <span className="text-slate-600">#{u.test_id}</span>
                        <span className="truncate">{u.title}</span>
                        <span className="text-amber-600 flex-shrink-0">— {u.reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* KPI row */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Scheduled',      value: summary.scheduled_count,    color: 'text-blue-700' },
            { label: 'In Progress',    value: summary.in_progress_count,  color: 'text-amber-700' },
            { label: 'Completed Today', value: summary.completed_today,   color: 'text-emerald-700' },
            { label: 'Critical Pending', value: summary.critical_pending, color: 'text-red-600' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card px-5 py-4">
              <div className={`text-3xl font-bold font-mono ${color}`}>{value}</div>
              <div className="text-xs text-slate-500 mt-1">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Technician load bars */}
      {summary && summary.technician_load.length > 0 && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-600 mb-4">Technician Workload</h2>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            {summary.technician_load.map(t => (
              <div key={t.id} className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-600 truncate">{t.name}</span>
                  <span className="text-xs font-mono text-amber-700 ml-1">{t.active_tests}</span>
                </div>
                <div className="h-1.5 bg-surface-600 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-500 rounded-full transition-all"
                    style={{ width: `${Math.min(100, (t.active_tests ?? 0) * 20)}%` }}
                  />
                </div>
                <div className="text-xs text-slate-600 truncate">{t.specialty}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select className="input w-auto text-sm" value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}>
          <option value="active">Active (scheduled + in-progress)</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select className="input w-auto text-sm" value={filterTech}
          onChange={e => setFilterTech(Number(e.target.value) || '')}>
          <option value="">All Technicians</option>
          {techs.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select className="input w-auto text-sm" value={filterMachine}
          onChange={e => setFilterMachine(e.target.value)}>
          <option value="">All Machines</option>
          {machines.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <span className="text-xs text-slate-500 ml-auto">{slots.length} tests</span>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner />
          </div>
        ) : slots.length === 0 ? (
          <div className="text-center py-16 text-slate-500">
            <div className="text-4xl mb-3">📋</div>
            No tests in queue. Schedule one to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-surface-600 text-xs font-medium text-slate-500 uppercase tracking-wider">
                  <th className="px-4 py-3">Priority</th>
                  <th className="px-4 py-3">Test</th>
                  <th className="px-4 py-3">Machine</th>
                  <th className="px-4 py-3">Scheduled</th>
                  <th className="px-4 py-3">Duration</th>
                  <th className="px-4 py-3">Technician</th>
                  <th className="px-4 py-3">AI Prediction</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {slots.map(slot => (
                  <ScheduleRow
                    key={slot.id}
                    slot={slot}
                    techs={techs}
                    onUpdate={handleUpdate}
                    onDelete={handleDelete}
                    onView={setViewSlot}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showAdd && (
        <AddTestModal
          techs={techs}
          machines={machines}
          onSave={handleAdd}
          onClose={() => setShowAdd(false)}
        />
      )}
      {viewSlot && (
        <ViewTestModal slot={viewSlot} onClose={() => setViewSlot(null)} />
      )}
    </div>
  )
}
