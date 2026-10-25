import { useEffect, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { Link } from "react-router-dom"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { getDashboard, getMetrics } from "../lib/api"
import type { DashboardRow, Metrics } from "../lib/api"
import { chartTheme } from "../lib/chartTheme"
import { useTheme } from "../lib/useTheme"
import { fmtDate, humanStatus, plural } from "../lib/format"

/**
 * The cross-project dashboard, v2: a KPI strip of the six numbers that
 * matter, five meaningful charts (delivery status, open-risk profile,
 * open work per project, actions by owner, activity timeline), and the
 * original project cards below. Both requests load in parallel; each
 * band renders as its data arrives. No chart animations, quiet axes,
 * and empty states that stay out of the way.
 */

/** Shown when /api/metrics itself fails, so the charts degrade to their empty states. */
const EMPTY_METRICS: Metrics = {
  totals: {
    projects: 0,
    meetings: 0,
    decisions: 0,
    history_events: 0,
    open_risks: 0,
    open_blockers: 0,
    open_actions: 0,
    resolved_risks: 0,
    resolved_blockers: 0,
    resolved_actions: 0,
    meetings_last_30d: 0,
  },
  resolution_rate: 1.0,
  status_distribution: [],
  per_project: [],
  risk_impacts: [],
  activity_timeline: [],
  action_owners: [],
}

/** The impacts the risk-profile donut shows, worst first. */
const IMPACT_ORDER = ["high", "medium", "low"] as const

function ellipsize(value: string, max = 18): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

/** "unknown" reads as "Not started" everywhere on the dashboard. */
function statusLabel(status: string): string {
  return status === "unknown" ? "Not started" : humanStatus(status)
}

/** A chart panel: heading, hint line, the chart (or its empty state), and an optional footer legend. */
function ChartPanel(props: {
  title: string
  hint?: string
  wide?: boolean
  bodyClass?: string
  height?: number
  empty: string | null
  label: string
  footer?: ReactNode
  children: ReactNode
}) {
  return (
    <section className={`panel${props.wide ? " panel--wide" : ""}`}>
      <h2>{props.title}</h2>
      {props.hint ? <p className="chart-sub">{props.hint}</p> : null}

      {props.empty === null ? (
        <>
          <div
            className={`chart-body${props.bodyClass ? ` ${props.bodyClass}` : ""}`}
            role="img"
            aria-label={props.label}
            style={props.height === undefined ? undefined : { height: `${props.height}px` }}
          >
            {props.children}
          </div>
          {props.footer}
        </>
      ) : (
        <p className="chart-empty">{props.empty}</p>
      )}
    </section>
  )
}

/** A donut with its total standing in the hole: the quietest way to read a share. */
function DonutHole(props: { value: number | string; label: string }) {
  return (
    <div className="donut-center" aria-hidden="true">
      <span className="donut-center__value">{props.value}</span>
      <span className="donut-center__label">{props.label}</span>
    </div>
  )
}

export default function DashboardPage() {
  const theme = useTheme()
  const t = chartTheme(theme)
  const [rows, setRows] = useState<DashboardRow[] | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)

  useEffect(() => {
    getDashboard()
      .then((data) => setRows(data.rows))
      .catch(() => setRows([]))
    getMetrics()
      .then((data) => setMetrics(data))
      .catch(() => setMetrics(EMPTY_METRICS))
  }, [])

  if (rows === null && metrics === null) return null

  const m = metrics ?? EMPTY_METRICS

  const axisTick = { fill: t.axis, fontSize: 12 }
  const tooltipContentStyle: CSSProperties = {
    backgroundColor: t.tooltip.background,
    border: `1px solid ${t.tooltip.border}`,
    borderRadius: "0.7rem",
    padding: "0.5rem 0.75rem",
    color: t.tooltip.text,
    fontSize: "0.75rem",
  }
  const tooltipLabelStyle = { color: t.tooltip.text, fontWeight: 600 }
  const tooltipItemStyle = { color: t.tooltip.text }
  const renderLegend = (value: unknown) => (
    <span style={{ color: t.axis, fontSize: "0.75rem" }}>{String(value)}</span>
  )

  const statusColorOf = (status: string): string => {
    switch (status.replace(/\s+/g, "_")) {
      case "delivered":
        return t.status.delivered
      case "on_track":
        return t.status.on_track
      case "at_risk":
        return t.status.at_risk
      case "blocked":
        return t.status.blocked
      default:
        return t.status.unknown
    }
  }

  const impactColorOf = (impact: string): string => {
    switch (impact) {
      case "high":
        return t.impact.high
      case "medium":
        return t.impact.medium
      case "low":
        return t.impact.low
      default:
        return t.muted
    }
  }

  // Chart data, derived straight from the metrics payload.
  const statusData = m.status_distribution.map((entry) => ({
    status: entry.status,
    name: statusLabel(entry.status),
    value: entry.count,
  }))

  // Only open risks, by impact; unknown-impact risks join as a muted
  // "Not assessed" slice so the donut always matches the KPI count.
  const impactData: Array<{ impact: string; label: string; open: number }> =
    IMPACT_ORDER.map((impact) => {
      const entry = m.risk_impacts.find((candidate) => candidate.impact === impact)
      return {
        impact,
        label: impact[0].toUpperCase() + impact.slice(1),
        open: entry ? entry.open : 0,
      }
    })

  const unknownImpact = m.risk_impacts.find(
    (candidate) => candidate.impact === "unknown",
  )

  if (unknownImpact && unknownImpact.open > 0) {
    impactData.push({
      impact: "unknown",
      label: "Not assessed",
      open: unknownImpact.open,
    })
  }

  const openImpacts = impactData.filter((entry) => entry.open > 0)

  // Top six projects by currently open work.
  const openWork = m.per_project
    .map((project) => ({
      name: project.name,
      open_risks: project.open_risks,
      open_blockers: project.open_blockers,
      open_actions: project.open_actions,
      open_total: project.open_risks + project.open_blockers + project.open_actions,
    }))
    .filter((project) => project.open_total > 0)
    .sort((a, b) => b.open_total - a.open_total)
    .slice(0, 6)

  const openTotal =
    m.totals.open_risks + m.totals.open_blockers + m.totals.open_actions
  const ownersTotal = m.action_owners.reduce(
    (sum, entry) => sum + entry.open + entry.completed,
    0,
  )
  const openWorkHeight = Math.max(220, 38 * openWork.length + 24)

  // Six KPIs, each one answerable at a glance.
  const activeProjects = m.status_distribution
    .filter((entry) => entry.status !== "unknown")
    .reduce((sum, entry) => sum + entry.count, 0)

  const kpis: Array<{ label: string; value: number | string }> = [
    { label: "Active projects", value: activeProjects },
    { label: "Open risks", value: m.totals.open_risks },
    { label: "Open actions", value: m.totals.open_actions },
    { label: "Open blockers", value: m.totals.open_blockers },
    { label: "Resolution rate", value: `${Math.round(m.resolution_rate * 100)}%` },
    { label: "Meetings · 30d", value: m.totals.meetings_last_30d },
  ]

  return (
    <>
      <div className="page-heading">
        <div>
          <Link to="/projects">← Projects</Link>
          <span className="eyebrow">Cross-project view</span>
          <h1>Dashboard</h1>
          <p>Every project at a glance.</p>
        </div>
      </div>

      {metrics !== null && (
        <div className="kpi-strip" aria-label="Cross-project totals">
          {kpis.map((kpi) => (
            <div className="kpi" key={kpi.label}>
              <span className="kpi-label">{kpi.label}</span>
              <span className="kpi-value">{kpi.value}</span>
            </div>
          ))}
        </div>
      )}

      {metrics !== null && (
        <div className="cards metrics-grid">
          <ChartPanel
            title="Delivery status"
            hint="Every project by its current delivery status."
            empty={m.totals.projects === 0 ? "No projects yet." : null}
            label={`Projects by delivery status: ${statusData
              .map((entry) => `${entry.name} ${entry.value}`)
              .join(", ")}`}
            footer={
              <ul className="chart-legend">
                {statusData.map((entry) => (
                  <li key={entry.status}>
                    <span
                      className="swatch"
                      style={{ backgroundColor: statusColorOf(entry.status) }}
                    />
                    {entry.name}: {entry.value}
                  </li>
                ))}
              </ul>
            }
          >
            <div className="donut">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius="60%"
                    outerRadius="82%"
                    paddingAngle={2}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {statusData.map((entry) => (
                      <Cell
                        key={entry.status}
                        fill={statusColorOf(entry.status)}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={tooltipContentStyle}
                    labelStyle={tooltipLabelStyle}
                    itemStyle={tooltipItemStyle}
                  />
                </PieChart>
              </ResponsiveContainer>
              <DonutHole value={m.totals.projects} label="projects" />
            </div>
          </ChartPanel>

          <ChartPanel
            title="Risk profile"
            hint="Open risks by impact; resolution progress lives in the KPI strip."
            empty={m.totals.open_risks === 0 ? "No open risks." : null}
            label={`Open risks by impact: ${openImpacts
              .map((entry) => `${entry.label} ${entry.open}`)
              .join(", ")}`}
            footer={
              <ul className="chart-legend">
                {openImpacts.map((entry) => (
                  <li key={entry.impact}>
                    <span
                      className="swatch"
                      style={{ backgroundColor: impactColorOf(entry.impact) }}
                    />
                    {entry.label}: {entry.open} open
                  </li>
                ))}
              </ul>
            }
          >
            <div className="donut">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={openImpacts}
                    dataKey="open"
                    nameKey="label"
                    cx="50%"
                    cy="50%"
                    innerRadius="60%"
                    outerRadius="82%"
                    paddingAngle={2}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {openImpacts.map((entry) => (
                      <Cell
                        key={entry.impact}
                        fill={impactColorOf(entry.impact)}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={tooltipContentStyle}
                    labelStyle={tooltipLabelStyle}
                    itemStyle={tooltipItemStyle}
                  />
                </PieChart>
              </ResponsiveContainer>
              <DonutHole value={m.totals.open_risks} label="open risks" />
            </div>
          </ChartPanel>

          <ChartPanel
            title="Open work by project"
            hint="Open risks, blockers, and actions, top six projects."
            empty={
              m.per_project.length === 0
                ? "No projects yet."
                : openTotal === 0
                  ? "No open risks, blockers, or actions."
                  : null
            }
            label={`Open work per project: ${openWork
              .map(
                (project) =>
                  `${project.name}: ${project.open_risks} risks, ${project.open_blockers} blockers, ${project.open_actions} actions`,
              )
              .join("; ")}`}
            height={openWorkHeight}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={openWork}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={t.grid}
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  allowDecimals={false}
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={140}
                  tick={axisTick}
                  tickFormatter={(value: string) => ellipsize(value)}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={tooltipContentStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  cursor={{ fill: t.grid }}
                />
                <Legend formatter={renderLegend} />
                <Bar
                  dataKey="open_risks"
                  name="Risks"
                  stackId="open"
                  fill={t.kind.risks}
                  barSize={12}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="open_blockers"
                  name="Blockers"
                  stackId="open"
                  fill={t.kind.blockers}
                  barSize={12}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="open_actions"
                  name="Actions"
                  stackId="open"
                  fill={t.kind.actions}
                  barSize={12}
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Actions by owner"
            hint="Open and completed action items per owner; unowned items count as unassigned."
            empty={ownersTotal === 0 ? "No action items yet." : null}
            label={`Action items by owner: ${m.action_owners
              .map(
                (entry) =>
                  `${entry.owner}: ${entry.open} open, ${entry.completed} completed`,
              )
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={m.action_owners}
                margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={t.grid}
                  vertical={false}
                />
                <XAxis
                  dataKey="owner"
                  tick={axisTick}
                  tickFormatter={(value: string) => ellipsize(value, 12)}
                  axisLine={false}
                  tickLine={false}
                  interval={0}
                />
                <YAxis
                  allowDecimals={false}
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                  width={32}
                />
                <Tooltip
                  contentStyle={tooltipContentStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  cursor={{ fill: t.grid }}
                />
                <Legend formatter={renderLegend} />
                <Bar
                  dataKey="open"
                  name="Open"
                  stackId="owner"
                  fill={t.kind.actions}
                  barSize={26}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="completed"
                  name="Completed"
                  stackId="owner"
                  fill={t.muted}
                  barSize={26}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Activity"
            hint="Meetings analyzed and history events recorded, by month."
            wide
            bodyClass="chart-body--wide"
            empty={m.activity_timeline.length === 0 ? "No activity yet." : null}
            label={`Monthly activity: ${m.activity_timeline
              .map(
                (entry) =>
                  `${entry.month}: ${entry.meetings} meetings, ${entry.events} events`,
              )
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={m.activity_timeline}
                margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={t.grid}
                  vertical={false}
                />
                <XAxis
                  dataKey="month"
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                  width={32}
                />
                <Tooltip
                  contentStyle={tooltipContentStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  cursor={{ stroke: t.grid, strokeDasharray: "3 3" }}
                />
                <Legend formatter={renderLegend} />
                <Area
                  type="monotone"
                  dataKey="events"
                  name="History events"
                  stroke={t.categorical[1]}
                  fill={t.categorical[1]}
                  fillOpacity={0.14}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="meetings"
                  name="Meetings"
                  stroke={t.categorical[0]}
                  fill={t.categorical[0]}
                  fillOpacity={0.14}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </ChartPanel>
        </div>
      )}

      {rows !== null && (
        <div className="dashboard-projects">
          {rows.length > 0 ? (
            <div className="cards" aria-label="Projects">
              {rows.map((row) => (
                <section className="panel" key={row.project.id}>
                  <h2>
                    <Link to={`/projects/${row.project.id}`}>
                      {row.project.name}
                    </Link>
                  </h2>

                  <p>
                    <strong>{humanStatus(row.status)}</strong>
                  </p>

                  <p>{row.progress}</p>

                  <small>
                    {plural(row.open_risks, "open risk")}
                    {" · "}
                    {plural(row.open_blockers, "open blocker")}
                    {" · "}
                    {plural(row.open_actions, "open action")}
                    {" · "}
                    {plural(row.meeting_count, "meeting")}
                    {row.last_meeting ? (
                      <>
                        {" · last "}
                        {fmtDate(row.last_meeting)}
                      </>
                    ) : null}
                  </small>
                </section>
              ))}
            </div>
          ) : (
            <p>No projects yet.</p>
          )}
        </div>
      )}
    </>
  )
}
