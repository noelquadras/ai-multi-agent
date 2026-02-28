"""
State schema for LangGraph agent workflow.
This defines the shared state that flows through all agent nodes.
"""

from typing import TypedDict, Annotated, Sequence, Optional, Literal, Any
from datetime import datetime
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dict(old: dict, new: dict) -> dict:
    """Merge two dictionaries, with the new one overwriting existing keys."""
    if old is None: return new
    if new is None: return old
    return {**old, **new}


def append_list(old: list, new: list) -> list:
    """Append-only reducer for lists."""
    if old is None: return new or []
    if new is None: return old
    return old + new


def merge_agent_states(old: dict[str, dict], new: dict[str, dict]) -> dict[str, dict]:
    """
    Isolated state reducer. 
    Each agent can only update its own sub-key in the agent_states dict.
    """
    if old is None: return new or {}
    if new is None: return old
    
    # Deep merge at the top level (per-agent key)
    result = old.copy()
    for agent_id, state_update in new.items():
        if agent_id in result:
            result[agent_id] = {**result[agent_id], **state_update}
        else:
            result[agent_id] = state_update
    return result


class Event(TypedDict):
    """System event for event-sourced coordination."""
    type: str  # e.g., "agent_started", "routing_decision", "error"
    agent: str
    timestamp: str
    data: Optional[dict[str, Any]]


class TaskProfile(TypedDict, total=False):
    """Classification of the task complexity and required execution path."""
    complexity: Literal["trivial", "standard", "complex"]
    needs_spec: bool
    needs_review: bool
    needs_docs: bool
    needs_testing: bool
    rationale: str


class TaskInfo(TypedDict, total=False):
    """Information about a task in the plan."""
    task_id: str
    instruction: str
    task_type: str
    assignee: str
    dependent_task_ids: list[str]
    is_finished: bool
    result: str


class TaskPlan(TypedDict, total=False):
    """Dynamic task plan created by the manager."""
    goal: str
    tasks: list[TaskInfo]


class PlanStep(TypedDict):
    """A strictly structured step in the execution plan."""
    step_id: int
    phase: Literal["PLAN", "MAKE", "TEST"]
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"]


class AgentMetrics(TypedDict, total=False):
    """Token usage and execution time metrics per phase."""
    tokens: int
    execution_time: float


class AgentState(TypedDict):
    """
    Shared state across all agent nodes in the graph.
    Converted to Event-Sourced model for coordination.
    """
    # ── Input (Static) ──────────────────────────────────────────────────
    requirements: str
    task_id: str
    model: str
    agent_models: Optional[dict[str, str]]
    benchmark_test_code: Optional[str]
    
    # ── Coordination (Event Sourced / Supervisor Only) ─────────────────
    # Worker agents should NOT update these directly.
    # Supervisor derives current_agent and routing from messages or these events.
    events: Annotated[list[Event], append_list]
    errors: Annotated[list[Event], append_list]
    
    # ── Global Shared Context (Single-Writer Pattern) ──────────────────
    # Task Profile: Written only by Classifier/Supervisor.
    task_profile: Optional[TaskProfile]
    
    # Task Plan: Dynamic plan created by manager for task execution
    task_plan: Optional[TaskPlan]
    
    # Retry Strategy: Hint for retrying with different approach
    _retry_strategy: Optional[str]
    
    # ── Per-Agent Isolated States ─────────────────────────────────────
    # Each agent 'Worker-A' should only update state['agent_states']['Worker-A']
    agent_states: Annotated[dict[str, dict[str, Any]], merge_agent_states]
    
    # Global Metrics (Merge-Safe) ───────────────────────────────────
    agent_metrics: Annotated[dict[str, AgentMetrics], merge_dict]
    total_tokens_used: Optional[int]

    # ── Telemetry & Counters ──────────────────────────────────────────
    # Managers should be the ones incrementing these
    iteration_count: int
    debug_loop_count: int
    plan_iterations: int
    make_iterations: int
    test_iterations: int

    # ── Nested Graph & Autonomous State ───────────────────────────────
    execution_plan: list[PlanStep]
    failure_type: Optional[Literal["runtime_error", "syntax_error", "logical_failure", "spec_mismatch", "timeout", "unknown"]]
    confidence_score: float
    acceptance_criteria: dict
    phase: Optional[Literal["PLAN", "MAKE", "TEST", "DONE"]]

    # ── Core LangGraph State ──────────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # ── ReAct Supervisor State ────────────────────────────────────────
    react_plan: list[dict]
    react_plan_obj: Any
    working_memory: str
    artifact_registry: dict
    decision_trace: list[str]
    budget: dict
    last_failure_type: str
    terminate: bool

    # ── Derived Helper (Used for shorthand if needed, but Event remains source of truth) ──
    # If using these, ensures they are updated ONLY by the Manager/Supervisor.
    current_agent: str 
