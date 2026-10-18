"""
FastAPI application: the JSON API behind the React frontend.

Every route from the Flask layer is ported with the same semantics:
the same consolidation pipeline, the same guardrails, the same
idempotency rules. HTML rendering moved to the React frontend; flash
messages became structured JSON responses:

- validation failures -> 400 {"error": "..."}
- missing records     -> 404
- manual resolve warnings (idempotent no-ops) -> 200 {"level": "warning", ...}
- consolidation fallback -> 201 with a "warning" field

The factory mirrors the Flask one: create_app(router_instance=None,
database_url=None), so the test suite drives a FakeRouter against an
in-memory database exactly as before.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from analyzer import analyze_document, parse_analysis
from config import DEFAULT_MODEL, DEFAULT_PROVIDER, EMBEDDING_MODEL
from database import (
    close_request_scope,
    configure_database,
    db,
    new_request_scope,
)
from document_parser import extract_text
from matching import (
    combine_plans,
    downgrade_create_duplicates,
    has_llm_findings,
    normalize_title,
    pre_match,
)
from memory_consolidator import MemoryConsolidator
from models import (
    ActionItem,
    Blocker,
    Decision,
    HistoryEvent,
    Meeting,
    Project,
    ReviewResolution,
    Risk,
)
from project_memory import (
    apply_consolidation_plan,
    apply_meeting_analysis,
    apply_review_create,
    apply_review_merge,
    apply_state,
    review_model_class,
)
from report import build_status_report
from router import ModelRouter


# ---------------------------------------------------------------------------
# Request bodies


class ProjectCreate(BaseModel):
    name: str = ""
    description: str = ""


class ManualResolve(BaseModel):
    action: str = "resolve"
    note: str = ""


class ReviewResolve(BaseModel):
    action: str = ""
    target_item_id: Optional[int] = None
    note: str = ""


# ---------------------------------------------------------------------------
# Memory extraction (framework-independent, ported verbatim from app.py)


def get_available_models(router):
    # Dynamic discovery from the provider API. Used as a health check:
    # the add-meeting form fails fast if the default model is missing.
    return router.get_models(DEFAULT_PROVIDER)


def get_project_memory(project_id):
    """
    Extract the current project memory from the database.

    All statuses are included, not only open ones: a resolved risk
    re-mentioned in a later meeting is the same canonical entity and
    must be reopened rather than duplicated.
    """
    memory = {
        "risks": [],
        "blockers": [],
        "action_items": [],
        "decisions": []
    }

    for risk in Risk.query.filter_by(project_id=project_id).all():
        memory["risks"].append({
            "id": risk.id,
            "title": risk.title,
            "canonical_title": risk.canonical_title,
            "embedding": risk.title_embedding,
            "description": risk.description,
            "impact": risk.impact,
            "mitigation": risk.mitigation,
            "status": risk.status
        })

    for blocker in Blocker.query.filter_by(project_id=project_id).all():
        memory["blockers"].append({
            "id": blocker.id,
            "title": blocker.title,
            "canonical_title": blocker.canonical_title,
            "embedding": blocker.title_embedding,
            "description": blocker.description,
            "status": blocker.status
        })

    for action in ActionItem.query.filter_by(project_id=project_id).all():
        memory["action_items"].append({
            "id": action.id,
            "title": action.title,
            "canonical_title": action.canonical_title,
            "embedding": action.title_embedding,
            "details": action.details,
            "owner": action.owner,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "status": action.status
        })

    for decision in Decision.query.filter_by(project_id=project_id).all():
        memory["decisions"].append({
            "id": decision.id,
            "title": decision.title,
            "canonical_title": decision.canonical_title,
            "embedding": decision.title_embedding,
            "details": decision.details
        })

    return memory


_MEMORY_MODEL_CLASSES = {
    "risks": Risk,
    "blockers": Blocker,
    "action_items": ActionItem,
    "decisions": Decision,
}


def ensure_item_embeddings(router, memory):
    """
    Embed items whose title_embedding is missing and persist the
    vectors. Titles are stable, so each item is embedded once and
    later meetings reuse the stored vector.

    Embeddings are an enrichment layer: on any provider failure the
    memory is returned unchanged and candidate matching falls back to
    lexical similarity.
    """
    pending = []

    for section in _MEMORY_MODEL_CLASSES:
        for item in memory.get(section) or []:
            canonical = item.get("canonical_title") or ""

            if not item.get("embedding") and canonical.strip():
                pending.append((section, item, canonical))

    if not pending:
        return memory

    try:
        vectors = router.embed_texts(
            DEFAULT_PROVIDER,
            EMBEDDING_MODEL,
            [canonical for _, _, canonical in pending],
        )
    except Exception:
        # Silent degradation: lexical candidate ranking still works.
        return memory

    for (section, item, _), vector in zip(pending, vectors):
        item["embedding"] = vector

        row = db.session.get(_MEMORY_MODEL_CLASSES[section], item["id"])

        if row is not None:
            row.title_embedding = vector

    db.session.commit()

    return memory


def embed_finding_titles(router, analysis):
    """
    Embed the finding titles of a new analysis and return a mapping
    of canonical title -> vector for pre_match. Never raises: without
    embeddings the pre-match falls back to lexical candidates.
    """
    titles = []
    seen = set()

    for section in ("risks", "blockers", "action_items", "decisions"):
        for finding in analysis.get(section) or []:
            if not isinstance(finding, dict):
                continue

            title = normalize_title(finding.get("title"))

            if title and title not in seen:
                seen.add(title)
                titles.append(title)

    if not titles:
        return {}

    try:
        vectors = router.embed_texts(DEFAULT_PROVIDER, EMBEDDING_MODEL, titles)
    except Exception:
        return {}

    return dict(zip(titles, vectors))


def history_changes(event):
    """
    Extract scalar field changes (field, old, new) from an event's
    before/after snapshots. Nested structures (plan items, new
    items) are skipped: their content is already reflected in the
    event summary. Ported verbatim from the Flask template filter.
    """
    before = event.before_data if isinstance(event.before_data, dict) else {}
    after = event.after_data if isinstance(event.after_data, dict) else {}
    changes = []

    for key, new_value in after.items():
        if key not in before or before[key] == new_value:
            continue

        if isinstance(new_value, (dict, list)) or isinstance(before[key], (dict, list)):
            continue

        changes.append((key, before[key], new_value))

    return changes


# ---------------------------------------------------------------------------
# Serializers (plain dicts: the frontend owns its own types)


def _dt(value):
    return value.isoformat() if value else None


def serialize_risk(risk):
    return {
        "id": risk.id,
        "title": risk.title,
        "description": risk.description,
        "impact": risk.impact,
        "mitigation": risk.mitigation,
        "status": risk.status,
        "resolved_at": _dt(risk.resolved_at),
    }


def serialize_blocker(blocker):
    return {
        "id": blocker.id,
        "title": blocker.title,
        "description": blocker.description,
        "status": blocker.status,
        "resolved_at": _dt(blocker.resolved_at),
    }


def serialize_action(action):
    return {
        "id": action.id,
        "title": action.title,
        "details": action.details,
        "owner": action.owner,
        "due_date": action.due_date.isoformat() if action.due_date else None,
        "status": action.status,
        "completed_at": _dt(action.completed_at),
    }


def serialize_decision(decision):
    return {
        "id": decision.id,
        "title": decision.title,
        "details": decision.details,
    }


def serialize_meeting(meeting, detail=False):
    data = {
        "id": meeting.id,
        "project_id": meeting.project_id,
        "title": meeting.title,
        "source_filename": meeting.source_filename,
        "provider": meeting.provider,
        "model": meeting.model,
        "created_at": _dt(meeting.created_at),
    }

    if detail:
        data["original_text"] = meeting.original_text
        data["analysis_text"] = meeting.analysis_text
        data["analysis_json"] = meeting.analysis_json
        data["project_name"] = meeting.project.name

    return data


def serialize_event(event):
    return {
        "id": event.id,
        "project_id": event.project_id,
        "meeting_id": event.meeting_id,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "summary": event.summary,
        "before_data": event.before_data,
        "after_data": event.after_data,
        "created_at": _dt(event.created_at),
        "changes": [
            {"field": field, "old": old, "new": new}
            for field, old, new in history_changes(event)
        ],
    }


def serialize_project_summary(project):
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "updated_at": _dt(project.updated_at),
    }


def serialize_state(state):
    if state is None:
        return {
            "delivery_status": "unknown",
            "progress_summary": "No meeting analysis yet.",
            "completed_items": [],
            "in_progress_items": [],
        }

    return {
        "delivery_status": state.delivery_status,
        "progress_summary": state.progress_summary or "No meeting analysis yet.",
        "completed_items": state.completed_items or [],
        "in_progress_items": state.in_progress_items or [],
    }


def error_response(message, status_code=400):
    return JSONResponse(status_code=status_code, content={"error": message})


class _SyncUpload:
    """
    Flask FileStorage-compatible view over a Starlette UploadFile:
    document_parser.extract_text reads .filename and calls .read()
    synchronously.
    """

    def __init__(self, filename, content: bytes):
        self.filename = filename
        self._content = content

    def read(self) -> bytes:
        return self._content


# ---------------------------------------------------------------------------
# Application factory


def create_app(router_instance=None, database_url=None):
    configure_database(database_url)
    router = router_instance or ModelRouter()

    app = FastAPI(
        title="AI Delivery Assistant",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # The Vite dev server proxies /api in development; production is
    # same-origin. localhost origins are allowed for convenience.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_session_scope(request: Request, call_next):
        # One scoped session per request, independent of the
        # threadpool thread that runs the endpoint.
        token = new_request_scope()

        try:
            response = await call_next(request)
        finally:
            close_request_scope(token)

        return response

    def _get_project(project_id):
        project = db.session.get(Project, project_id)

        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        return project

    @app.get("/api/health")
    def health():
        """
        The add-meeting gate: the app always analyzes with the fixed
        OpenRouter route, the model list is only a health check so the
        form can fail fast.
        """
        try:
            models = get_available_models(router)
        except (ValueError, RuntimeError) as exception:
            return {"analysis_ready": False, "model": None, "error": str(exception)}

        selected_model = DEFAULT_MODEL if DEFAULT_MODEL in models else None

        if selected_model is None:
            return {
                "analysis_ready": False,
                "model": None,
                "error": "The default model is currently unavailable.",
            }

        return {"analysis_ready": True, "model": selected_model, "error": None}

    @app.get("/api/dashboard")
    def dashboard():
        rows = []

        for project in Project.query.order_by(Project.updated_at.desc()).all():
            state = project.state
            rows.append({
                "project": {"id": project.id, "name": project.name},
                "status": (state.delivery_status if state else "unknown").replace("_", " "),
                "progress": state.progress_summary if state else "No meeting analysis yet.",
                "open_risks": Risk.query.filter_by(project_id=project.id, status="open").count(),
                "open_blockers": Blocker.query.filter_by(project_id=project.id, status="open").count(),
                "open_actions": ActionItem.query.filter_by(project_id=project.id, status="open").count(),
                "meeting_count": Meeting.query.filter_by(project_id=project.id).count(),
                "last_meeting": _dt(
                    db.session.query(db.func.max(Meeting.created_at))
                    .filter_by(project_id=project.id)
                    .scalar()
                ),
            })

        return {"rows": rows}

    @app.get("/api/projects")
    def projects_list():
        return {
            "projects": [
                serialize_project_summary(project)
                for project in Project.query.order_by(Project.updated_at.desc()).all()
            ]
        }

    @app.post("/api/projects", status_code=201)
    def projects_create(body: ProjectCreate):
        name = (body.name or "").strip()
        description = (body.description or "").strip()

        if not name:
            return error_response("Project name is required.")

        if Project.query.filter_by(name=name).first():
            return error_response("A project with this name already exists.")

        project = Project(name=name, description=description)
        db.session.add(project)
        db.session.commit()

        return {"id": project.id, "name": project.name}

    @app.get("/api/projects/{project_id}")
    def project_overview(project_id: int):
        project = _get_project(project_id)

        needs_review_count = (
            HistoryEvent.query.filter_by(project_id=project.id, event_type="needs_review")
            .filter(~HistoryEvent.review_resolution.has())
            .count()
        )

        return {
            "project": serialize_project_summary(project),
            "state": serialize_state(project.state),
            "risks": [
                serialize_risk(r)
                for r in Risk.query.filter_by(project_id=project.id, status="open").order_by(Risk.id.desc()).all()
            ],
            "resolved_risks": [
                serialize_risk(r)
                for r in Risk.query.filter_by(project_id=project.id, status="resolved").order_by(Risk.id.desc()).all()
            ],
            "blockers": [
                serialize_blocker(b)
                for b in Blocker.query.filter_by(project_id=project.id, status="open").order_by(Blocker.id.desc()).all()
            ],
            "resolved_blockers": [
                serialize_blocker(b)
                for b in Blocker.query.filter_by(project_id=project.id, status="resolved").order_by(Blocker.id.desc()).all()
            ],
            "actions": [
                serialize_action(a)
                for a in ActionItem.query.filter_by(project_id=project.id, status="open").order_by(ActionItem.id.desc()).all()
            ],
            "completed_actions": [
                serialize_action(a)
                for a in ActionItem.query.filter_by(project_id=project.id, status="completed").order_by(ActionItem.id.desc()).all()
            ],
            "meeting_count": Meeting.query.filter_by(project_id=project.id).count(),
            "needs_review_count": needs_review_count,
        }

    @app.get("/api/projects/{project_id}/meetings")
    def project_meetings(project_id: int):
        project = _get_project(project_id)

        return {
            "project": serialize_project_summary(project),
            "meetings": [serialize_meeting(m) for m in project.meetings],
        }

    @app.post("/api/projects/{project_id}/meetings", status_code=201)
    async def add_meeting(
        project_id: int,
        title: str = Form(""),
        meeting_notes: str = Form(""),
        meeting_file: Optional[UploadFile] = File(None),
    ):
        project = _get_project(project_id)

        try:
            models = get_available_models(router)
        except (ValueError, RuntimeError) as exception:
            return error_response(str(exception))

        selected_model = DEFAULT_MODEL if DEFAULT_MODEL in models else None

        if selected_model is None:
            return error_response("The default model is currently unavailable.")

        warning = None

        try:
            if meeting_file is not None and meeting_file.filename:
                # document_parser.extract_text speaks the Flask
                # FileStorage protocol (sync .read(), .filename); wrap
                # the already-loaded upload bytes in that shape.
                upload_bytes = await meeting_file.read()
                original_text = extract_text(_SyncUpload(meeting_file.filename, upload_bytes))
                source_filename = meeting_file.filename
            elif meeting_notes.strip():
                original_text, source_filename = meeting_notes.strip(), None
            else:
                raise ValueError("Upload meeting notes or paste meeting text.")

            # Idempotency: re-submitting identical notes is a
            # no-op rather than a second memory mutation.
            duplicate_meeting = Meeting.query.filter_by(
                project_id=project.id,
                original_text=original_text,
            ).first()

            if duplicate_meeting is not None:
                raise ValueError(
                    f"Identical meeting notes already exist "
                    f"({duplicate_meeting.title}, "
                    f"{duplicate_meeting.created_at:%Y-%m-%d}). "
                    f"No changes were applied."
                )

            analysis_text = analyze_document(original_text, DEFAULT_PROVIDER, selected_model, router)
            analysis_json = parse_analysis(analysis_text)
            meeting = Meeting(
                project_id=project.id,
                title=(title or "").strip() or "Untitled meeting",
                source_filename=source_filename,
                original_text=original_text,
                analysis_text=analysis_text,
                analysis_json=analysis_json,
                provider=DEFAULT_PROVIDER,
                model=selected_model,
            )
            db.session.add(meeting)
            db.session.flush()

            # Deterministic pre-matching resolves exact title
            # duplicates without the LLM; the remaining findings go
            # to the LLM with a candidate shortlist, and the LLM
            # plan passes a duplicate check before being applied.
            try:
                existing_memory = get_project_memory(project.id)
                ensure_item_embeddings(router, existing_memory)
                finding_embeddings = embed_finding_titles(
                    router, analysis_json
                )
                pre_matched = pre_match(
                    existing_memory, analysis_json, finding_embeddings
                )
                llm_findings = pre_matched["llm_findings"]

                if has_llm_findings(llm_findings):
                    consolidator = MemoryConsolidator(router)
                    consolidation_plan = consolidator.consolidate(
                        existing_memory=existing_memory,
                        new_analysis=llm_findings,
                        provider=DEFAULT_PROVIDER,
                        model=selected_model
                    )
                else:
                    consolidation_plan = {
                        "risks": [],
                        "blockers": [],
                        "action_items": [],
                        "decisions": [],
                    }

                downgrade_create_duplicates(existing_memory, consolidation_plan)

                apply_consolidation_plan(
                    project,
                    meeting,
                    combine_plans(pre_matched["auto"], consolidation_plan),
                )
            except Exception as consolidation_error:
                # Fallback to traditional analysis if consolidation fails
                warning = (
                    "Note: Consolidation encountered an issue "
                    f"({str(consolidation_error)}), using standard analysis."
                )
                apply_meeting_analysis(project, meeting, analysis_json)
            else:
                # The consolidation path only reconciles individual
                # memory items: apply the meeting status and progress
                # explicitly (previously they were silently dropped).
                apply_state(project, meeting, analysis_json)

            db.session.commit()

            response = {"meeting_id": meeting.id}

            if warning:
                response["warning"] = warning

            return response
        except (ValueError, RuntimeError) as exception:
            db.session.rollback()
            return error_response(str(exception))

    @app.get("/api/meetings/{meeting_id}")
    def meeting_detail(meeting_id: int):
        meeting = db.session.get(Meeting, meeting_id)

        if meeting is None:
            raise HTTPException(status_code=404, detail="Meeting not found")

        events = (
            HistoryEvent.query.filter_by(meeting_id=meeting.id)
            .order_by(HistoryEvent.id)
            .all()
        )

        return {
            "meeting": serialize_meeting(meeting, detail=True),
            "events": [serialize_event(event) for event in events],
        }

    @app.get("/api/projects/{project_id}/history")
    def project_history(project_id: int, type: str = ""):
        project = _get_project(project_id)
        selected_type = (type or "").strip()

        type_counts = dict(
            db.session.query(HistoryEvent.event_type, db.func.count(HistoryEvent.id))
            .filter_by(project_id=project.id)
            .group_by(HistoryEvent.event_type)
            .all()
        )

        query = HistoryEvent.query.filter_by(project_id=project.id)

        if selected_type:
            query = query.filter_by(event_type=selected_type)

        events = query.order_by(HistoryEvent.created_at.desc(), HistoryEvent.id.desc()).all()

        return {
            "project": serialize_project_summary(project),
            "events": [serialize_event(event) for event in events],
            "type_counts": type_counts,
            "selected_type": selected_type,
        }

    @app.get("/api/projects/{project_id}/report")
    def status_report(project_id: int, download: int = 0):
        project = _get_project(project_id)
        report = build_status_report(project)

        if download:
            return Response(
                content=report,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": "attachment; filename="
                    f"status-report-{project.id}.md"
                },
            )

        return {"project": serialize_project_summary(project), "report": report}

    def open_review_events(project):
        return (
            HistoryEvent.query.filter_by(
                project_id=project.id,
                event_type="needs_review",
            )
            .filter(~HistoryEvent.review_resolution.has())
            .order_by(HistoryEvent.id.desc())
            .all()
        )

    @app.get("/api/projects/{project_id}/review")
    def review_queue(project_id: int):
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

    @app.post("/api/projects/{project_id}/review/{event_id}/resolve")
    def resolve_review_event(project_id: int, event_id: int, body: ReviewResolve):
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
                    raise ValueError("Unknown entity type.")

                raw_target = body.target_item_id

                target = None
                if raw_target is not None:
                    target = db.session.get(model_class, int(raw_target))

                if target is None or target.project_id != project.id:
                    raise ValueError(
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
                raise ValueError("Unknown review action.")
        except ValueError as exception:
            db.session.rollback()
            return error_response(str(exception))

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

    @app.post("/api/projects/{project_id}/items/{item_type}/{item_id}/resolve")
    def manual_item_resolve(project_id: int, item_type: str, item_id: int, body: ManualResolve):
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

        if item is None or item.project_id != project.id:
            raise HTTPException(status_code=404, detail="Item not found")

        latest_meeting_id = db.session.scalar(
            db.select(Meeting.id)
            .filter_by(project_id=project.id)
            .order_by(Meeting.created_at.desc())
            .limit(1)
        )

        if action == "resolve":
            if item.status == target_status:
                return {
                    "status": item.status,
                    "level": "warning",
                    "message": f"{item.title} is already {target_status}.",
                }

            item.status = target_status
            setattr(item, time_col, datetime.now(timezone.utc))
            setattr(item, meeting_col, None)
            db.session.commit()
            db.session.add(HistoryEvent(
                project_id=project.id,
                meeting_id=latest_meeting_id,
                entity_type=entity_type,
                entity_id=item.id,
                event_type="manual_resolve",
                summary=f"Manually resolved {entity_type}: {item.title}",
                after_data={"status": target_status, "note": note},
                created_at=datetime.now(timezone.utc),
            ))
            db.session.commit()

            return {
                "status": item.status,
                "level": "success",
                "message": f"{entity_type.title()} resolved: {item.title}",
            }

        if action == "reopen":
            if item.status == "open":
                return {
                    "status": item.status,
                    "level": "warning",
                    "message": f"{item.title} is already open.",
                }

            item.status = "open"
            setattr(item, time_col, None)
            setattr(item, meeting_col, None)
            db.session.commit()
            db.session.add(HistoryEvent(
                project_id=project.id,
                meeting_id=latest_meeting_id,
                entity_type=entity_type,
                entity_id=item.id,
                event_type="manual_reopen",
                summary=f"Manually reopened {entity_type}: {item.title}",
                after_data={"status": "open", "note": note},
                created_at=datetime.now(timezone.utc),
            ))
            db.session.commit()

            return {
                "status": item.status,
                "level": "success",
                "message": f"{entity_type.title()} reopened: {item.title}",
            }

        return error_response("Unknown action.")

    # The untouched static design assets (tokens.css, styles.css),
    # served exactly as Flask served them.
    app.mount(
        "/static",
        StaticFiles(directory=str(Path("static").resolve())),
        name="static",
    )

    # Serve the React production bundle. A file in frontend/dist wins
    # (hashed assets); any other path falls back to index.html so the
    # SPA router owns deep links like /projects/1/overview.
    dist_dir = Path("frontend/dist").resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        candidate = (dist_dir / full_path).resolve()

        if full_path and candidate.is_file() and dist_dir in candidate.parents:
            return FileResponse(candidate)

        index = dist_dir / "index.html"

        if index.is_file():
            return FileResponse(index)

        return JSONResponse(
            status_code=404,
            content={"error": "Frontend bundle is not built. Run: pnpm --dir frontend build"},
        )

    return app
