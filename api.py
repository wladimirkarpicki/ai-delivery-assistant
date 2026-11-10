"""
FastAPI application: the JSON API behind the React frontend.

Every route from the original Flask-era layer is ported with the same
semantics (the stack is FastAPI + plain SQLAlchemy 2.x; Flask is not a
dependency): the same consolidation pipeline, the same guardrails, the
same idempotency rules. HTML rendering moved to the React frontend; flash
messages became structured JSON responses:

- validation failures -> 400 {"error": "..."}
- missing records     -> 404
- manual resolve warnings (idempotent no-ops) -> 200 {"level": "warning", ...}
- consolidation fallback -> 201 with a "warning" field

The factory mirrors the original one: create_app(router_instance=None,
database_url=None), so the test suite drives a FakeRouter against an
in-memory database exactly as before.
"""

import logging
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Imported directly rather than through the db namespace: the staticmethod
# re-export loses select()'s overloads, so mypy then reads a multi-column
# select as a single-argument call.
from sqlalchemy import func, select

# The three analytics handlers, as a router. They share one discipline and
# moved together because a change to it has to be made in all three.
from api_analytics import router as analytics_router

# Auth is module-level and reads its state from request.app.state, so a
# separate module could import these as dependencies. The previous form
# was a set of closures inside create_app, which is what blocked a router
# split: a closure closes over the create_app call that made it.
from api_auth import (
    # Re-exported because the test suite clears this dict between tests. It
    # lives in api_auth with the login route that fills it, and a
    # module-level dict is what keeps the lockout process-wide rather than
    # per-app.
    _is_production,
    get_current_user,
    install_auth,
)
from api_deps import _get_project, install_deps
from api_memory import (
    get_available_models,
)
from api_routers_auth import router as auth_router
from api_routers_items import router as items_router
from api_routers_meetings import router as meetings_router

# Serializers, moved out whole. They are pure functions over rows, so they
# moved with no other change, and the route handlers below reach them
# through this import rather than a copy that could drift.
from api_serializers import (
    error_response,
    serialize_action,
    serialize_blocker,
    serialize_event,
    serialize_project_summary,
    serialize_risk,
    serialize_state,
)
from config import DEFAULT_MODEL, __version__
from config_loader import (
    get_jwt_secret_key,
    get_token_ttl_hours,
)
from database import (
    close_request_scope,
    configure_database,
    db,
    new_request_scope,
)
from models import (
    ActionItem,
    Blocker,
    HistoryEvent,
    Meeting,
    Project,
    Risk,
)
from project_memory import (
    _bounded,
)
from report import build_status_report
from router import ModelRouter
from telemetry import REQUEST_ID_HEADER, configure_logging, new_request_id


def _dt(value):
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Request bodies


class ProjectCreate(BaseModel):
    name: str = ""
    description: str = ""


