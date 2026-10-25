/**
 * Typed client for the FastAPI backend (api.py).
 *
 * All shapes mirror the JSON serializers on the server one-to-one;
 * validation failures surface as ApiError with the server's message.
 * Every request carries the bearer token from lib/auth.ts; when the
 * API refuses a token that was sent (401), the token is dead and the
 * client returns to the sign-in page.
 */

import { getToken, removeToken, type AuthUser } from "./auth"

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const token = getToken()

  if (token) headers.set("Authorization", `Bearer ${token}`)

  const response = await fetch(path, { ...init, headers })

  if (!response.ok) {
    // A 401 for an authenticated request means the token is gone
    // (expired, revoked, account deleted): drop it and sign in
    // again. Unauthenticated 401s are ordinary login refusals and
    // stay on the sign-in page as errors.
    if (response.status === 401 && token) {
      removeToken()
      window.location.assign("/login")
    }

    let message = `${response.status} ${response.statusText}`

    try {
      const body = await response.json()
      if (body && typeof body.error === "string") message = body.error
      else if (body && typeof body.detail === "string") message = body.detail
    } catch {
      // non-JSON error body: keep the status line
    }

    throw new ApiError(message, response.status)
  }

  return (await response.json()) as T
}

// ---------------------------------------------------------------------------
// Shapes

export interface ProjectSummary {
  id: number
  name: string
  description: string
  updated_at: string | null
}

export interface ProjectStateInfo {
  delivery_status: string
  progress_summary: string
  completed_items: string[]
  in_progress_items: string[]
}

export interface Risk {
  id: number
  title: string
  description: string
  impact: string
  mitigation: string
  status: string
  resolved_at: string | null
}

export interface Blocker {
  id: number
  title: string
  description: string
  status: string
  resolved_at: string | null
}

export interface ActionItem {
  id: number
  title: string
  details: string
  owner: string | null
  due_date: string | null
  status: string
  completed_at: string | null
}

export interface ProjectOverview {
  project: ProjectSummary
  state: ProjectStateInfo
  risks: Risk[]
  resolved_risks: Risk[]
  blockers: Blocker[]
  resolved_blockers: Blocker[]
  actions: ActionItem[]
  completed_actions: ActionItem[]
  meeting_count: number
  needs_review_count: number
}

export interface MeetingSummary {
  id: number
  project_id: number
  title: string
  source_filename: string | null
  provider: string
  model: string
  created_at: string | null
}

export interface HistoryEventChange {
  field: string
  old: unknown
  new: unknown
}

export interface HistoryEvent {
  id: number
  project_id: number
  meeting_id: number
  entity_type: string
  entity_id: number | null
  event_type: string
  summary: string
  before_data: Record<string, unknown> | null
  after_data: Record<string, unknown> | null
  created_at: string | null
  changes: HistoryEventChange[]
}

export interface MeetingDetail {
  meeting: MeetingSummary & {
    original_text: string
    analysis_text: string
    analysis_json: Record<string, unknown>
    project_name: string
  }
  events: HistoryEvent[]
}

export interface HistoryPage {
  project: ProjectSummary
  events: HistoryEvent[]
  type_counts: Record<string, number>
  selected_type: string
}

export interface ReviewTarget {
  id: number
  title: string
}

export interface ReviewQueueItem {
  event: HistoryEvent
  plan_item: Record<string, unknown>
  new_item: Record<string, unknown>
  targets: ReviewTarget[]
}

export interface DashboardRow {
  project: { id: number; name: string }
  status: string
  progress: string
  open_risks: number
  open_blockers: number
  open_actions: number
  meeting_count: number
  last_meeting: string | null
}

export interface MetricsTotals {
  projects: number
  meetings: number
  decisions: number
  history_events: number
  open_risks: number
  open_blockers: number
  open_actions: number
}

export interface StatusDistributionEntry {
  status: string
  count: number
}

export interface OpenItemsMixEntry {
  kind: "risks" | "blockers" | "actions"
  count: number
}

export interface PerProjectMetrics {
  project_id: number
  name: string
  meetings: number
  open_risks: number
  open_blockers: number
  open_actions: number
}

export interface RiskImpactMetrics {
  impact: string
  open: number
  resolved: number
}

export interface ActivityTimelineEntry {
  month: string
  meetings: number
  events: number
}

export interface ActionOwnerMetrics {
  owner: string
  open: number
  completed: number
}

export interface Metrics {
  totals: MetricsTotals
  status_distribution: StatusDistributionEntry[]
  open_items_mix: OpenItemsMixEntry[]
  per_project: PerProjectMetrics[]
  risk_impacts: RiskImpactMetrics[]
  activity_timeline: ActivityTimelineEntry[]
  action_owners: ActionOwnerMetrics[]
}

export interface HealthInfo {
  analysis_ready: boolean
  model: string | null
  error: string | null
}

export interface ManualResolveResult {
  status: string
  level: "success" | "warning"
  message: string
}

