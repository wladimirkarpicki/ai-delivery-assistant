import os

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_wtf import CSRFProtect

from analyzer import analyze_document, parse_analysis
from config import DEFAULT_MODEL, DEFAULT_PROVIDER
from database import configure_database, db
from document_parser import extract_text
from memory_consolidator import MemoryConsolidator
from models import ActionItem, Blocker, Decision, HistoryEvent, Meeting, Project, Risk
from project_memory import apply_consolidation_plan, apply_meeting_analysis
from router import ModelRouter

def get_available_models(router):
    # Dynamic discovery from the provider API. Used as a health check:
    # the add-meeting form fails fast if the default model is missing.
    return router.get_models(DEFAULT_PROVIDER)


def get_project_memory(project_id):
    """Extract the current project memory from the database."""
    memory = {
        "risks": [],
        "blockers": [],
        "action_items": [],
        "decisions": []
    }
    
    # Get open risks
    for risk in Risk.query.filter_by(project_id=project_id, status="open").all():
        memory["risks"].append({
            "id": risk.id,
            "title": risk.title,
            "description": risk.description,
            "impact": risk.impact,
            "mitigation": risk.mitigation,
            "status": risk.status
        })
    
    # Get open blockers
    for blocker in Blocker.query.filter_by(project_id=project_id, status="open").all():
        memory["blockers"].append({
            "id": blocker.id,
            "title": blocker.title,
            "description": blocker.description,
            "status": blocker.status
        })
    
    # Get open action items
    for action in ActionItem.query.filter_by(project_id=project_id, status="open").all():
        memory["action_items"].append({
            "id": action.id,
            "title": action.title,
            "details": action.details,
            "owner": action.owner,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "status": action.status
        })
    
    # Get decisions
    for decision in Decision.query.filter_by(project_id=project_id).all():
        memory["decisions"].append({
            "id": decision.id,
            "title": decision.title,
            "details": decision.details
        })
    
    return memory


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

    @app.get("/projects/<int:project_id>")
    def project_overview(project_id):
        project = db.session.get(Project, project_id) or abort(404)
        return render_template("project_overview.html", project=project, risks=Risk.query.filter_by(project_id=project.id, status="open").order_by(Risk.id.desc()).all(), blockers=Blocker.query.filter_by(project_id=project.id, status="open").order_by(Blocker.id.desc()).all(), actions=ActionItem.query.filter_by(project_id=project.id, status="open").order_by(ActionItem.id.desc()).all(), meeting_count=Meeting.query.filter_by(project_id=project.id).count())

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
        events = HistoryEvent.query.filter_by(project_id=project.id).order_by(HistoryEvent.created_at.desc(), HistoryEvent.id.desc()).all()
        return render_template("history.html", project=project, events=events)

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
                if not selected_model:
                    raise ValueError("No supported models are currently available.")
                analysis_text = analyze_document(original_text, DEFAULT_PROVIDER, selected_model, router)
                analysis_json = parse_analysis(analysis_text)
                meeting = Meeting(project_id=project.id, title=request.form.get("title", "").strip() or "Untitled meeting", source_filename=source_filename, original_text=original_text, analysis_text=analysis_text, analysis_json=analysis_json, provider=DEFAULT_PROVIDER, model=selected_model)
                db.session.add(meeting)
                db.session.flush()
                
                # Use AI-driven consolidation to avoid duplicates
                try:
                    existing_memory = get_project_memory(project.id)
                    consolidator = MemoryConsolidator(router)
                    consolidation_plan = consolidator.consolidate(
                        existing_memory=existing_memory,
                        new_analysis=analysis_json,
                        provider=DEFAULT_PROVIDER,
                        model=selected_model
                    )
                    apply_consolidation_plan(project, meeting, consolidation_plan)
                except Exception as consolidation_error:
                    # Fallback to traditional analysis if consolidation fails
                    flash(f"Note: Consolidation encountered an issue ({str(consolidation_error)}), using standard analysis.", "warning")
                    apply_meeting_analysis(project, meeting, analysis_json)
                
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
