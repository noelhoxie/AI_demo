// ── Data Architecture page ─────────────────────────────────────────────────────
export default function ArchitecturePage() {
  return (
    <div className="p-8 space-y-8 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Data Architecture</h1>
        <p className="text-sm text-slate-500 mt-1">
          How lab machine data and manual technician inputs flow through Databricks into the platform
        </p>
      </div>

      {/* Diagram */}
      <div className="space-y-4">

        {/* ── Layer 1: Data Sources ── */}
        <LayerLabel>Data Sources</LayerLabel>
        <div className="grid grid-cols-3 gap-4">
          <SourceNode
            color="blue"
            icon={<MachineIcon />}
            title="Pressure / Leak Tester"
            subtitle="Bay 1 · machine_pressure"
            bullets={[
              'Pressure (psi)',
              'Hold time (sec)',
              'Leak rate (psi/min)',
              'Ambient temp (°C)',
            ]}
          />
          <SourceNode
            color="blue"
            icon={<MachineIcon />}
            title="Flow / Performance Tester"
            subtitle="Bay 2 · machine_flow"
            bullets={[
              'Flow rate (L/min)',
              'Delta P (bar)',
              'Efficiency (%)',
              'RPM · Vibration (mm/s)',
            ]}
          />
          <SourceNode
            color="amber"
            icon={<PersonIcon />}
            title="Technician Manual Input"
            subtitle="Web form · real-time"
            bullets={[
              'Visual inspection notes',
              'Anomalies noted',
              'Corrective actions',
              'Override result + confidence',
            ]}
          />
        </div>

        {/* ── Arrows down ── */}
        <div className="grid grid-cols-3 gap-4">
          <Arrow label="Automated feed" />
          <Arrow label="Automated feed" />
          <Arrow label="Form submission" color="amber" />
        </div>

        {/* ── Layer 2: Storage ── */}
        <LayerLabel>Storage Layer</LayerLabel>
        <div className="grid grid-cols-2 gap-4">
          <StorageNode
            color="brand"
            icon={<DatabricksIcon />}
            title="Databricks Delta Lake"
            subtitle="Bronze Layer · read-only"
            bullets={[
              'nah_demo.airtech_lab_bronze.machine_pressure_readings',
              'nah_demo.airtech_lab_bronze.machine_flow_readings',
              'Delta format · time-travel capable',
              'Queried via SQL Warehouse',
            ]}
          />
          <StorageNode
            color="emerald"
            icon={<DatabaseIcon />}
            title="Lakebase (Databricks Postgres)"
            subtitle="Write-back store · managed PostgreSQL"
            bullets={[
              'lab.reading_enhancements — manual overlays',
              'lab.predictions — AI-generated scores',
              'lab.test_schedule — upcoming test queue',
              'lab.technicians — personnel registry',
            ]}
          />
        </div>

        {/* ── Arrows down ── */}
        <div className="grid grid-cols-2 gap-4">
          <Arrow label="SQL Warehouse read" color="brand" />
          <Arrow label="psycopg2 connection pool" color="emerald" />
        </div>

        {/* ── Layer 3: Application ── */}
        <LayerLabel>Application Layer</LayerLabel>
        <div className="grid grid-cols-1 gap-4">
          <div className="card border border-brand-200 bg-brand-100 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                    d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                </svg>
              </div>
              <div>
                <div className="text-base font-semibold text-slate-900">Airtech Lab Intelligence Platform</div>
                <div className="text-xs text-slate-500">Flask API · React/TypeScript frontend · Deployed on Databricks Apps</div>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: 'Test Leaderboard', desc: 'Schedule queue, technician workload, AI risk scoring' },
                { label: 'Machine Readings', desc: 'Live bronze layer feed with pass/fail metrics' },
                { label: 'Enhance Readings', desc: 'Inline form for manual observations & overrides' },
                { label: 'Data Architecture', desc: 'This view — system overview' },
              ].map(({ label, desc }) => (
                <div key={label} className="bg-surface-700/60 rounded-lg px-3 py-2.5">
                  <div className="text-xs font-medium text-brand-700 mb-1">{label}</div>
                  <div className="text-xs text-slate-500">{desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Legend ── */}
        <div className="flex items-center gap-6 pt-2">
          <span className="text-xs text-slate-600 font-medium uppercase tracking-wider">Legend</span>
          <LegendItem color="blue" label="Lab machine (automated)" />
          <LegendItem color="amber" label="Manual / human input" />
          <LegendItem color="brand" label="Databricks platform" />
          <LegendItem color="emerald" label="Lakebase (PostgreSQL)" />
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function LayerLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-surface-600" />
      <span className="text-xs font-semibold text-slate-500 uppercase tracking-widest px-2">{children}</span>
      <div className="h-px flex-1 bg-surface-600" />
    </div>
  )
}