def create_app(router_instance=None, database_url=None):
    configure_database(database_url)
    router = router_instance or ModelRouter()

    # The router goes on app.state, not a closure: the test suite passes a
    # fake per app, and a shared singleton would leak the last-bound fake
    # into every other app in the same process.
    app = FastAPI(
        title="AI Delivery Assistant",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    install_deps(app, router)

    # One formatter and level for the whole app, so a production line
    # carries a timestamp, a level and a logger name. Before this the
    # four loggers in the codebase ran on Python's defaults.
    configure_logging()

    # The version, on the first line the process writes. A bug report that
    # does not name a version cannot be acted on, and before this there was
    # nothing in the log or the response that carried it.
    logging.getLogger("ai-delivery-assistant.startup").info(
        "AI Delivery Assistant %s starting", __version__
    )

    # The Vite dev server proxies /api in development; production is
    # same-origin. localhost origins are allowed for convenience.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        # allow_credentials is required for the session cookie to travel
        # on cross-origin requests, and it is incompatible with a
        # wildcard in allow_origins or allow_headers, so both stay
        # explicit. Authorization stays listed for clients that have not
        # moved to the cookie yet.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # A CSP with no unsafe-inline in script-src is what makes the
        # next layer of defence real: the client reads the bearer token
        # from localStorage today, so any injected script can simply read
        # it back out. This header costs nothing and lands independently
        # of the cookie migration.
        #
        # style-src stays 'unsafe-inline' because the design assets in
        # static/ carry inline style attributes; tightening that is a
        # separate change. The one inline script that must run is the
        # pre-paint theme block in frontend/index.html, allowed by hash
        # rather than by unsafe-inline, so its exact bytes are pinned.
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'sha256-SpAlGCCFsricsGUdodyI/o/5Hb573esmO8SjeD7Mw7M='; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "frame-src 'none'"
        )
        # The remaining response headers are the standard set for a JSON
        # API that serves one SPA.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.middleware("http")
    async def request_session_scope(request: Request, call_next):
        # One scoped session per request, independent of the
        # threadpool thread that runs the endpoint.
        token = new_request_scope()

        # Echo the caller's id or mint one, so a user-reported failure
        # can be found in the log by matching this value.
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        finally:
            close_request_scope(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    # ------------------------------------------------------------------
    # Authentication: JWT HS256 bearer sessions. The account is
    # re-read from the database on every request, so tokens of
    # deleted accounts stop working immediately.
    secret_key = get_jwt_secret_key()

    if not secret_key:
        # The Docker healthcheck must not depend on .env: an
        # ephemeral key keeps the API serving; only tokens reset
        # on every restart.
        if _is_production():
            raise RuntimeError(
                "JWT_SECRET_KEY is not set and AIDA_ENV is production. "
                "Refusing to start: an ephemeral key would silently "
                "invalidate every token on restart, and a predictable "
                "one would let anyone mint an admin session."
            )
        secret_key = secrets.token_hex(32)
        logging.getLogger("ai-delivery-assistant.auth").warning(
            "JWT_SECRET_KEY is not set; generated an ephemeral key. "
            "Tokens stop validating on every restart. "
            "Set JWT_SECRET_KEY in .env for production."
        )

    token_ttl = timedelta(hours=get_token_ttl_hours())

    # The signing key and the ttl live on app.state, and the auth functions
    # in api_auth read them per request. A module-level global was the
    # alternative and is worse than it looks: secret_key is generated per
    # create_app call, and the test suite builds about ten apps in one
    # process, so a global would make all of them share one key and one
    # revocation set, and every test would keep passing while the isolation
    # they were written to check quietly disappeared.
    install_auth(app, secret_key, token_ttl)

    @app.get("/api/health")
    def health():
        """
        Readiness gate for the add-meeting form: the app always analyzes
        with the fixed NVIDIA route, so the form only needs to know
        whether that route is usable.

        The response is deliberately minimal. It used to return the model
        name and the raw provider error, which told an unauthenticated
        caller which vendor and exact model the app depends on, and
        whether the API key was configured at all.
        """
        try:
            models = get_available_models(router)
        except (ValueError, RuntimeError):
            # A stable reason code, never the provider's own message:
            # the key-missing case is a configuration detail, not
            # something to confirm to an anonymous caller.
            return {"analysis_ready": False, "reason": "model_list_unavailable"}

        if DEFAULT_MODEL not in models:
            return {"analysis_ready": False, "reason": "default_model_unavailable"}

        return {"analysis_ready": True, "reason": None}

    @app.get("/api/projects")
    def projects_list(user: dict = Depends(get_current_user)):
        return {
            "projects": [
                serialize_project_summary(project)
                for project in Project.query.order_by(Project.updated_at.desc()).all()
            ]
        }

    @app.post("/api/projects", status_code=201)
    def projects_create(body: ProjectCreate, user: dict = Depends(get_current_user)):
        # Clamped, not merely stripped: projects.name is varchar(200) and
        # PostgreSQL rejects an over-long value with a 500, which SQLite
        # would have accepted silently.
        name = _bounded((body.name or "").strip(), "name")
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
    def project_overview(project_id: int, user: dict = Depends(get_current_user)):
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

    @app.get("/api/projects/{project_id}/history")
    def project_history(
        project_id: int,
        type: str = "",
        user: dict = Depends(get_current_user),
    ):
        project = _get_project(project_id)
        selected_type = (type or "").strip()

        type_counts: dict[str, int] = {}
        results = db.session.execute(
            select(HistoryEvent.event_type, func.count(HistoryEvent.id))
            .where(HistoryEvent.project_id == project.id)
            .group_by(HistoryEvent.event_type)
        ).all()
        for event_type, count in results:
            type_counts[str(event_type)] = int(count)

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
    def status_report(
        project_id: int,
        download: int = 0,
        user: dict = Depends(get_current_user),
    ):
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

    # The routers, registered before the catch-all below. Ordering matters
    # here for a reason that is silent when it is wrong: spa_fallback
    # matches any path, so a router registered after it would never be
    # reached and its endpoints would 404 as the SPA.
    app.include_router(auth_router)
    app.include_router(analytics_router)
    app.include_router(items_router)
    app.include_router(meetings_router)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        candidate = (dist_dir / full_path).resolve()

        if full_path:
            try:
                candidate.relative_to(dist_dir)
            except ValueError:
                pass
            else:
                if candidate.is_file():
                    return FileResponse(candidate)

        index = dist_dir / "index.html"

        if index.is_file():
            return FileResponse(index)

        return JSONResponse(
            status_code=404,
            content={"error": "Frontend bundle is not built. Run: pnpm --dir frontend build"},
        )

    return app
