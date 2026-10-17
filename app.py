import os

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from flask_wtf import CSRFProtect

from analyzer import analyze_document, parse_analysis
from config import DEFAULT_MODEL, DEFAULT_PROVIDER, EMBEDDING_MODEL
from database import configure_database, db
from document_parser import extract_text
from matching import (
    combine_plans,
    downgrade_create_duplicates,
    has_llm_findings,
    normalize_title,
    pre_match,
)
from memory_consolidator import MemoryConsolidator
from models import ActionItem, Blocker, Decision, HistoryEvent, Meeting, Project, ReviewResolution, Risk
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


def create_app(router_instance=None, database_url=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "development-only-change-me")
    if database_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)
    else:
        configure_database(app)
    router = router_instance or ModelRouter()

    # Validate CSRF tokens on every POST form.
    CSRFProtect(app)

    @app.get("/")
    def index():
        return redirect(url_for("projects"))

    @app.route("/projects", methods=["GET", "POST"])
    def projects():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            if not name:
                flash("Project name is required.", "error")
            elif Project.query.filter_by(name=name).first():
                flash("A project with this name already exists.", "error")
            else:
                project = Project(name=name, description=description)
                db.session.add(project)
                db.session.commit()
                return redirect(url_for("project_overview", project_id=project.id))
        return render_template("projects.html", projects=Project.query.order_by(Project.updated_at.desc()).all())

    @app.post("/projects/<int:project_id>/items/<item_type>/<int:item_id>/resolve")
    def manual_item_resolve(project_id, item_type, item_id):
        from datetime import datetime, timezone
        project = db.session.get(Project, project_id) or abort(404)
        action = request.form.get("action", "resolve").strip().lower()
        note = request.form.get("note", "").strip()
        entity_map = {
            "risk": ("risk", Risk, "resolved", "resolved_at", "resolved_in_meeting_id"),
            "blocker": ("blocker", Blocker, "resolved", "resolved_at", "resolved_in_meeting_id"),
            "action_item": ("action_item", ActionItem, "completed", "completed_at", "completed_in_meeting_id"),
        }
        if item_type not in entity_map:
            abort(404)
        entity_type, model_class, target_status, time_col, meeting_col = entity_map[item_type]
        item = db.session.get(model_class, item_id)
        if item is None or item.project_id != project.id:
            abort(404)
        latest_meeting_id = db.session.scalar(
            db.select(Meeting.id)
            .filter_by(project_id=project.id)
            .order_by(Meeting.created_at.desc())
            .limit(1)
        )
        if action == "resolve":
            if item.status == target_status:
                flash(f"{item.title} is already {target_status}.", "warning")
            else:
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
                flash(f"{entity_type.title()} resolved: {item.title}", "success")
        elif action == "reopen":
            if item.status == "open":
                flash(f"{item.title} is already open.", "warning")
            else:
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
                flash(f"{entity_type.title()} reopened: {item.title}", "success")
        else:
            flash("Unknown action.", "error")
        return redirect(url_for("project_overview", project_id=project.id))

    @app.get("/projects/<int:project_id>")
    def project_overview(project_id):
        project = db.session.get(Project, project_id) or abort(404)
        needs_review_count = (
            HistoryEvent.query.filter_by(project_id=project.id, event_type="needs_review")
            .filter(~HistoryEvent.review_resolution.has())
            .count()
        )
        return render_template("project_overview.html",
            project=project,
            risks=Risk.query.filter_by(project_id=project.id, status="open").order_by(Risk.id.desc()).all(),
            resolved_risks=Risk.query.filter_by(project_id=project.id, status="resolved").order_by(Risk.id.desc()).all(),
            blockers=Blocker.query.filter_by(project_id=project.id, status="open").order_by(Blocker.id.desc()).all(),
            resolved_blockers=Blocker.query.filter_by(project_id=project.id, status="resolved").order_by(Blocker.id.desc()).all(),
            actions=ActionItem.query.filter_by(project_id=project.id, status="open").order_by(ActionItem.id.desc()).all(),
            completed_actions=ActionItem.query.filter_by(project_id=project.id, status="completed").order_by(ActionItem.id.desc()).all(),
            meeting_count=Meeting.query.filter_by(project_id=project.id).count(),
            needs_review_count=needs_review_count)

    @app.get("/projects/<int:project_id>/meetings")
    def project_meetings(project_id):
        project = db.session.get(Project, project_id) or abort(404)
        return render_template("meetings.html", project=project, meetings=project.meetings)

    @app.get("/meetings/<int:meeting_id>")
    def meeting_detail(meeting_id):
        meeting = db.session.get(Meeting, meeting_id) or abort(404)
        events = HistoryEvent.query.filter_by(meeting_id=meeting.id).order_by(HistoryEvent.id).all()
        return render_template("meeting_detail.html", meeting=meeting, events=events)

    @app.get("/projects/<int:project_id>/history")
    def project_history(project_id):
        project = db.session.get(Project, project_id) or abort(404)
        selected_type = request.args.get("type", "").strip()

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
        return render_template(
            "history.html",
            project=project,
            events=events,
            type_counts=type_counts,
            selected_type=selected_type,
        )

    @app.get("/projects/<int:project_id>/report")
    def status_report(project_id):
        project = db.session.get(Project, project_id) or abort(404)
        report = build_status_report(project)

        if request.args.get("download"):
            return Response(
                report,
                mimetype="text/markdown",
                headers={
                    "Content-Disposition": "attachment; filename="
                    f"status-report-{project.id}.md"
                },
            )

        return render_template("report.html", project=project, report=report)

    @app.get("/dashboard")
    def dashboard():
        rows = []
        for project in Project.query.order_by(Project.updated_at.desc()).all():
            state = project.state
            rows.append({
                "project": project,
                "status": (state.delivery_status if state else "unknown").replace("_", " "),
                "progress": state.progress_summary if state else "No meeting analysis yet.",
                "open_risks": Risk.query.filter_by(project_id=project.id, status="open").count(),
                "open_blockers": Blocker.query.filter_by(project_id=project.id, status="open").count(),
                "open_actions": ActionItem.query.filter_by(project_id=project.id, status="open").count(),
                "meeting_count": Meeting.query.filter_by(project_id=project.id).count(),
                "last_meeting": db.session.query(db.func.max(Meeting.created_at)).filter_by(project_id=project.id).scalar(),
            })
        return render_template("dashboard.html", rows=rows)

    @app.template_filter("history_changes")
    def history_changes_filter(event):
        """
        Extract scalar field changes (field, old, new) from an event's
        before/after snapshots. Nested structures (plan items, new
        items) are skipped: their content is already reflected in the
        event summary.
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

    @app.get("/projects/<int:project_id>/review")
    def review_queue(project_id):
        project = db.session.get(Project, project_id) or abort(404)

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
                "event": event,
                "plan_item": plan_item,
                "new_item": new_item,
                "targets": targets,
            })

        return render_template("review_queue.html", project=project, queue=queue)

    @app.post("/projects/<int:project_id>/review/<int:event_id>/resolve")
    def resolve_review_event(project_id, event_id):
        project = db.session.get(Project, project_id) or abort(404)

        event = HistoryEvent.query.filter_by(
            id=event_id,
            project_id=project.id,
            event_type="needs_review",
        ).first() or abort(404)

        if event.review_resolution is not None:
            flash("This review item was already resolved.", "error")
            return redirect(url_for("review_queue", project_id=project.id))

        meeting = db.session.get(Meeting, event.meeting_id) or abort(404)
        plan_item = (event.after_data or {}).get("plan_item") or {}
        action = request.form.get("action", "")
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

                raw_target = request.form.get("target_item_id", "")

                try:
                    target = db.session.get(model_class, int(raw_target))
                except (TypeError, ValueError):
                    target = None

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
            flash(str(exception), "error")
            return redirect(url_for("review_queue", project_id=project.id))

        note = request.form.get("note", "").strip()

        db.session.add(
            ReviewResolution(
                history_event_id=event.id,
                action=resolution_action,
                target_item_id=target_item_id,
                note=note,
            )
        )
        db.session.commit()
        flash("Review item resolved.", "success")
        return redirect(url_for("review_queue", project_id=project.id))

    @app.route("/projects/<int:project_id>/meetings/new", methods=["GET", "POST"])
    def add_meeting(project_id):
        project = db.session.get(Project, project_id) or abort(404)
        error = None
        try:
            models = get_available_models(router)
        except (ValueError, RuntimeError) as exception:
            models, error = [], str(exception)
        # The app always analyzes with the Free Models Router; the model
        # list is only a health check so the form can fail fast.
        selected_model = DEFAULT_MODEL if DEFAULT_MODEL in models else None
        if error is None and selected_model is None:
            error = "The default model is currently unavailable."
        if request.method == "POST" and not error:
            notes = request.form.get("meeting_notes", "")
            uploaded_file = request.files.get("meeting_file")
            try:
                if uploaded_file and uploaded_file.filename:
                    original_text, source_filename = extract_text(uploaded_file), uploaded_file.filename
                elif notes.strip():
                    original_text, source_filename = notes.strip(), None
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

                if not selected_model:
                    raise ValueError("No supported models are currently available.")
                analysis_text = analyze_document(original_text, DEFAULT_PROVIDER, selected_model, router)
                analysis_json = parse_analysis(analysis_text)
                meeting = Meeting(project_id=project.id, title=request.form.get("title", "").strip() or "Untitled meeting", source_filename=source_filename, original_text=original_text, analysis_text=analysis_text, analysis_json=analysis_json, provider=DEFAULT_PROVIDER, model=selected_model)
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
                    flash(f"Note: Consolidation encountered an issue ({str(consolidation_error)}), using standard analysis.", "warning")
                    apply_meeting_analysis(project, meeting, analysis_json)
                else:
                    # The consolidation path only reconciles individual
                    # memory items: apply the meeting status and progress
                    # explicitly (previously they were silently dropped).
                    apply_state(project, meeting, analysis_json)
                
                db.session.commit()
                flash("Meeting saved and project memory updated.", "success")
                return redirect(url_for("meeting_detail", meeting_id=meeting.id))
            except (ValueError, RuntimeError) as exception:
                db.session.rollback()
                error = str(exception)
        return render_template("add_meeting.html", project=project, analysis_ready=selected_model is not None, error=error)

    @app.context_processor
    def nav_projects():
        """Feed the command palette with the current project list."""
        return {"nav_projects": Project.query.order_by(Project.name.asc()).all()}

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()
        return render_template("500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
