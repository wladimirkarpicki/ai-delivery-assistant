import type { ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import AppShell from "./components/AppShell"
import AddMeetingPage from "./pages/AddMeetingPage"
import DashboardPage from "./pages/DashboardPage"
import HistoryPage from "./pages/HistoryPage"
import LoginPage from "./pages/LoginPage"
import MeetingDetailPage from "./pages/MeetingDetailPage"
import MeetingsPage from "./pages/MeetingsPage"
import NotFoundPage from "./pages/NotFoundPage"
import PasswordPage from "./pages/PasswordPage"
import ProjectOverviewPage from "./pages/ProjectOverviewPage"
import ProjectsPage from "./pages/ProjectsPage"
import ReportPage from "./pages/ReportPage"
import ReviewQueuePage from "./pages/ReviewQueuePage"
import SetupPage from "./pages/SetupPage"
import UsersPage from "./pages/UsersPage"
import { AuthProvider, useAuth } from "./lib/useAuth"

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) return null

  if (!user) return <Navigate to="/login" replace />

  return <>{children}</>
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  if (user?.role !== "admin") return <Navigate to="/dashboard" replace />

  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/setup" element={<SetupPage />} />

        {/* Flask: GET / -> redirect to the projects page. */}
        <Route path="/" element={<Navigate to="/projects" replace />} />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectOverviewPage />} />
          <Route path="/projects/:projectId/meetings" element={<MeetingsPage />} />
          <Route path="/projects/:projectId/meetings/new" element={<AddMeetingPage />} />
          <Route path="/projects/:projectId/history" element={<HistoryPage />} />
          <Route path="/projects/:projectId/review" element={<ReviewQueuePage />} />
          <Route path="/projects/:projectId/report" element={<ReportPage />} />
          <Route path="/meetings/:meetingId" element={<MeetingDetailPage />} />
          <Route path="/password" element={<PasswordPage />} />
          <Route
            path="/users"
            element={
              <RequireAdmin>
                <UsersPage />
              </RequireAdmin>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
