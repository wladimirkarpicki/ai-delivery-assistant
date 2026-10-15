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

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _TolerantModel(BaseModel):
    """Ignore unknown keys; validate the documented contract only."""

    model_config = ConfigDict(extra="ignore")


# -----------------------------------------------------------
# Analysis contract (analyzer.py)
# -----------------------------------------------------------

class RiskFinding(_TolerantModel):
    title: Optional[str] = None
    description: Optional[str] = None
    impact: Optional[str] = None
    mitigation: Optional[str] = None
    status: Optional[str] = None


class BlockerFinding(_TolerantModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class DecisionFinding(_TolerantModel):
    title: Optional[str] = None
    details: Optional[str] = None


class ActionItemFinding(_TolerantModel):
    title: Optional[str] = None
    details: Optional[str] = None
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None


class Analysis(_TolerantModel):
    executive_summary: Optional[str] = None
    project_status: Optional[str] = None
    progress_summary: Optional[str] = None
    completed_items: Optional[List[Any]] = None
    in_progress_items: Optional[List[Any]] = None
    risks: Optional[List[RiskFinding]] = None
    blockers: Optional[List[BlockerFinding]] = None
    decisions: Optional[List[DecisionFinding]] = None
    action_items: Optional[List[ActionItemFinding]] = None


# -----------------------------------------------------------
# Consolidation plan contract (memory_consolidator.py)
# -----------------------------------------------------------

class PlanEntry(_TolerantModel):
    decision: Optional[str] = None
    new_item: Optional[Dict[str, Any]] = None
    existing_item_id: Optional[Union[int, str]] = None
    canonical_title: Optional[str] = None
    reason: Optional[str] = None


class ConsolidationPlan(_TolerantModel):
    risks: List[PlanEntry] = Field(default_factory=list)
    blockers: List[PlanEntry] = Field(default_factory=list)
    action_items: List[PlanEntry] = Field(default_factory=list)
    decisions: List[PlanEntry] = Field(default_factory=list)


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
