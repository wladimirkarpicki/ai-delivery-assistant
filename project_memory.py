from datetime import date

from database import db
from models import ActionItem, Blocker, Decision, HistoryEvent, Meeting, ProjectState, Risk, utcnow


def _value(item, key, default=""):
    value = item.get(key, default) if isinstance(item, dict) else default
    return value.strip() if isinstance(value, str) else value


def _find_open(model, project_id, title):
    return model.query.filter_by(project_id=project_id, title=title, status="open").first()


def _event(project_id, meeting_id, entity_type, entity_id, event_type, summary, before=None, after=None):
    db.session.add(HistoryEvent(project_id=project_id, meeting_id=meeting_id, entity_type=entity_type, entity_id=entity_id, event_type=event_type, summary=summary, before_data=before, after_data=after))


def _apply_state(project, meeting, analysis):
    state = project.state or ProjectState(project=project)
    before = {"delivery_status": state.delivery_status, "progress_summary": state.progress_summary}
    state.delivery_status = _value(analysis, "project_status", "unknown") or "unknown"
    state.progress_summary = _value(analysis, "progress_summary")
    state.completed_items = analysis.get("completed_items", [])
    state.in_progress_items = analysis.get("in_progress_items", [])
    state.updated_in_meeting_id = meeting.id
    db.session.add(state)
    db.session.flush()
    _event(project.id, meeting.id, "project_state", state.id, "updated", "Updated current project status.", before, {"delivery_status": state.delivery_status, "progress_summary": state.progress_summary})


def _apply_risks(project, meeting, risks):
    for item in risks or []:
        title = _value(item, "title")
        if not title:
            continue
        risk = _find_open(Risk, project.id, title)
        is_resolved = _value(item, "status", "open") == "resolved"
        if risk is None:
            risk = Risk(project_id=project.id, title=title, description=_value(item, "description"), impact=_value(item, "impact", "unknown"), mitigation=_value(item, "mitigation"), status="resolved" if is_resolved else "open", created_in_meeting_id=meeting.id, updated_in_meeting_id=meeting.id)
            if is_resolved:
                risk.resolved_at, risk.resolved_in_meeting_id = utcnow(), meeting.id
            db.session.add(risk)
            db.session.flush()
            _event(project.id, meeting.id, "risk", risk.id, "created", f"Recorded risk: {title}", after={"status": risk.status})
        else:
            before = {"status": risk.status, "impact": risk.impact, "mitigation": risk.mitigation}
            risk.description, risk.impact, risk.mitigation, risk.updated_in_meeting_id = _value(item, "description"), _value(item, "impact", "unknown"), _value(item, "mitigation"), meeting.id
            if is_resolved:
                risk.status, risk.resolved_at, risk.resolved_in_meeting_id = "resolved", utcnow(), meeting.id
                action, summary = "resolved", f"Resolved risk: {title}"
            else:
                action, summary = "updated", f"Updated risk: {title}"
            _event(project.id, meeting.id, "risk", risk.id, action, summary, before, {"status": risk.status, "impact": risk.impact, "mitigation": risk.mitigation})


def _apply_blockers(project, meeting, blockers):
    for item in blockers or []:
        title = _value(item, "title")
        if not title:
            continue
        blocker = _find_open(Blocker, project.id, title)
        resolved = _value(item, "status", "open") == "resolved"
        if blocker is None:
            blocker = Blocker(project_id=project.id, title=title, description=_value(item, "description"), status="resolved" if resolved else "open", created_in_meeting_id=meeting.id, updated_in_meeting_id=meeting.id)
            if resolved:
                blocker.resolved_at, blocker.resolved_in_meeting_id = utcnow(), meeting.id
            db.session.add(blocker); db.session.flush()
            _event(project.id, meeting.id, "blocker", blocker.id, "created", f"Recorded blocker: {title}")
        else:
            before = {"status": blocker.status}
            blocker.description, blocker.updated_in_meeting_id = _value(item, "description"), meeting.id
            if resolved:
                blocker.status, blocker.resolved_at, blocker.resolved_in_meeting_id = "resolved", utcnow(), meeting.id
                action, summary = "resolved", f"Resolved blocker: {title}"
            else:
                action, summary = "updated", f"Updated blocker: {title}"
            _event(project.id, meeting.id, "blocker", blocker.id, action, summary, before, {"status": blocker.status})


def _apply_actions(project, meeting, actions):
    for item in actions or []:
        title = _value(item, "title")
        if not title:
            continue
        action_item = _find_open(ActionItem, project.id, title)
        completed = _value(item, "status", "open") == "completed"
        due_date = _value(item, "due_date", None)
        try:
            due_date = date.fromisoformat(due_date) if due_date else None
        except ValueError:
            due_date = None
        if action_item is None:
            action_item = ActionItem(project_id=project.id, title=title, details=_value(item, "details"), owner=_value(item, "owner", None), due_date=due_date, status="completed" if completed else "open", created_in_meeting_id=meeting.id, updated_in_meeting_id=meeting.id)
            if completed:
                action_item.completed_at, action_item.completed_in_meeting_id = utcnow(), meeting.id
            db.session.add(action_item); db.session.flush()
            _event(project.id, meeting.id, "action_item", action_item.id, "created", f"Recorded action: {title}")
        else:
            before = {"status": action_item.status, "owner": action_item.owner, "due_date": str(action_item.due_date) if action_item.due_date else None}
            action_item.details, action_item.owner, action_item.due_date, action_item.updated_in_meeting_id = _value(item, "details"), _value(item, "owner", None), due_date, meeting.id
            if completed:
                action_item.status, action_item.completed_at, action_item.completed_in_meeting_id = "completed", utcnow(), meeting.id
                action, summary = "completed", f"Completed action: {title}"
            else:
                action, summary = "updated", f"Updated action: {title}"
            _event(project.id, meeting.id, "action_item", action_item.id, action, summary, before, {"status": action_item.status, "owner": action_item.owner, "due_date": str(action_item.due_date) if action_item.due_date else None})


def apply_meeting_analysis(project, meeting, analysis):
    """Mutate current state while retaining an immutable meeting and event trail."""
    _apply_state(project, meeting, analysis)
    _apply_risks(project, meeting, analysis.get("risks"))
    _apply_blockers(project, meeting, analysis.get("blockers"))
    _apply_actions(project, meeting, analysis.get("action_items"))
    for item in analysis.get("decisions", []):
        title = _value(item, "title")
        if title:
            decision = Decision(project_id=project.id, title=title, details=_value(item, "details"), created_in_meeting_id=meeting.id)
            db.session.add(decision); db.session.flush()
            _event(project.id, meeting.id, "decision", decision.id, "created", f"Recorded decision: {title}")
