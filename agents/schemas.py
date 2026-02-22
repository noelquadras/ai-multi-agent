"""
Structured Pydantic output schemas for all LLM agent nodes.

These schemas replace fragile raw-string parsing with typed,
machine-parseable models.  Downstream nodes (especially the refiner)
can access individual fields directly instead of applying heuristic
substring matching on long freeform text.

Usage in nodes:
    structured_llm = llm.with_structured_output(ReviewOutput)
    result: ReviewOutput = structured_llm.invoke(messages)
"""

from typing import Literal
from pydantic import BaseModel, Field


class ReviewOutput(BaseModel):
    """Structured output from the Code Reviewer node."""

    verdict: Literal["APPROVE", "NEEDS_REFINE"] = Field(
        description="APPROVE if the code is production-ready, NEEDS_REFINE if it has blocking issues."
    )
    critical_issues: list[str] = Field(
        default_factory=list,
        description="P0 blockers — bugs, security flaws, or incorrect behaviour that must be fixed."
    )
    minor_issues: list[str] = Field(
        default_factory=list,
        description="Style warnings, readability concerns, or non-critical improvements."
    )
    fix_suggestions: list[str] = Field(
        default_factory=list,
        description="Actionable, concrete fix instructions — one per issue."
    )
    overall_score: int = Field(
        ge=1, le=10,
        description="Code quality score from 1 (terrible) to 10 (production-perfect)."
    )


class AnalysisOutput(BaseModel):
    """Structured output from the Terminal Analyzer node."""

    verdict: Literal["PASS", "FIX_REQUIRED"] = Field(
        description="PASS if the code ran correctly, FIX_REQUIRED if a fix is needed."
    )
    error_type: Literal["syntax", "runtime", "assertion", "timeout", "none"] = Field(
        description="Category of the error observed, or 'none' if the code passed."
    )
    root_cause: str = Field(
        default="",
        description="Concise explanation of the root cause of the failure."
    )
    fix_hints: list[str] = Field(
        default_factory=list,
        description="Specific, actionable hints on how to fix the error."
    )


class DecisionOutput(BaseModel):
    """Structured output from the Decision Maker node."""

    decision: Literal["YES", "NO"] = Field(
        description="YES if the code needs refinement, NO if it is good enough."
    )
    rationale: str = Field(
        default="",
        description="Brief explanation of why the decision was made."
    )
