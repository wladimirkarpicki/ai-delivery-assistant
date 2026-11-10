"""
The analytics routes: the dashboard rows, the cross-project metrics, and
the Prometheus exposition endpoint.

These three were the largest handlers in api.py and moved together because
they share one discipline, which the docstrings each repeat and which is
worth stating once: every number is aggregated in a fixed number of
batched queries, never with a round trip per project. That is what took
the dashboard from 302 SELECTs to 8 at 50 projects, and the reason the
three are in one module rather than split further is that a change to the
aggregation discipline has to be made in all three at once.

The month aggregation is the part that took three attempts and is worth
reading in one place: reading every created_at into Python was O(rows),
bounding it to 24 months fixed the cost and silently dropped older
months, and GROUP BY is the form that costs what the data has months
rather than rows and drops nothing.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import extract, func, select
from sqlalchemy.orm import selectinload

from api_auth import get_current_user
from api_serializers import _dt
from database import db
from models import (
    ActionItem,
    Blocker,
    Decision,
    HistoryEvent,
    Meeting,
    Project,
    ProjectState,
    Risk,
)

router = APIRouter()


@router.get("/api/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    """
    One row per project for the overview table.

    Counts and the last-meeting timestamp are aggregated in a fixed
    number of grouped queries rather than per project: the docstring
    below /api/metrics claims the same discipline, and until now the
    dashboard did not honour it. Measured before the change, 50
    projects issued 302 SELECTs; /api/metrics issued 22 regardless of
    project count.
    """
    projects = (
        Project.query.order_by(Project.updated_at.desc())
        # project.state is a lazy relationship, so touching it inside
        # the loop issued one extra query per project. Eager-loading it
        # turns that into a single batched lookup.
        .options(selectinload(Project.state))
        .all()
    )

    # project_id -> aggregate, for each of the four counts. A missing
    # key means zero, which is what the per-row lookups default to.
    def _grouped(model, status=None):
        query = select(model.project_id, func.count(model.id))

        if status is not None:
            query = query.where(model.status == status)

        return dict(db.session.execute(query.group_by(model.project_id)).all())

    risk_open = _grouped(Risk, "open")
    blocker_open = _grouped(Blocker, "open")
    action_open = _grouped(ActionItem, "open")
    meeting_count = _grouped(Meeting)

    last_meeting = {
        row[0]: row[1]
        for row in db.session.execute(
            select(Meeting.project_id, func.max(Meeting.created_at)).group_by(
                Meeting.project_id
            )
        ).all()
    }

    rows = []

    for project in projects:
        state = project.state
        rows.append({
            "project": {"id": project.id, "name": project.name},
            "status": (state.delivery_status if state else "unknown").replace("_", " "),
            "progress": state.progress_summary if state else "No meeting analysis yet.",
            "open_risks": risk_open.get(project.id, 0),
            "open_blockers": blocker_open.get(project.id, 0),
            "open_actions": action_open.get(project.id, 0),
            "meeting_count": meeting_count.get(project.id, 0),
            "last_meeting": _dt(last_meeting.get(project.id)),
        })

    return {"rows": rows}

@router.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    """
    Prometheus exposition format, scraped by the monitoring stack.

    This route is the reason monitoring/prometheus.yml has something
    to scrape. Before it existed, /metrics was answered by the SPA
    catch-all with index.html, so Prometheus recorded zero samples
    and every dashboard and alert was decorative.

    Values are counted per scrape rather than kept in process
    counters: a single-user app has no request volume worth tracking
    in-process, and the ledger is the source of truth. The endpoint
    needs no bearer token because it exposes counts, not content,
    and the scrape config cannot authenticate.
    """
    counts = {
        "projects": db.session.query(func.count(Project.id)).scalar() or 0,
        "meetings": db.session.query(func.count(Meeting.id)).scalar() or 0,
        "history_events": db.session.query(func.count(HistoryEvent.id)).scalar() or 0,
        "open_risks": db.session.query(func.count(Risk.id)).filter(Risk.status == "open").scalar() or 0,
        "open_blockers": db.session.query(func.count(Blocker.id)).filter(Blocker.status == "open").scalar() or 0,
        "open_action_items": db.session.query(func.count(ActionItem.id)).filter(ActionItem.status == "open").scalar() or 0,
    }
    total = (
        counts["open_risks"] + counts["open_blockers"] + counts["open_action_items"]
    )

    lines = [
        "# HELP aida_projects Number of projects recorded.",
        "# TYPE aida_projects gauge",
        f"aida_projects {counts['projects']}",
        "# HELP aida_meetings Number of meetings recorded.",
        "# TYPE aida_meetings gauge",
        f"aida_meetings {counts['meetings']}",
        "# HELP aida_history_events Number of history events recorded.",
        "# TYPE aida_history_events gauge",
        f"aida_history_events {counts['history_events']}",
        "# HELP aida_open_risks Risks still open.",
        "# TYPE aida_open_risks gauge",
        f"aida_open_risks {counts['open_risks']}",
        "# HELP aida_open_blockers Blockers still open.",
        "# TYPE aida_open_blockers gauge",
        f"aida_open_blockers {counts['open_blockers']}",
        "# HELP aida_open_action_items Action items still open.",
        "# TYPE aida_open_action_items gauge",
        f"aida_open_action_items {counts['open_action_items']}",
        "# HELP aida_open_items_total Open risks, blockers and action items combined.",
        "# TYPE aida_open_items_total gauge",
        f"aida_open_items_total {total}",
    ]

    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

@router.get("/api/metrics")
def metrics(user: dict = Depends(get_current_user)):
    """
    Cross-project metrics for the dashboard charts, aggregated in a
    fixed number of batched queries - no per-project round trips,
    the same discipline as the dashboard rows.

    Month bucketing happens in Python rather than SQL date
    functions: the test suite runs on SQLite and production on
    PostgreSQL, and created_at comes back as a plain datetime from
    both, so grouping needs no dialect-specific SQL.

    resolution_rate is the share of risks, blockers, and actions
    ever recorded that are no longer open (resolved/completed). An
    empty ledger reads as 1.0: with nothing pending, nothing is
    outstanding. meetings_last_30d counts meetings created in the
    trailing 30 days.
    """
    cutoff_30d = datetime.now(UTC) - timedelta(days=30)

    totals = {
        "projects": Project.query.count(),
        "meetings": Meeting.query.count(),
        "decisions": Decision.query.count(),
        "history_events": HistoryEvent.query.count(),
        "open_risks": Risk.query.filter_by(status="open").count(),
        "open_blockers": Blocker.query.filter_by(status="open").count(),
        "open_actions": ActionItem.query.filter_by(status="open").count(),
        "resolved_risks": Risk.query.filter_by(status="resolved").count(),
        "resolved_blockers": Blocker.query.filter_by(status="resolved").count(),
        "resolved_actions": ActionItem.query.filter_by(status="completed").count(),
        "meetings_last_30d": Meeting.query.filter(
            Meeting.created_at >= cutoff_30d
        ).count(),
    }

    # Resolution rate over every risk, blocker, and action ever
    # recorded: resolved / (resolved + open). Zero work means
    # nothing is outstanding, which reads as a full 1.0.
    resolved_total = (
        totals["resolved_risks"]
        + totals["resolved_blockers"]
        + totals["resolved_actions"]
    )
    outstanding_total = (
        totals["open_risks"] + totals["open_blockers"] + totals["open_actions"]
    )
    resolution_rate = (
        resolved_total / (resolved_total + outstanding_total)
        if (resolved_total + outstanding_total) > 0
        else 1.0
    )

    # Delivery status over every project; projects without a state
    # count as "unknown". Human-readable keys, the same
    # replace("_", " ") the dashboard rows use.
    status_counts: dict[str, int] = {}

    for status, count in db.session.execute(
        select(
            ProjectState.delivery_status, func.count(Project.id)
        )
        .outerjoin(ProjectState, ProjectState.project_id == Project.id)
        .group_by(ProjectState.delivery_status)
    ).all():
        key = (status or "unknown").replace("_", " ")
        status_counts[key] = status_counts.get(key, 0) + int(count)

    status_distribution = [
        {"status": status, "count": count}
        for status, count in sorted(
            status_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    def counts_by_project(model, status=None):
        query = select(model.project_id, func.count(model.id))

        if status is not None:
            query = query.where(model.status == status)

        return {
            project_id: int(count)
            for project_id, count in db.session.execute(
                query.group_by(model.project_id)
            ).all()
        }

    meeting_counts = counts_by_project(Meeting)
    open_risk_counts = counts_by_project(Risk, "open")
    open_blocker_counts = counts_by_project(Blocker, "open")
    open_action_counts = counts_by_project(ActionItem, "open")

    per_project = [
        {
            "project_id": project.id,
            "name": project.name,
            "meetings": meeting_counts.get(project.id, 0),
            "open_risks": open_risk_counts.get(project.id, 0),
            "open_blockers": open_blocker_counts.get(project.id, 0),
            "open_actions": open_action_counts.get(project.id, 0),
        }
        for project in Project.query.order_by(Project.updated_at.desc()).all()
    ]

    # Risk impact breakdown: every impact present in the data
    # (including "unknown"), each with its open and resolved
    # counts. Statuses outside open/resolved are not counted.
    impact_counts: dict[str, dict[str, int]] = {}

    for impact, status, count in db.session.execute(
        select(Risk.impact, Risk.status, func.count(Risk.id)).group_by(
            Risk.impact, Risk.status
        )
    ).all():
        bucket = impact_counts.setdefault(
            impact or "unknown", {"open": 0, "resolved": 0}
        )

        if status in bucket:
            bucket[status] += int(count)

    impact_order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}

    risk_impacts = [
        {"impact": impact, "open": counts["open"], "resolved": counts["resolved"]}
        for impact, counts in sorted(
            impact_counts.items(),
            key=lambda item: (impact_order.get(item[0], 4), item[0]),
        )
    ]

    # The timeline is aggregated by the database, not in Python.
    #
    # The previous version read every created_at into Python and
    # counted there, which is O(rows) per request on a table where
    # HistoryEvent grows with every event of every item of every
    # meeting. A first attempt fixed that by bounding the window to 24
    # months, but that hid data: a month older than the window was
    # absent from the timeline, and the gap looked identical to a
    # month with nothing in it.
    #
    # GROUP BY is the fix that does not choose a cutoff. It returns one
    # row per distinct month, so the work is proportional to how long
    # history has been kept rather than to how many rows it holds, and
    # every month that exists is in the result.
    #
    # extract() rather than strftime or date_trunc: those are SQLite
    # and PostgreSQL only, and the tests run on SQLite while
    # production runs PostgreSQL. SQLAlchemy compiles extract for both.
    def month_counts(model):
        rows = db.session.execute(
            select(
                extract("year", model.created_at),
                extract("month", model.created_at),
                func.count(),
            )
            .where(model.created_at.isnot(None))
            .group_by(
                extract("year", model.created_at),
                extract("month", model.created_at),
            )
        ).all()

        return {
            (int(year), int(month)): count
            for year, month, count in rows
        }

    meeting_months = month_counts(Meeting)
    event_months = month_counts(HistoryEvent)

    activity_timeline = [
        {
            "month": f"{year:04d}-{month:02d}",
            "meetings": meeting_months.get((year, month), 0),
            "events": event_months.get((year, month), 0),
        }
        for year, month in sorted(set(meeting_months) | set(event_months))
    ]

    # Action items by owner; a missing owner reads as "unassigned".
    owner_counts: dict[str, dict[str, int]] = {}

    for owner, status, count in db.session.execute(
        select(
            ActionItem.owner, ActionItem.status, func.count(ActionItem.id)
        ).group_by(ActionItem.owner, ActionItem.status)
    ).all():
        bucket = owner_counts.setdefault(
            owner or "unassigned", {"open": 0, "completed": 0}
        )

        if status in bucket:
            bucket[status] += int(count)

    action_owners = [
        {"owner": owner, "open": counts["open"], "completed": counts["completed"]}
        for owner, counts in sorted(
            owner_counts.items(),
            key=lambda item: (-item[1]["open"], item[0]),
        )
    ]

    return {
        "totals": totals,
        "resolution_rate": resolution_rate,
        "status_distribution": status_distribution,
        "per_project": per_project,
        "risk_impacts": risk_impacts,
        "activity_timeline": activity_timeline,
        "action_owners": action_owners,
    }

