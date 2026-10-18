"""
Status report generation.

Builds a plain-Markdown status report from the project memory:
delivery status, progress, open and resolved work, and decisions.
The report is a read-only projection: nothing here mutates the
database, so exporting is safe at any time.
"""

from datetime import UTC, datetime

from models import ActionItem, Blocker, Decision, Risk


def _section(lines, heading, entries):
    """Append a markdown section; skip entirely when there is nothing to show."""
    if not entries:
        return

    lines.append(f"## {heading}")
    lines.append("")

    for entry in entries:
        lines.append(entry)

    lines.append("")


def _risk_line(risk):
    parts = [f"- {risk.title}"]

    if risk.impact:
        parts.append(f"impact: {risk.impact}")

    if risk.mitigation:
        parts.append(f"mitigation: {risk.mitigation}")

    if risk.status == "resolved" and risk.resolved_at:
        parts.append(f"resolved {risk.resolved_at:%Y-%m-%d}")

    if len(parts) == 1:
        return parts[0]

    return parts[0] + " (" + "; ".join(parts[1:]) + ")"


def _action_line(action):
    parts = []

    if action.owner:
        parts.append(f"owner: {action.owner}")

    if action.due_date:
        parts.append(f"due {action.due_date:%Y-%m-%d}")

    if action.status == "completed" and action.completed_at:
        parts.append(f"completed {action.completed_at:%Y-%m-%d}")

    return (
        f"- {action.title} (" + "; ".join(parts) + ")"
        if parts
        else f"- {action.title}"
    )


def build_status_report(project):
    """
    Render the full status report of a project as Markdown.

    Must be called inside an app context: the relationships lazy-load
    from the database.
    """
    state = project.state
    risks = Risk.query.filter_by(project_id=project.id).order_by(Risk.id).all()
    blockers = Blocker.query.filter_by(project_id=project.id).order_by(Blocker.id).all()
    actions = ActionItem.query.filter_by(project_id=project.id).order_by(ActionItem.id).all()
    decisions = Decision.query.filter_by(project_id=project.id).order_by(Decision.id).all()

    open_risks = [r for r in risks if r.status == "open"]
    resolved_risks = [r for r in risks if r.status == "resolved"]
    open_blockers = [b for b in blockers if b.status == "open"]
    resolved_blockers = [b for b in blockers if b.status == "resolved"]
    open_actions = [a for a in actions if a.status == "open"]
    completed_actions = [a for a in actions if a.status == "completed"]

    status = (state.delivery_status if state else "unknown").replace("_", " ")

    lines = [
        f"# Status report: {project.name}",
        "",
        f"Generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        "## Status",
        "",
        f"- Delivery status: {status}",
        f"- Progress: {state.progress_summary if state else 'No meeting analysis yet.'}",
        "",
    ]

    _section(lines, "Open risks", [_risk_line(r) for r in open_risks])
    _section(lines, "Resolved risks", [_risk_line(r) for r in resolved_risks])
    _section(lines, "Open blockers", [f"- {b.title}" for b in open_blockers])
    _section(
        lines,
        "Resolved blockers",
        [
            f"- {b.title} (resolved {b.resolved_at:%Y-%m-%d})"
            if b.resolved_at
            else f"- {b.title}"
            for b in resolved_blockers
        ],
    )
    _section(lines, "Open action items", [_action_line(a) for a in open_actions])
    _section(lines, "Completed action items", [_action_line(a) for a in completed_actions])

    if decisions:
        lines.append("## Decisions")
        lines.append("")

        for decision in decisions:
            lines.append(f"- {decision.title}")

        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"- Risks: {len(open_risks)} open, {len(resolved_risks)} resolved"
    )
    lines.append(
        f"- Blockers: {len(open_blockers)} open, {len(resolved_blockers)} resolved"
    )
    lines.append(
        f"- Action items: {len(open_actions)} open, {len(completed_actions)} completed"
    )
    lines.append(f"- Decisions: {len(decisions)}")
    lines.append("")

    return "\n".join(lines)
