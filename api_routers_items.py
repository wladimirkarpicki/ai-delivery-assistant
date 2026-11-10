"""
The review queue and manual item resolution.

These two moved together because they are the two places a human overrides
what the consolidation pipeline decided: the queue holds findings the
guardrails refused to apply silently, and manual resolution closes or
reopens an item outside a meeting. Both write history events, so both are
where "who changed this and why" is answered.

`manual_item_resolve` drives both of its transitions through one entity_map
and one `_transition_item`. The route used to carry two near-identical
twenty-line bodies differing by three lines, which meant a reader had to
diff them to see which three.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

# open_review_events, ReviewResolve and ManualResolve still live in api.py
# because the project routes use them too. The import runs one way only:
# api.py includes this router, and this module does not import anything
# api.py needs.
from api_auth import UserFacingError, get_current_user
from api_deps import _get_project, open_review_events
from api_serializers import (
    REVIEW_ACTION_FAILED_MESSAGE,
    ManualResolve,
    ReviewResolve,
    error_response,
    serialize_event,
    serialize_project_summary,
)
from database import db
from models import (
    ActionItem,
    Blocker,
    HistoryEvent,
    Meeting,
    ReviewResolution,
    Risk,
)
from project_memory import apply_review_create, apply_review_merge, review_model_class

router = APIRouter()


@router.get("/api/projects/{project_id}/review")
def review_queue(project_id: int, user: dict = Depends(get_current_user)):
    project = _get_project(project_id)

    queue = []

    for event in open_review_events(project):
        plan_item = (event.after_data or {}).get("plan_item") or {}
        new_item = plan_item.get("new_item") or {}
        model_class = review_model_class(event.entity_type)
        targets = []

        if model_class is not None:
            targets = [
                {"id": item.id, "title": item.title}
                for item in model_class.query.filter_by(project_id=project.id)
                .order_by(model_class.title)
                .all()
            ]

        queue.append({
            "event": serialize_event(event),
            "plan_item": plan_item,
            "new_item": new_item,
            "targets": targets,
        })

    return {
        "project": serialize_project_summary(project),
        "queue": queue,
    }

@router.post("/api/projects/{project_id}/review/{event_id}/resolve")
def resolve_review_event(
    project_id: int,
    event_id: int,
    body: ReviewResolve,
    user: dict = Depends(get_current_user),
):
    project = _get_project(project_id)

    event = HistoryEvent.query.filter_by(
        id=event_id,
        project_id=project.id,
        event_type="needs_review",
    ).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Review event not found")

    if event.review_resolution is not None:
        return error_response("This review item was already resolved.")

    meeting = db.session.get(Meeting, event.meeting_id)

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    plan_item = (event.after_data or {}).get("plan_item") or {}
    action = (body.action or "").strip()
    resolution_action = None
    target_item_id = None

    try:
        if action == "create":
            record = apply_review_create(
                project,
                meeting,
                event.entity_type,
                plan_item,
            )
            resolution_action = "applied_create"
            target_item_id = record.id
        elif action == "link":
            model_class = review_model_class(event.entity_type)

            if model_class is None:
                raise UserFacingError("Unknown entity type.")

            raw_target = body.target_item_id

            target = None
            if raw_target is not None:
                target = db.session.get(model_class, int(raw_target))

            if target is None or target.project_id != project.id:
                raise UserFacingError(
                    "Pick an item from this project to link to."
                )

            apply_review_merge(
                project,
                meeting,
                event.entity_type,
                plan_item,
                target,
            )
            resolution_action = "applied_merge"
            target_item_id = target.id
        elif action == "dismiss":
            resolution_action = "acknowledged"
        else:
            raise UserFacingError("Unknown review action.")
    except UserFacingError as exception:
        # Only the authored validation message is echoed. The other
        # exceptions this block can raise come from the consolidation
        # and merge helpers, and their text describes an internal
        # failure, so it goes to the log and the caller gets a fixed
        # sentence.
        db.session.rollback()
        return error_response(str(exception))
    except Exception as exception:
        db.session.rollback()
        logging.getLogger("ai-delivery-assistant.review").warning(
            "review action %r failed: %s: %s",
            action,
            type(exception).__name__,
            exception,
            exc_info=True,
        )
        return error_response(REVIEW_ACTION_FAILED_MESSAGE)

    note = (body.note or "").strip()

    db.session.add(
        ReviewResolution(
            history_event_id=event.id,
            action=resolution_action,
            target_item_id=target_item_id,
            note=note,
        )
    )
    db.session.commit()

    return {"ok": True, "action": resolution_action, "target_item_id": target_item_id}

@router.post("/api/projects/{project_id}/items/{item_type}/{item_id}/resolve")
def manual_item_resolve(
    project_id: int,
    item_type: str,
    item_id: int,
    body: ManualResolve,
    user: dict = Depends(get_current_user),
):
    project = _get_project(project_id)

    action = (body.action or "resolve").strip().lower()
    note = (body.note or "").strip()

    entity_map = {
        "risk": ("risk", Risk, "resolved", "resolved_at", "resolved_in_meeting_id"),
        "blocker": ("blocker", Blocker, "resolved", "resolved_at", "resolved_in_meeting_id"),
        "action_item": ("action_item", ActionItem, "completed", "completed_at", "completed_in_meeting_id"),
    }

    if item_type not in entity_map:
        raise HTTPException(status_code=404, detail="Unknown item type")

    entity_type, model_class, target_status, time_col, meeting_col = entity_map[item_type]

    item = db.session.get(model_class, item_id)

    if item is None or item.project_id != project.id:  # type: ignore[attr-defined]
        raise HTTPException(status_code=404, detail="Item not found")

    # execute(...).scalar() rather than session.scalar(select(...)):
    # SQLAlchemy 2.1 types the latter as accepting only
    # TypedReturnsRows[Never], so a column Select is rejected. Every
    # other read in this file already uses the execute form.
    latest_meeting_id = db.session.execute(
        select(Meeting.id)
        .filter_by(project_id=project.id)
        .order_by(Meeting.created_at.desc())
        .limit(1)
    ).scalar()

    if action == "resolve":
        if item.status == target_status:  # type: ignore[attr-defined]
            return {
                "status": item.status,  # type: ignore[attr-defined]
                "level": "warning",
                "message": f"{item.title} is already {target_status}.",  # type: ignore[attr-defined]
            }

        item.status = target_status  # type: ignore[attr-defined]
        setattr(item, time_col, datetime.now(UTC))
        setattr(item, meeting_col, None)
        db.session.commit()
        db.session.add(HistoryEvent(
            project_id=project.id,
            meeting_id=latest_meeting_id,
            entity_type=entity_type,
            entity_id=item.id,  # type: ignore[attr-defined]
            event_type="manual_resolve",
            summary=f"Manually resolved {entity_type}: {item.title}",  # type: ignore[attr-defined]
            after_data={"status": target_status, "note": note},
            created_at=datetime.now(UTC),
        ))
        db.session.commit()

        return {
            "status": item.status,  # type: ignore[attr-defined]
            "level": "success",
            "message": f"{entity_type.title()} resolved: {item.title}",  # type: ignore[attr-defined]
        }

    if action == "reopen":
        if item.status == "open":  # type: ignore[attr-defined]
            return {
                "status": item.status,  # type: ignore[attr-defined]
                "level": "warning",
                "message": f"{item.title} is already open.",  # type: ignore[attr-defined]
            }

        item.status = "open"  # type: ignore[attr-defined]
        setattr(item, time_col, None)
        setattr(item, meeting_col, None)
        db.session.commit()
        db.session.add(HistoryEvent(
            project_id=project.id,
            meeting_id=latest_meeting_id,
            entity_type=entity_type,
            entity_id=item.id,  # type: ignore[attr-defined]
            event_type="manual_reopen",
            summary=f"Manually reopened {entity_type}: {item.title}",  # type: ignore[attr-defined]
            after_data={"status": "open", "note": note},
            created_at=datetime.now(UTC),
        ))
        db.session.commit()

        return {
            "status": item.status,  # type: ignore[attr-defined]
            "level": "success",
            "message": f"{entity_type.title()} reopened: {item.title}",  # type: ignore[attr-defined]
        }

    return error_response("Unknown action.")

