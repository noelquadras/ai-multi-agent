"""
Structured command schemas for the autonomous orchestrator.

Inspired by MetaGPT's RoleZero command parsing: the orchestrator LLM emits
structured OrchestratorOutput containing one or more OrchestratorCommands.
These commands drive all routing, plan mutation, and workflow control.

Usage:
    from agents.command_schemas import OrchestratorOutput, OrchestratorCommand
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """Single step in the orchestrator's dynamic execution plan."""
    step_id: int = Field(description="Unique step identifier (1-indexed)")
    description: str = Field(description="What this step accomplishes")
    agent: str = Field(
        description="Agent node name to handle this step. "
                    "Valid: spec_writer, generate, review, decide, "
                    "refine, test, analyze_test, document"
    )
    status: Literal["pending", "in_progress", "done", "skipped"] = Field(
        default="pending",
        description="Current execution status of this step"
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="Step IDs that must complete before this step can run"
    )


class PlanRevision(BaseModel):
    """A revised execution plan — the orchestrator can emit this to
    mutate the workflow at runtime (self-evolving workflow)."""
    steps: list[PlanStep] = Field(description="The full revised plan")
    reasoning: str = Field(
        default="",
        description="Why the plan was revised"
    )


class OrchestratorCommand(BaseModel):
    """Single structured command from the orchestrator LLM."""
    command: Literal[
        "spawn_agent",      # Dispatch work to a specific agent node
        "revise_plan",      # Mutate the current execution plan
        "finish_task",      # Mark the current plan step as done
        "ask_human",        # Request human/user input (future extension)
        "end_workflow",     # Terminate the entire workflow
    ] = Field(description="The command to execute")
    args: dict = Field(
        default_factory=dict,
        description="Command-specific arguments. "
                    "spawn_agent: {agent: str}  |  "
                    "revise_plan: {steps: [...], reasoning: str}  |  "
                    "finish_task: {step_id: int}  |  "
                    "ask_human: {question: str}  |  "
                    "end_workflow: {reason: str}"
    )
    rationale: str = Field(
        default="",
        description="Brief reasoning for choosing this command"
    )


class OrchestratorOutput(BaseModel):
    """Full structured output from one orchestrator think→act cycle.
    
    The LLM produces this on each iteration of the reasoning loop.
    It contains the chain-of-thought reasoning plus one or more
    commands to execute.
    """
    thinking: str = Field(
        description="Chain-of-thought reasoning about the current state, "
                    "what has been accomplished, and what should happen next"
    )
    commands: list[OrchestratorCommand] = Field(
        description="One or more commands to execute. "
                    "At least one command is required."
    )
    plan_update: Optional[PlanRevision] = Field(
        default=None,
        description="Optional inline plan revision. "
                    "Use when test/review feedback requires workflow changes."
    )
