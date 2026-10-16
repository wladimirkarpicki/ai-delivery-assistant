"""
Deterministic pre-matching for meeting findings.

Before the LLM consolidation call, findings that exactly match an
existing item by canonical title are resolved without the LLM:

- unchanged duplicates (same status, or no status given) become MERGE
- explicit status changes become UPDATE, in both directions: closing
  (open -> resolved/completed) and reopening (resolved/completed -> open)

The canonical title is the item identity regardless of its current
status, so a resolved risk re-mentioned in a later meeting is reopened
rather than duplicated. Decisions are append-only: an exact title match
is the same decision and is merged without an LLM call.

The findings that still need the LLM are returned as copies annotated
with a candidate_ids shortlist of similar existing items, which keeps
the LLM from inventing ids. After the LLM answers, CREATE entries that
collide with an existing title are downgraded to MERGE.
"""

import re

ALL_SECTIONS = ("risks", "blockers", "action_items", "decisions")
AUTO_SECTIONS = ("risks", "blockers", "action_items")
CANDIDATE_LIMIT = 3

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on",
    "with", "at", "by", "from", "is", "are", "was", "were", "be",
}


def normalize_title(title):
    """Casefold, strip punctuation edges, and collapse whitespace."""
    if not isinstance(title, str):
        return ""

    title = title.strip().strip(".,;:!?-–—\"'()[]{}«»„“”")
    return " ".join(title.casefold().split())


def title_tokens(title):
    """Meaningful word tokens used for fuzzy similarity."""
    return {
        token
        for token in _WORD_RE.findall(normalize_title(title))
        if token not in _STOPWORDS
    }


def similarity(tokens_a, tokens_b):
    """Jaccard overlap between two token sets, from 0.0 to 1.0."""
    if not tokens_a or not tokens_b:
        return 0.0

    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _index_items(items):
    """Map canonical title -> item for a memory section."""
    index = {}

    for item in items or []:
        if not isinstance(item, dict):
            continue

        canonical = item.get("canonical_title")

        if not isinstance(canonical, str) or not canonical.strip():
            canonical = item.get("title")

        key = normalize_title(canonical)

        if key and key not in index:
            index[key] = item

    return index


def _find_candidates(items, finding_tokens, limit=CANDIDATE_LIMIT):
    """The most similar existing items for a finding, best first."""
    scored = []

    for item in items or []:
        if not isinstance(item, dict):
            continue

        score = similarity(finding_tokens, title_tokens(item.get("title")))

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("id") or 0))

    return scored[:limit]


def _status_change_new_item(section, existing, finding):
    """
    A new_item payload for a deterministic status-change UPDATE.

    The finding's own status is the target state, whether it closes
    the item (resolved/completed) or reopens it. Non-empty text
    fields from the finding are carried along.
    """
    new_item = {
        "title": existing.get("title"),
        "status": finding.get("status"),
    }

    for key in ("description", "details", "impact", "mitigation", "owner"):
        value = finding.get(key)

        if isinstance(value, str) and value.strip():
            new_item[key] = value

    due_date = finding.get("due_date")

    if isinstance(due_date, str) and due_date.strip():
        new_item["due_date"] = due_date

    return new_item


def _annotate_candidates(existing_memory, unmatched):
    """Copy each unmatched finding and attach its candidate_ids."""
    annotated = {}

    for section in ALL_SECTIONS:
        items = existing_memory.get(section) or []
        section_annotated = []

        for finding in unmatched.get(section) or []:
            tokens = title_tokens(finding.get("title"))
            candidates = _find_candidates(items, tokens)

            section_annotated.append({
                **finding,
                "candidate_ids": [
                    item.get("id") for _, item in candidates
                ],
            })

        annotated[section] = section_annotated

    return annotated


