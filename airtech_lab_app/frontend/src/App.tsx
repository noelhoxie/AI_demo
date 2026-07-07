import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import AdminPage from './pages/Admin'
import DashboardPage from './pages/Dashboard'
import TestRunPage from './pages/TestRun'
import ProcedureBuilderPage from './pages/ProcedureBuilder'
import RunsPage from './pages/Runs'
import RunDetailPage from './pages/RunDetail'
import InspectionRecordsPage from './pages/InspectionRecords'
import InspectionRecordDetailPage from './pages/InspectionRecordDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="import" element={<Navigate to="/admin" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="test-run" element={<TestRunPage />} />
          <Route path="procedure-builder" element={<ProcedureBuilderPage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route path="runs/:runId" element={<RunDetailPage />} />
          <Route path="inspection/records" element={<InspectionRecordsPage />} />
          <Route path="inspection/records/:id" element={<InspectionRecordDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
