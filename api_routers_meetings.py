"""
The meeting routes: submitting notes, and reading one back with its history.

`add_meeting` is the largest handler left in the application and is in this
module rather than split further because the body it has is one pipeline
that has to run in order: read the upload, guard the duplicate, run the
analysis, pre-match, consolidate, apply, commit. The steps are visible
top to bottom in one function, and splitting them across modules would
trade that for indirection without making any step smaller.

The pipeline's two properties that a reader should not have to take on
trust, both pinned by tests:

- a failure anywhere before the commit leaves no partial meeting, because
  the rollback is in the outer handler and the session is flushed not
  committed mid-way;
- the consolidation failure path degrades to the deterministic analysis
  rather than failing the request, and the reason goes to the log and not
  into the response.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlalchemy.exc import SQLAlchemyError

from analyzer import analyze_document, parse_analysis
from api_auth import UserFacingError, get_current_user
from api_deps import _get_project, get_router
from api_memory import (
    embed_finding_titles,
    ensure_item_embeddings,
    get_available_models,
    get_project_memory,
)
from api_serializers import (
    MEETING_SUBMIT_FAILED_MESSAGE,
    MODEL_LIST_UNAVAILABLE_MESSAGE,
    error_response,
    serialize_event,
    serialize_meeting,
    serialize_project_summary,
)
from api_uploads import _SyncUpload
from config import DEFAULT_MODEL, DEFAULT_PROVIDER
from database import db
from document_parser import extract_text
from matching import (
    combine_plans,
    downgrade_create_duplicates,
    has_llm_findings,
    pre_match,
)
from memory_consolidator import MemoryConsolidator
from models import HistoryEvent, Meeting
from project_memory import (
    _bounded,
    apply_consolidation_plan,
    apply_meeting_analysis,
    apply_state,
)

router = APIRouter()


@router.get("/api/projects/{project_id}/meetings")
def project_meetings(project_id: int, user: dict = Depends(get_current_user)):
    project = _get_project(project_id)

    return {
        "project": serialize_project_summary(project),
        "meetings": [serialize_meeting(m) for m in project.meetings],
    }

@router.post("/api/projects/{project_id}/meetings", status_code=201)
def add_meeting(
    request: Request,
    project_id: int,
    title: str = Form(""),
    meeting_notes: str = Form(""),
    meeting_file: UploadFile | None = None,
    user: dict = Depends(get_current_user),
):
    project = _get_project(project_id)

    try:
        # `provider` rather than `router`: in this module `router` is the
        # APIRouter these routes hang from, which is a different thing
        # with a different name. Confusing them is invisible until a
        # request arrives and an AttributeError says APIRouter has no
        # get_models, or no generate.
        provider = get_router(request)
        models = get_available_models(provider)
    except (ValueError, RuntimeError, httpx.HTTPError, httpx.TransportError) as exception:
        # Provider failures arrive as httpx errors, not as ValueError:
        # tenacity retries with reraise=True, so a 429 or a timeout
        # surfaces the original HTTPStatusError/TimeoutException. Without
        # those classes in the tuple this returned a bare 500.
        #
        # The exception text is logged and never returned: it carries
        # the provider's URL and status, which tells an anonymous
        # caller something about the infrastructure. The caller gets a
        # fixed sentence instead, and the operator gets the cause.
        logging.getLogger("ai-delivery-assistant.meetings").warning(
            "model list unavailable for a meeting submission: %s: %s",
            type(exception).__name__,
            exception,
        )
        return error_response(MODEL_LIST_UNAVAILABLE_MESSAGE)

    selected_model = DEFAULT_MODEL if DEFAULT_MODEL in models else None

    if selected_model is None:
        return error_response("The default model is currently unavailable.")

    warning = None

    try:
        if meeting_file is not None and meeting_file.filename:
            # document_parser.extract_text speaks the Flask
            # FileStorage protocol (sync .read(), .filename); wrap
            # the already-loaded upload bytes in that shape.
            #
            # This endpoint is sync on purpose: the pipeline below
            # makes blocking LLM calls with a 180 s timeout each, and
            # an async def would run it on the event loop, stalling
            # every other request including /api/health. As a sync
            # endpoint FastAPI runs it in the threadpool instead.
            upload_bytes = meeting_file.file.read()
            original_text = extract_text(_SyncUpload(meeting_file.filename, upload_bytes))
            # The client controls this string, and source_filename is
            # varchar(255), so a long name would fail on PostgreSQL.
            source_filename = _bounded(meeting_file.filename, "source_filename")
        elif meeting_notes.strip():
            original_text, source_filename = meeting_notes.strip(), None
        else:
            raise UserFacingError("Upload meeting notes or paste meeting text.")

        # Idempotency: re-submitting identical notes is a
        # no-op rather than a second memory mutation.
        duplicate_meeting = Meeting.query.filter_by(
            project_id=project.id,
            original_text=original_text,
        ).first()

        if duplicate_meeting is not None:
            raise UserFacingError(
                f"Identical meeting notes already exist "
                f"({duplicate_meeting.title}, "
                f"{duplicate_meeting.created_at:%Y-%m-%d}). "
                f"No changes were applied."
            )

        analysis_text = analyze_document(original_text, DEFAULT_PROVIDER, selected_model, provider)
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
            ensure_item_embeddings(provider, existing_memory)
            finding_embeddings = embed_finding_titles(
                provider, analysis_json
            )
            pre_matched = pre_match(
                existing_memory, analysis_json, finding_embeddings
            )
            llm_findings = pre_matched["llm_findings"]

            if has_llm_findings(llm_findings):
                consolidator = MemoryConsolidator(provider)
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
        except (
            ValueError,
            RuntimeError,
            KeyError,
            TypeError,
            httpx.HTTPError,
            httpx.TransportError,
        ) as consolidation_error:
            # Fallback to traditional analysis if consolidation fails.
            # The httpx classes matter: without them a provider failure
            # during consolidation escapes this handler entirely and the
            # endpoint returns 500 instead of degrading to the
            # deterministic path, which is what this branch documents.
            #
            # The cause goes to the log and not into the warning. The
            # warning is part of the response, and the exception text
            # carries the provider endpoint and status, or the failing
            # statement, which is exactly what an anonymous caller
            # should not read. The caller is told that the deterministic
            # path was used; the operator is told why.
            logging.getLogger("ai-delivery-assistant.meetings").warning(
                "consolidation fell back to standard analysis: %s: %s",
                type(consolidation_error).__name__,
                consolidation_error,
                exc_info=True,
            )
            warning = (
                "Note: Consolidation encountered an issue, "
                "so standard analysis was used instead."
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
            response["warning"] = warning  # type: ignore[assignment]

        return response
    except (
        ValueError,
        RuntimeError,
        SQLAlchemyError,
        httpx.HTTPError,
        httpx.TransportError,
    ) as exception:
        # SQLAlchemyError is in the tuple on purpose. SQLite does not
        # enforce varchar(n), so a too-long value from an LLM (or a
        # long upload filename) is only caught on a real PostgreSQL,
        # where it raises DataError. Without this, that surface is a
        # 500 instead of a 400, and the session is left dirty. The
        # httpx classes cover a provider failure that escapes the
        # inner handler.
        db.session.rollback()

        # The two raises inside this block carry messages written for
        # the user, so they are returned. Everything else is either a
        # provider failure or an internal error whose text says where
        # the stack lives, and that goes to the log only.
        if isinstance(exception, UserFacingError):
            return error_response(str(exception))

        logging.getLogger("ai-delivery-assistant.meetings").warning(
            "meeting submission failed: %s: %s",
            type(exception).__name__,
            exception,
            exc_info=True,
        )
        return error_response(MEETING_SUBMIT_FAILED_MESSAGE)

@router.get("/api/meetings/{meeting_id}")
def meeting_detail(meeting_id: int, user: dict = Depends(get_current_user)):
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

