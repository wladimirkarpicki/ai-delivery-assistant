@
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

class RiskItem(BaseModel):
    title: str
    description: str = ""
    impact: str = "unknown"
    mitigation: str = ""
    status: str = "open"

class BlockerItem(BaseModel):
    title: str
    description: str = ""
    status: str = "open"

class ActionItem(BaseModel):
    title: str
    details: str = ""
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "open"

class DecisionItem(BaseModel):
    title: str
    details: str = ""

class AnalysisResponse(BaseModel):
    executive_summary: str = ""
    project_status: str = "unknown"
    progress_summary: str = ""
    completed_items: List[str] = Field(default_factory=list)
    in_progress_items: List[str] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    blockers: List[BlockerItem] = Field(default_factory=list)
    decisions: List[DecisionItem] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)

