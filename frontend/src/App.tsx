import type { ReactNode } from "react"
import { lazy, Suspense } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import AppShell from "./components/AppShell"
import { NotFoundBody } from "./pages/NotFound"
import LoginPage from "./pages/LoginPage"
import SetupPage from "./pages/SetupPage"
import { AuthProvider, useAuth } from "./lib/useAuth"

// Every page below the shell is loaded on demand. The dashboard pulls in
// recharts and its d3 dependencies, which measured at 380 kB of the
// 703 kB single chunk. Eager loading meant every visitor paid for the
// charting library they never opened.
const AddMeetingPage = lazy(() => import("./pages/AddMeetingPage"))
const DashboardPage = lazy(() => import("./pages/DashboardPage"))
const HistoryPage = lazy(() => import("./pages/HistoryPage"))
const MeetingDetailPage = lazy(() => import("./pages/MeetingDetailPage"))
const MeetingsPage = lazy(() => import("./pages/MeetingsPage"))
const PasswordPage = lazy(() => import("./pages/PasswordPage"))
const ProjectOverviewPage = lazy(() => import("./pages/ProjectOverviewPage"))
const ProjectsPage = lazy(() => import("./pages/ProjectsPage"))
const ReportPage = lazy(() => import("./pages/ReportPage"))
const ReviewQueuePage = lazy(() => import("./pages/ReviewQueuePage"))
const UsersPage = lazy(() => import("./pages/UsersPage"))

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
      <Suspense fallback={null}>
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
            <Route
              path="/projects/:projectId"
              element={<ProjectOverviewPage />}
            />
            <Route
              path="/projects/:projectId/meetings"
              element={<MeetingsPage />}
            />
            <Route
              path="/projects/:projectId/meetings/new"
              element={<AddMeetingPage />}
            />
            <Route path="/projects/:projectId/history" element={<HistoryPage />} />
            <Route
              path="/projects/:projectId/review"
              element={<ReviewQueuePage />}
            />
            <Route path="/projects/:projectId/report" element={<ReportPage />} />
            <Route
              path="/meetings/:meetingId"
              element={<MeetingDetailPage />}
            />
            <Route path="/password" element={<PasswordPage />} />
            <Route
              path="/users"
              element={
                <RequireAdmin>
                  <UsersPage />
                </RequireAdmin>
              }
            />
            <Route path="*" element={<NotFoundBody />} />
          </Route>
        </Routes>
      </Suspense>
    </AuthProvider>
  )
}