type Color = 'blue' | 'amber' | 'brand' | 'emerald'

const COLOR_BORDER: Record<Color, string> = {
  blue:    'border-blue-200 bg-blue-50',
  amber:   'border-amber-200 bg-amber-50',
  brand:   'border-brand-200 bg-brand-50',
  emerald: 'border-emerald-200 bg-emerald-50',
}
const COLOR_ICON: Record<Color, string> = {
  blue:    'bg-blue-700',
  amber:   'bg-amber-600',
  brand:   'bg-brand-600',
  emerald: 'bg-emerald-700',
}
const COLOR_TITLE: Record<Color, string> = {
  blue:    'text-blue-700',
  amber:   'text-amber-700',
  brand:   'text-brand-700',
  emerald: 'text-emerald-700',
}
const COLOR_ARROW: Record<Color, string> = {
  blue:    'text-blue-700',
  amber:   'text-amber-600',
  brand:   'text-brand-500',
  emerald: 'text-emerald-600',
}
const COLOR_DOT: Record<Color, string> = {
  blue:    'bg-blue-500',
  amber:   'bg-amber-500',
  brand:   'bg-brand-500',
  emerald: 'bg-emerald-500',
}

function SourceNode({ color, icon, title, subtitle, bullets }: {
  color: Color; icon: React.ReactNode; title: string; subtitle: string; bullets: string[]
}) {
  return (
    <div className={`card border ${COLOR_BORDER[color]} p-4 space-y-3`}>
      <div className="flex items-center gap-2.5">
        <div className={`w-8 h-8 rounded-lg ${COLOR_ICON[color]} flex items-center justify-center flex-shrink-0`}>
          {icon}
        </div>
        <div>
          <div className={`text-sm font-semibold ${COLOR_TITLE[color]}`}>{title}</div>
          <div className="text-xs text-slate-600">{subtitle}</div>
        </div>
      </div>
      <ul className="space-y-1">
        {bullets.map(b => (
          <li key={b} className="text-xs text-slate-500 flex items-start gap-1.5">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-slate-600 flex-shrink-0" />
            {b}
          </li>
        ))}
      </ul>
    </div>
  )
}

function StorageNode({ color, icon, title, subtitle, bullets }: {
  color: Color; icon: React.ReactNode; title: string; subtitle: string; bullets: string[]
}) {
  return (
    <div className={`card border ${COLOR_BORDER[color]} p-5 space-y-3`}>
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-lg ${COLOR_ICON[color]} flex items-center justify-center flex-shrink-0`}>
          {icon}
        </div>
        <div>
          <div className={`text-sm font-semibold ${COLOR_TITLE[color]}`}>{title}</div>
          <div className="text-xs text-slate-600">{subtitle}</div>
        </div>
      </div>
      <ul className="space-y-1.5">
        {bullets.map(b => (
          <li key={b} className="text-xs text-slate-500 flex items-start gap-1.5 font-mono">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-slate-600 flex-shrink-0 font-sans" />
            {b}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Arrow({ label, color = 'blue' }: { label: string; color?: Color }) {
  return (
    <div className="flex flex-col items-center gap-1 py-1">
      <div className={`text-xs ${COLOR_ARROW[color]}`}>
        <svg className="w-5 h-8" fill="none" viewBox="0 0 20 32" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M10 2 L10 22 M6 18 L10 26 L14 18" />
        </svg>
      </div>
      <span className="text-xs text-slate-600">{label}</span>
    </div>
  )
}

function LegendItem({ color, label }: { color: Color; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2.5 h-2.5 rounded-sm ${COLOR_DOT[color]}`} />
      <span className="text-xs text-slate-500">{label}</span>
    </div>
  )
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function MachineIcon() {
  return (
    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
    </svg>
  )
}

function PersonIcon() {
  return (
    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  )
}

function DatabricksIcon() {
  return (
    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M4 7l8-4 8 4v10l-8 4-8-4V7z" />
    </svg>
  )
}

function DatabaseIcon() {
  return (
    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3v10c0 1.657-3.582 3-8 3s-8-1.343-8-3V7z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 12c0 1.657 3.582 3 8 3s8-1.343 8-3" />
    </svg>
  )
}