def _dedupe_findings(findings):
    """
    Collapse same-normalized-title findings within one meeting.

    The first mention wins; a later mention that flips the status
    replaces an earlier open one. Titleless findings pass through
    unchanged (the plan applier records them for review).
    """
    seen = {}
    ordered = []

    for finding in findings or []:
        if not isinstance(finding, dict):
            continue

        key = normalize_title(finding.get("title"))

        if not key:
            ordered.append(finding)
            continue

        if key not in seen:
            seen[key] = finding
            ordered.append(finding)
            continue

        previous = seen[key]
        later_flips = finding.get("status") in ("resolved", "completed")
        previous_flips = previous.get("status") in ("resolved", "completed")

        if later_flips and not previous_flips:
            for index, candidate in enumerate(ordered):
                if candidate is previous:
                    ordered[index] = finding
                    break

            seen[key] = finding

    return ordered


def pre_match(existing_memory, analysis):
    """
    Deterministic pre-matching pass over new findings.

    Returns {"auto": {section: [plan entries]}, "llm_findings":
    {section: [finding copies]}}. The original analysis payload is
    not modified.
    """
    auto = {section: [] for section in ALL_SECTIONS}
    unmatched = {section: [] for section in ALL_SECTIONS}

    for section in ALL_SECTIONS:
        findings = _dedupe_findings(analysis.get(section) or [])
        index = _index_items(existing_memory.get(section) or [])

        for finding in findings:
            if not isinstance(finding, dict):
                continue

            existing = index.get(normalize_title(finding.get("title")))

            if existing is None:
                unmatched[section].append(finding)
                continue

            if section == "decisions":
                # Decisions are append-only: an exact title match is
                # the same decision, merged without an LLM call.
                auto[section].append({
                    "decision": "MERGE",
                    "existing_item_id": existing.get("id"),
                    "new_item": {"title": existing.get("title")},
                    "canonical_title": existing.get("title"),
                    "reason": (
                        "deterministic pre-match: duplicate decision title"
                    ),
                })
                continue

            if section not in AUTO_SECTIONS:
                unmatched[section].append(finding)
                continue

            finding_status = finding.get("status")
            existing_status = existing.get("status")

            status_changes = (
                isinstance(finding_status, str)
                and finding_status.strip() != ""
                and finding_status != existing_status
            )

            if status_changes:
                auto[section].append({
                    "decision": "UPDATE",
                    "existing_item_id": existing.get("id"),
                    "new_item": _status_change_new_item(section, existing, finding),
                    "canonical_title": existing.get("title"),
                    "reason": (
                        "deterministic pre-match: exact title match "
                        "with status change"
                    ),
                })
            else:
                auto[section].append({
                    "decision": "MERGE",
                    "existing_item_id": existing.get("id"),
                    "new_item": {"title": existing.get("title")},
                    "canonical_title": existing.get("title"),
                    "reason": (
                        "deterministic pre-match: exact duplicate title"
                    ),
                })

    return {
        "auto": auto,
        "llm_findings": _annotate_candidates(existing_memory, unmatched),
    }


def has_llm_findings(llm_findings):
    """True when at least one finding still needs the LLM."""
    return any(llm_findings.get(section) for section in ALL_SECTIONS)


def downgrade_create_duplicates(existing_memory, plan):
    """
    Rewrite CREATE entries whose normalized title collides with an
    existing item (any status) into MERGE entries.

    Returns the number of downgraded entries. Mutates the plan in
    place; the plan applier validates the rewritten entries like any
    other.
    """
    downgraded = 0

    for section in ALL_SECTIONS:
        entries = (plan or {}).get(section) or []
        index = _index_items(existing_memory.get(section) or [])

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            if entry.get("decision") != "CREATE":
                continue

            new_item = entry.get("new_item") or {}
            existing = index.get(normalize_title(new_item.get("title")))

            if existing is None:
                continue

            entry["decision"] = "MERGE"
            entry["existing_item_id"] = existing.get("id")
            entry["reason"] = (
                "deterministic duplicate check: CREATE collided "
                "with an existing title"
            )
            downgraded += 1

    return downgraded


def combine_plans(auto_by_section, llm_plan):
    """Merge deterministic entries and the LLM plan into one plan."""
    combined = {}

    for section in ALL_SECTIONS:
        combined[section] = (
            list((auto_by_section or {}).get(section) or [])
            + list((llm_plan or {}).get(section) or [])
        )

    return combined
