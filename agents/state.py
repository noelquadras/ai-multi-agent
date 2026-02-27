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


class AgentMetrics(TypedDict):
    """Token usage and invocation metrics per agent."""
    calls: int
    tokens: int


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
    
    # ── Per-Agent Isolated States ─────────────────────────────────────
    # Each agent 'Worker-A' should only update state['agent_states']['Worker-A']
    agent_states: Annotated[dict[str, dict[str, Any]], merge_agent_states]
    
    # ── Global Metrics (Merge-Safe) ───────────────────────────────────
    agent_metrics: Annotated[dict[str, AgentMetrics], merge_dict]
    total_tokens_used: Optional[int]

    # ── Telemetry & Counters ──────────────────────────────────────────
    # Managers should be the ones incrementing these
    iteration_count: int
    debug_loop_count: int

    # ── Core LangGraph State ──────────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # ── Derived Helper (Used for shorthand if needed, but Event remains source of truth) ──
    # If using these, ensures they are updated ONLY by the Manager/Supervisor.
    current_agent: str 
