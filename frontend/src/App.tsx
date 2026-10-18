import { Routes, Route } from "react-router-dom"
import { AppShell } from "@/components/AppShell"
import { ProjectsPage } from "@/pages/Projects"
import { CreateProjectPage } from "@/pages/CreateProject"
import { ProjectOverviewPage } from "@/pages/ProjectOverview"
import { MeetingsPage } from "@/pages/Meetings"
import { AddMeetingPage } from "@/pages/AddMeeting"
import { HistoryPage } from "@/pages/History"
import { ReviewQueuePage } from "@/pages/ReviewQueue"
import { ReportPage } from "@/pages/Report"
import { DashboardPage } from "@/pages/Dashboard"
import { MeetingDetailPage } from "@/pages/MeetingDetail"

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/new" element={<CreateProjectPage />} />
        <Route path="/projects/:id/overview" element={<ProjectOverviewPage />} />
        <Route path="/projects/:id/meetings" element={<MeetingsPage />} />
        <Route path="/projects/:id/meetings/add" element={<AddMeetingPage />} />
        <Route path="/meetings/:id" element={<MeetingDetailPage />} />
        <Route path="/projects/:id/history" element={<HistoryPage />} />
        <Route path="/projects/:id/review" element={<ReviewQueuePage />} />
        <Route path="/projects/:id/report" element={<ReportPage />} />
        <Route path="*" element={<ProjectsPage />} />
      </Routes>
    </AppShell>
  )
}