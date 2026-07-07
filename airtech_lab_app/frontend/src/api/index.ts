import client from './client'
import type {
  Reading, Enhancement, Prediction, TestSlot,
  Machine, Technician, LeaderboardSummary, ShiftDef, BalancePlan,
} from '../types'

// ── Machines ───────────────────────────────────────────────────────────────────
export const getMachines = () =>
  client.get<Machine[]>('/machines')

// ── Readings ───────────────────────────────────────────────────────────────────
export const getReadings = (params?: { machine_id?: string; limit?: number; offset?: number }) =>
  client.get<Reading[]>('/readings', params)

export const getReading = (machineId: string, readingId: string) =>
  client.get<Reading>(`/readings/${machineId}/${readingId}`)

// ── Enhancements ───────────────────────────────────────────────────────────────
export const getEnhancements = (params?: { machine_id?: string; technician_id?: number }) =>
  client.get<Enhancement[]>('/enhancements', params)

export const getEnhancement = (readingId: string) =>
  client.get<Enhancement>(`/enhancements/${readingId}`)

export const createEnhancement = (data: Partial<Enhancement> & { bronze_reading_id: string }) =>
  client.post<Enhancement>('/enhancements', data)

export const updateEnhancement = (id: number, data: Partial<Enhancement>) =>
  client.patch<Enhancement>(`/enhancements/${id}`, data)

// ── Predictions ────────────────────────────────────────────────────────────────
export const getPredictions = () =>
  client.get<Prediction[]>('/predictions')

export const getPrediction = (readingId: string) =>
  client.get<Prediction>(`/predictions/${readingId}`)

export const triggerPrediction = (readingId: string, machineId: string) =>
  client.post(`/predictions/${readingId}/generate`, { machine_id: machineId })

// ── Technicians ────────────────────────────────────────────────────────────────
export const getTechnicians = () =>
  client.get<Technician[]>('/technicians')

export const createTechnician = (data: Partial<Technician>) =>
  client.post<Technician>('/technicians', data)

export const getTechnicianSchedule = (techId: number) =>
  client.get<TestSlot[]>(`/technicians/${techId}/schedule`)

// ── Schedule / Leaderboard ─────────────────────────────────────────────────────
export const getSchedule = (params?: {
  status?: string
  technician_id?: number
  machine_id?: string
}) =>
  client.get<TestSlot[]>('/schedule', params as Record<string, string | number | undefined>)

export const createScheduleSlot = (data: Partial<TestSlot>) =>
  client.post<TestSlot>('/schedule', data)

export const updateScheduleSlot = (id: number, data: Partial<TestSlot>) =>
  client.patch<TestSlot>(`/schedule/${id}`, data)

export const cancelScheduleSlot = (id: number) =>
  client.delete(`/schedule/${id}`)

export const getLeaderboardSummary = () =>
  client.get<LeaderboardSummary>('/leaderboard/summary')

export const balanceSchedule = (shifts: ShiftDef[]) =>
  client.post<BalancePlan>('/schedule/balance', { shifts })
