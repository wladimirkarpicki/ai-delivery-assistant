"""
Pydantic schemas for the structured JSON contracts exchanged with the
AI provider.

Two contracts exist:

- Analysis: the output of the meeting analysis call (`analyzer.py`).
- ConsolidationPlan: the output of the memory consolidation call
  (`memory_consolidator.py`).

The schemas validate the shape of an AI response before the rest of
the application applies it to the database. Unknown keys are ignored
so prompt evolution does not break parsing, but wrong types are
rejected loudly: a partially malformed response fails the whole call
(or falls back to reconciliation) instead of silently corrupting
project memory.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _TolerantModel(BaseModel):
    """Ignore unknown keys; validate the documented contract only."""

    model_config = ConfigDict(extra="ignore")


# -----------------------------------------------------------
# Analysis contract (analyzer.py)
# -----------------------------------------------------------

class RiskFinding(_TolerantModel):
    title: str | None = None
    description: str | None = None
    impact: str | None = None
    mitigation: str | None = None
    status: str | None = None


class BlockerFinding(_TolerantModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None


class DecisionFinding(_TolerantModel):
    title: str | None = None
    details: str | None = None


class ActionItemFinding(_TolerantModel):
    title: str | None = None
    details: str | None = None
    owner: str | None = None
    due_date: str | None = None
    status: str | None = None


class Analysis(_TolerantModel):
    executive_summary: str | None = None
    project_status: str | None = None
    progress_summary: str | None = None
    completed_items: list[Any] | None = None
    in_progress_items: list[Any] | None = None
    risks: list[RiskFinding] | None = None
    blockers: list[BlockerFinding] | None = None
    decisions: list[DecisionFinding] | None = None
    action_items: list[ActionItemFinding] | None = None


# -----------------------------------------------------------
# Consolidation plan contract (memory_consolidator.py)
# -----------------------------------------------------------

class PlanEntry(_TolerantModel):
    decision: str | None = None
    new_item: dict[str, Any] | None = None
    existing_item_id: int | str | None = None
    canonical_title: str | None = None
    reason: str | None = None


class ConsolidationPlan(_TolerantModel):
    risks: list[PlanEntry] = Field(default_factory=list)
    blockers: list[PlanEntry] = Field(default_factory=list)
    action_items: list[PlanEntry] = Field(default_factory=list)
    decisions: list[PlanEntry] = Field(default_factory=list)


def _describe(error: ValidationError) -> str:
    problems = []

    for issue in error.errors():
        location = ".".join(str(part) for part in issue["loc"]) or "(root)"
        problems.append(f"{location}: {issue['msg']}")

    return "; ".join(problems)


def validate_analysis(data: dict) -> None:
    """
    Validate a parsed analysis payload against the Analysis schema.

    Raises ValueError with a human-readable list of problems, so
    callers can surface the failure without depending on pydantic.
    """
    try:
        Analysis.model_validate(data)
    except ValidationError as error:
        raise ValueError(
            "The AI response does not match the analysis schema: "
            f"{_describe(error)}"
        ) from error


def validate_consolidation_plan(data: dict) -> None:
    """
    Validate a parsed consolidation plan (see validate_analysis).

    Unlike the Analysis schema, sections may not be null here: the
    reconciliation fallback depends on knowing the plan is structurally
    complete.
    """
    try:
        ConsolidationPlan.model_validate(data)
    except ValidationError as error:
        raise ValueError(
            "The AI memory consolidation response does not match the "
            f"consolidation plan schema: {_describe(error)}"
        ) from error
