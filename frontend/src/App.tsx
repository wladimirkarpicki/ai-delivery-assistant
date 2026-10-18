import { Navigate, Route, Routes } from "react-router-dom"
import AppShell from "./components/AppShell"
import AddMeetingPage from "./pages/AddMeetingPage"
import DashboardPage from "./pages/DashboardPage"
import HistoryPage from "./pages/HistoryPage"
import MeetingDetailPage from "./pages/MeetingDetailPage"
import MeetingsPage from "./pages/MeetingsPage"
import NotFoundPage from "./pages/NotFoundPage"
import ProjectOverviewPage from "./pages/ProjectOverviewPage"
import ProjectsPage from "./pages/ProjectsPage"
import ReportPage from "./pages/ReportPage"
import ReviewQueuePage from "./pages/ReviewQueuePage"

export default function App() {
  return (
    <Routes>
      {/* Flask: GET / -> redirect to the projects page. */}
      <Route path="/" element={<Navigate to="/projects" replace />} />

      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectOverviewPage />} />
        <Route path="/projects/:projectId/meetings" element={<MeetingsPage />} />
        <Route path="/projects/:projectId/meetings/new" element={<AddMeetingPage />} />
        <Route path="/projects/:projectId/history" element={<HistoryPage />} />
        <Route path="/projects/:projectId/review" element={<ReviewQueuePage />} />
        <Route path="/projects/:projectId/report" element={<ReportPage />} />
        <Route path="/meetings/:meetingId" element={<MeetingDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
