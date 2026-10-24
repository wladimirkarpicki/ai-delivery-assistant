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
 * The cross-project dashboard: KPI tiles and a grid of recharts
 * panels fed by /api/metrics, with the original project cards from
 * /api/dashboard below. Both requests load in parallel; the page
 * renders each band as its data arrives.
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
  },
  status_distribution: [],
  open_items_mix: [],
  per_project: [],
  risk_impacts: [],
  activity_timeline: [],
  action_owners: [],
}

const KIND_LABELS: Record<"risks" | "blockers" | "actions", string> = {
  risks: "Risks",
  blockers: "Blockers",
  actions: "Actions",
}

function ellipsize(value: string, max = 18): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
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

  // Chart data, derived straight from the metrics payload.
  const statusData = m.status_distribution.map((entry) => ({
    name: entry.status,
    value: entry.count,
  }))
  const openTotal =
    m.totals.open_risks + m.totals.open_blockers + m.totals.open_actions
  const mixData = m.open_items_mix.map((entry) => ({
    kind: entry.kind,
    name: KIND_LABELS[entry.kind],
    value: entry.count,
  }))
  const meetingsData = m.per_project.map((project) => ({
    name: project.name,
    meetings: project.meetings,
  }))
  const impactTotal = m.risk_impacts.reduce(
    (sum, entry) => sum + entry.open + entry.resolved,
    0,
  )
  const openImpacts = m.risk_impacts
    .filter((entry) => entry.open > 0)
    .map((entry) => ({
      impact: entry.impact,
      name: `${entry.impact} (open)`,
      value: entry.open,
    }))
  const resolvedImpacts = m.risk_impacts
    .filter((entry) => entry.resolved > 0)
    .map((entry) => ({
      impact: entry.impact,
      name: `${entry.impact} (resolved)`,
      value: entry.resolved,
    }))
  const impactColorOf = (impact: string) => {
    const index = m.risk_impacts.findIndex((entry) => entry.impact === impact)
    return t.categorical[(index < 0 ? 0 : index) % t.categorical.length]
  }
  const ownersTotal = m.action_owners.reduce(
    (sum, entry) => sum + entry.open + entry.completed,
    0,
  )
  const perProjectHeight = Math.max(256, 44 * m.per_project.length + 24)
  const ownersHeight = Math.max(256, 44 * m.action_owners.length + 24)

  const kpis: Array<{ label: string; value: number }> = [
    { label: "Projects", value: m.totals.projects },
    { label: "Meetings", value: m.totals.meetings },
    { label: "Decisions", value: m.totals.decisions },
    { label: "Open risks", value: m.totals.open_risks },
    { label: "Open blockers", value: m.totals.open_blockers },
    { label: "Open actions", value: m.totals.open_actions },
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
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius="75%"
                  isAnimationActive={false}
                >
                  {statusData.map((entry, index) => (
                    <Cell
                      key={entry.name}
                      fill={t.categorical[index % t.categorical.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={tooltipContentStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                />
                <Legend formatter={renderLegend} />
              </PieChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Open items mix"
            hint="Risks, blockers, and actions currently open, across every project."
            empty={openTotal === 0 ? "No open risks, blockers, or actions." : null}
            label={`Open items by kind: ${mixData
              .map((entry) => `${entry.name} ${entry.value}`)
              .join(", ")}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={mixData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius="55%"
                  outerRadius="80%"
                  isAnimationActive={false}
                >
                  {mixData.map((entry) => (
                    <Cell key={entry.kind} fill={t.kind[entry.kind]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={tooltipContentStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                />
                <Legend formatter={renderLegend} />
              </PieChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Meetings per project"
            hint="How many meetings each project has stored."
            empty={
              m.per_project.length === 0
                ? "No projects yet."
                : m.totals.meetings === 0
                  ? "No meetings recorded yet."
                  : null
            }
            label={`Meetings per project: ${meetingsData
              .map((entry) => `${entry.name} ${entry.meetings}`)
              .join(", ")}`}
            height={perProjectHeight}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={meetingsData}
                layout="vertical"
                margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
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
                  axisLine={{ stroke: t.grid }}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={120}
                  tick={axisTick}
                  tickFormatter={(value: string) => ellipsize(value)}
                  axisLine={{ stroke: t.grid }}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={tooltipContentStyle}
                  labelStyle={tooltipLabelStyle}
                  itemStyle={tooltipItemStyle}
                  cursor={{ fill: t.grid }}
                />
                <Bar
                  dataKey="meetings"
                  name="Meetings"
                  fill={t.categorical[0]}
                  radius={[0, 4, 4, 0]}
                  barSize={16}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Open work per project"
            hint="Open risks, blockers, and actions stacked per project."
            empty={
              m.per_project.length === 0
                ? "No projects yet."
                : openTotal === 0
                  ? "No open risks, blockers, or actions."
                  : null
            }
            label={`Open work per project: ${m.per_project
              .map(
                (project) =>
                  `${project.name}: ${project.open_risks} risks, ${project.open_blockers} blockers, ${project.open_actions} actions`,
              )
              .join("; ")}`}
            height={perProjectHeight}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={m.per_project}
                margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={t.grid}
                  vertical={false}
                />
                <XAxis
                  dataKey="name"
                  tick={axisTick}
                  tickFormatter={(value: string) => ellipsize(value, 12)}
                  axisLine={{ stroke: t.grid }}
                  tickLine={false}
                  interval={0}
                />
                <YAxis
                  allowDecimals={false}
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                  width={36}
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
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="open_blockers"
                  name="Blockers"
                  stackId="open"
                  fill={t.kind.blockers}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="open_actions"
                  name="Actions"
                  stackId="open"
                  fill={t.kind.actions}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Risks by impact"
            hint="Inner ring: open risks. Outer ring: resolved risks, dimmed."
            empty={impactTotal === 0 ? "No risks recorded yet." : null}
            label={`Risks by impact: ${m.risk_impacts
              .map(
                (entry) =>
                  `${entry.impact}: ${entry.open} open, ${entry.resolved} resolved`,
              )
              .join("; ")}`}
            footer={
              <ul className="chart-legend">
                {m.risk_impacts.map((entry) => (
                  <li key={entry.impact}>
                    <span
                      className="swatch"
                      style={{ backgroundColor: impactColorOf(entry.impact) }}
                    />
                    {entry.impact}: {entry.open} open, {entry.resolved} resolved
                  </li>
                ))}
              </ul>
            }
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={openImpacts}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius="38%"
                  outerRadius="64%"
                  isAnimationActive={false}
                >
                  {openImpacts.map((entry) => (
                    <Cell key={entry.name} fill={impactColorOf(entry.impact)} />
                  ))}
                </Pie>
                <Pie
                  data={resolvedImpacts}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius="68%"
                  outerRadius="92%"
                  isAnimationActive={false}
                >
                  {resolvedImpacts.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={impactColorOf(entry.impact)}
                      fillOpacity={0.45}
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
          </ChartPanel>

          <ChartPanel
            title="Action items by owner"
            hint="Open and completed action items per owner; unowned items count as unassigned."
            empty={ownersTotal === 0 ? "No action items yet." : null}
            label={`Action items by owner: ${m.action_owners
              .map(
                (entry) =>
                  `${entry.owner}: ${entry.open} open, ${entry.completed} completed`,
              )
              .join("; ")}`}
            height={ownersHeight}
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
                  axisLine={{ stroke: t.grid }}
                  tickLine={false}
                  interval={0}
                />
                <YAxis
                  allowDecimals={false}
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                  width={36}
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
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="completed"
                  name="Completed"
                  stackId="owner"
                  fill={t.muted}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartPanel>

          <ChartPanel
            title="Activity timeline"
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
                  axisLine={{ stroke: t.grid }}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={axisTick}
                  axisLine={false}
                  tickLine={false}
                  width={36}
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
                  fillOpacity={0.16}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="meetings"
                  name="Meetings"
                  stroke={t.categorical[0]}
                  fill={t.categorical[0]}
                  fillOpacity={0.16}
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
