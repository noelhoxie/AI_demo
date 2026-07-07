// ── Bronze layer machine readings ──────────────────────────────────────────────
export interface Reading {
  reading_id: string
  machine_id: string
  serial_number: string
  model_number: string
  test_type: string
  result_raw: 'PASS' | 'FAIL' | 'UNKNOWN'
  recorded_at: string
  source_table: string

  // Pressure tester fields
  pressure_psi?: number
  hold_time_sec?: number
  leak_rate_psi_min?: number
  ambient_temp_c?: number

  // Flow tester fields
  flow_rate_lpm?: number
  delta_p_bar?: number
  efficiency_pct?: number
  rpm?: number
  vibration_mm_s?: number

  // Attached
  enhancement?: Enhancement | null
  prediction?: Prediction | null
}

// ── Manual enhancement overlay ─────────────────────────────────────────────────
export interface Enhancement {
  id: number
  bronze_reading_id: string
  machine_id: string
  technician_id?: number
  technician_name?: string
  visual_inspection?: string
  anomalies_noted?: string
  corrective_actions?: string
  override_values: Record<string, number | string>
  manual_measurements: ManualMeasurement[]
  confidence_in_data: number  // 1-5
  notes?: string
  created_at: string
  updated_at: string
}

export interface ManualMeasurement {
  key: string
  label: string
  value: number | string
  unit?: string
}

// ── AI prediction ──────────────────────────────────────────────────────────────
export interface Prediction {
  id: number
  bronze_reading_id: string
  machine_id: string
  success_probability: number  // 0-100
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  risk_factors: string[]
  recommendations: string[]
  reasoning: string
  model_version: string
  generated_at: string
}

// ── Test schedule / leaderboard ────────────────────────────────────────────────
export interface TestSlot {
  id: number
  title: string
  sample_id?: string
  reading_id?: string
  machine_id?: string
  test_type?: string
  scheduled_at?: string
  estimated_duration_min: number
  priority: 'critical' | 'high' | 'normal' | 'low'
  technician_id?: number
  technician_name?: string
  technician_specialty?: string
  status: 'scheduled' | 'in_progress' | 'completed' | 'cancelled'
  started_at?: string
  completed_at?: string
  notes?: string
  // From joined prediction
  success_probability?: number
  risk_level?: Prediction['risk_level']
}

// ── Shift planning ─────────────────────────────────────────────────────────────
export interface ShiftDef {
  name: string
  start_time: string   // "06:00"
  end_time: string     // "14:00"
  capacity: number
}

export interface BalanceAssignment {
  test_id: number
  title: string
  shift: string
  priority: string
  machine_id?: string
  estimated_duration_min: number
  reason: string
}

export interface BalancePlan {
  assignments: BalanceAssignment[]
  shifts_summary: Record<string, { count: number; total_min: number; capacity: number }>
  unassigned: { test_id: number; title: string; reason: string }[]
  overall_summary: string
}

// ── Lab machine definition ─────────────────────────────────────────────────────
export interface Machine {
  id: string
  name: string
  type: string
  location: string
  table: string
}

// ── Technician ────────────────────────────────────────────────────────────────
export interface Technician {
  id: number
  name: string
  badge_id?: string
  specialty?: string
  email?: string
  is_active: boolean
  // From leaderboard summary
  active_tests?: number
  completed_today?: number
}

// ── Leaderboard summary ────────────────────────────────────────────────────────
export interface LeaderboardSummary {
  scheduled_count: number
  in_progress_count: number
  completed_today: number
  critical_pending: number
  technician_load: Technician[]
  risk_distribution: { risk_level: string; count: number }[]
}
