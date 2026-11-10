"""
Memory extraction and embedding preparation.

Framework-independent: nothing here imports FastAPI or touches a request,
which is why these helpers could move as a block rather than being
rewritten. The meeting route calls into this module, and so does health
for the model-list check.

`get_available_models` is worth reading closely because it is the one
function with a deliberate failure mode. /api/health is unauthenticated,
so an unguarded provider call there would let any request burn the app's
own quota, and once the provider starts rate-limiting, the first 429 takes
down every add-meeting request as well. Failures are therefore cached with
a TTL, and the TTL is what stops a provider outage from turning into a
request-storm.
"""

import logging
import time

from config import DEFAULT_PROVIDER, EMBEDDING_MODEL
from database import db
from matching import normalize_title
from models import ActionItem, Blocker, Decision, Risk

# Cache for the provider's model list, and the TTL applied to a failed
# lookup so an unauthenticated /api/health cannot spend the app's rate
# limit quota. Success is cached for the life of the process because the
# list changes rarely; a failure is retried after this interval.
#
# Module-level on purpose, unlike the auth state: this cache is not per-app
# security, it is a quota guard, and two apps sharing it costs nothing
# while two apps each calling the provider on a health check doubles the
# quota spent.
MODELS_FAILURE_TTL_SECONDS = 60
_models_cache: list | None = None
_models_cache_failure_at: float | None = None

# ---------------------------------------------------------------------------
# Memory extraction (framework-independent, ported verbatim from app.py)


def get_available_models(router):
    # Dynamic discovery from the provider API. Used as a health check:
    # the add-meeting form fails fast if the default model is missing.
    #
    # Failures are cached with a TTL. /api/health is unauthenticated, so
    # without this every request burns a provider call, and once the
    # provider starts rate limiting the app's own quota the first 429
    # takes down every add-meeting request too.
    global _models_cache, _models_cache_failure_at

    if _models_cache is not None:
        return _models_cache

    now = time.monotonic()

    if _models_cache_failure_at is not None:
        if now - _models_cache_failure_at < MODELS_FAILURE_TTL_SECONDS:
            raise RuntimeError("The model list is temporarily unavailable.")
        # TTL expired: forget the failure and try again.
        _models_cache_failure_at = None

    try:
        models = router.get_models(DEFAULT_PROVIDER)
    except Exception as exception:
        # Log the cause, return only a code: the response must not tell an
        # anonymous caller anything about the provider, but an operator
        # reading the logs needs to know whether this is a missing key, a
        # rate limit or an unreachable host.
        _models_cache_failure_at = now
        logging.getLogger("ai-delivery-assistant.models").warning(
            "model list unavailable: %s: %s",
            type(exception).__name__,
            exception,
        )
        raise RuntimeError("The model list could not be loaded.") from exception

    _models_cache = models
    return models


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
    except (ValueError, RuntimeError, KeyError, TypeError, ConnectionError, TimeoutError):
        # Silent degradation: lexical candidate ranking still works.
        return memory

    if len(vectors) != len(pending):
        # The caller matches vectors to items positionally, so a short
        # batch must not quietly leave some items unembedded.
        return memory

    for (section, item, _), vector in zip(pending, vectors):
        item["embedding"] = vector

        row = db.session.get(_MEMORY_MODEL_CLASSES[section], item["id"])

        if row is not None:
            row.title_embedding = vector

    # No commit here. This helper runs in the middle of the caller's
    # meeting transaction: committing would persist a meeting row whose
    # analysis has not been applied yet, so a later rollback would leave
    # a "ghost" meeting that also blocks re-submitting the same notes
    # through the duplicate guard. The caller owns the transaction.

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
    except (ValueError, RuntimeError, ConnectionError, TimeoutError):
        return {}

    return dict(zip(titles, vectors))