export interface MeetingAnalysisFinding {
  title?: string
  description?: string
  impact?: string
  mitigation?: string
  details?: string
  owner?: string
  due_date?: string
  status?: string
}

export interface MeetingAnalysis {
  executive_summary?: string
  project_status?: string
  progress_summary?: string
  completed_items?: string[]
  in_progress_items?: string[]
  risks?: MeetingAnalysisFinding[]
  blockers?: MeetingAnalysisFinding[]
  action_items?: MeetingAnalysisFinding[]
  decisions?: MeetingAnalysisFinding[]
}

// ---------------------------------------------------------------------------
// Endpoints

export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>("/api/health")
}

export function getDashboard(): Promise<{ rows: DashboardRow[] }> {
  return request<{ rows: DashboardRow[] }>("/api/dashboard")
}

export function getMetrics(): Promise<Metrics> {
  return request<Metrics>("/api/metrics")
}

export function getProjects(): Promise<{ projects: ProjectSummary[] }> {
  return request<{ projects: ProjectSummary[] }>("/api/projects")
}

export function createProject(
  name: string,
  description: string,
): Promise<{ id: number; name: string }> {
  return request<{ id: number; name: string }>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  })
}

export function getProjectOverview(
  projectId: number,
): Promise<ProjectOverview> {
  return request<ProjectOverview>(`/api/projects/${projectId}`)
}

export function getMeetings(
  projectId: number,
): Promise<{ project: ProjectSummary; meetings: MeetingSummary[] }> {
  return request<{ project: ProjectSummary; meetings: MeetingSummary[] }>(
    `/api/projects/${projectId}/meetings`,
  )
}

export interface AddMeetingInput {
  title: string
  meeting_notes: string
  file?: File | null
}

export function addMeeting(
  projectId: number,
  input: AddMeetingInput,
): Promise<{ meeting_id: number; warning?: string }> {
  const form = new FormData()
  form.set("title", input.title)
  form.set("meeting_notes", input.meeting_notes)

  if (input.file) form.set("meeting_file", input.file)

  return request<{ meeting_id: number; warning?: string }>(
    `/api/projects/${projectId}/meetings`,
    { method: "POST", body: form },
  )
}

export function getMeeting(meetingId: number): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/api/meetings/${meetingId}`)
}

export function getHistory(
  projectId: number,
  type?: string,
): Promise<HistoryPage> {
  const suffix = type ? `?type=${encodeURIComponent(type)}` : ""
  return request<HistoryPage>(`/api/projects/${projectId}/history${suffix}`)
}

export function getReport(
  projectId: number,
): Promise<{ project: ProjectSummary; report: string }> {
  return request<{ project: ProjectSummary; report: string }>(
    `/api/projects/${projectId}/report`,
  )
}

export function reportDownloadUrl(projectId: number): string {
  return `/api/projects/${projectId}/report?download=1`
}

export function getReviewQueue(
  projectId: number,
): Promise<{ project: ProjectSummary; queue: ReviewQueueItem[] }> {
  return request<{ project: ProjectSummary; queue: ReviewQueueItem[] }>(
    `/api/projects/${projectId}/review`,
  )
}

export function resolveReview(
  projectId: number,
  eventId: number,
  body: { action: string; target_item_id?: number | null; note?: string },
): Promise<{ ok: boolean; action: string; target_item_id: number | null }> {
  return request<{ ok: boolean; action: string; target_item_id: number | null }>(
    `/api/projects/${projectId}/review/${eventId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  )
}

export function manualResolve(
  projectId: number,
  itemType: "risk" | "blocker" | "action_item",
  itemId: number,
  action: "resolve" | "reopen",
  note = "",
): Promise<ManualResolveResult> {
  return request<ManualResolveResult>(
    `/api/projects/${projectId}/items/${itemType}/${itemId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    },
  )
}

// ---------------------------------------------------------------------------
// Authentication and users

export interface AuthResponse {
  access_token: string
  token_type: string
  user: AuthUser
}

export interface UserRow {
  id: number
  username: string
  role: "user" | "admin"
  is_you: boolean
}

export interface UserCreateInput {
  username: string
  password: string
  role: "user" | "admin"
}

export function authLogin(
  username: string,
  password: string,
): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  })
}

export function authSetup(
  username: string,
  password: string,
): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  })
}

export function getMe(): Promise<AuthUser> {
  return request<AuthUser>("/api/auth/me")
}

export function changeOwnPassword(
  currentPassword: string,
  password: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, password }),
  })
}

export function getUsers(): Promise<UserRow[]> {
  return request<UserRow[]>("/api/users")
}

export function createUser(input: UserCreateInput): Promise<UserRow> {
  return request<UserRow>("/api/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
}

export function updateUser(
  userId: number,
  body: { role?: "user" | "admin"; password?: string },
): Promise<UserRow> {
  return request<UserRow>(`/api/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function deleteUser(userId: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/users/${userId}`, {
    method: "DELETE",
  })
}

export function resetUserPassword(
  userId: number,
  password: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/users/${userId}/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  })
}
