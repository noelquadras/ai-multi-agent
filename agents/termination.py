"""
Composable termination conditions for the agent loop.

Inspired by AutoGen's TerminationCondition pattern (composable with | and &).
Each condition is a callable that inspects AgentState and returns a
TerminationResult.  CompositeTermination composes them with OR-semantics
(stop if ANY condition fires).

Usage:
    from agents.termination import DEFAULT_TERMINATION

    result = DEFAULT_TERMINATION(state)
    if result.should_stop:
        print(f"Stopping: {result.reason}")
"""

from dataclasses import dataclass
from agents.state import AgentState


@dataclass
class TerminationResult:
    """Outcome of a single termination check."""
    should_stop: bool
    reason: str


class IterationLimitTermination:
    """Stop after a fixed number of graph iterations."""

    def __init__(self, max_iterations: int = 15):
        self.max_iterations = max_iterations

    def __call__(self, state: AgentState) -> TerminationResult:
        count = state.get("iteration_count", 0)
        if count >= self.max_iterations:
            return TerminationResult(True, f"Iteration limit {self.max_iterations} reached (current: {count})")
        return TerminationResult(False, "")


class TokenBudgetTermination:
    """Stop when cumulative token usage exceeds a budget."""

    def __init__(self, max_tokens: int = 100_000):
        self.max_tokens = max_tokens

    def __call__(self, state: AgentState) -> TerminationResult:
        used = state.get("total_tokens_used") or 0
        if used >= self.max_tokens:
            return TerminationResult(True, f"Token budget {self.max_tokens} exceeded (used: {used})")
        return TerminationResult(False, "")


class DebugLoopLimitTermination:
    """Stop after too many refine→test→analyze debug loops."""

    def __init__(self, max_debug_loops: int = 5):
        self.max_debug_loops = max_debug_loops

    def __call__(self, state: AgentState) -> TerminationResult:
        loops = state.get("debug_loop_count", 0)
        if loops >= self.max_debug_loops:
            return TerminationResult(True, f"Debug loop limit {self.max_debug_loops} reached (current: {loops})")
        return TerminationResult(False, "")


class CompositeTermination:
    """OR-semantics: stop if ANY condition is met."""

    def __init__(self, *conditions):
        self.conditions = conditions

    def __call__(self, state: AgentState) -> TerminationResult:
        for cond in self.conditions:
            result = cond(state)
            if result.should_stop:
                return result
        return TerminationResult(False, "")


# ─── Default policy used by should_refine_after_analysis ───
DEFAULT_TERMINATION = CompositeTermination(
    IterationLimitTermination(max_iterations=15),
    TokenBudgetTermination(max_tokens=100_000),
    DebugLoopLimitTermination(max_debug_loops=5),
)
