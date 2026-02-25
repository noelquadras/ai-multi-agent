"""
Action types and self-registration registry for the Pub-Sub architecture.

MetaGPT-style pattern: each node declares what it watches via @subscribe().
The Manager queries the registry at runtime to route messages.
Adding a new agent = create the file + decorate with @subscribe. No central
config editing required.

Usage:
    from agents.action_types import ActionType, subscribe, make_action_message

    @subscribe(ActionType.PRD_READY)
    def code_generator_node(state):
        ...
        return {"messages": [make_action_message("...", ActionType.CODE_READY, "generate")]}
"""

from enum import StrEnum
from langchain_core.messages import AIMessage


class ActionType(StrEnum):
    """All publishable action types in the system."""
    TASK_START          = "task_start"
    PRD_READY           = "prd_ready"
    CODE_READY          = "code_ready"
    REVIEW_READY        = "review_ready"
    DECISION_REFINE     = "decision_refine"
    DECISION_APPROVED   = "decision_approved"
    CODE_REFINED        = "code_refined"
    TEST_COMPLETE       = "test_complete"
    ANALYSIS_PASS       = "analysis_pass"
    ANALYSIS_FIX        = "analysis_fix"
    ANALYSIS_REGENERATE = "analysis_regenerate"
    DOCS_READY          = "docs_ready"


class SubscriptionRegistry:
    """
    Singleton registry. Nodes self-register with @subscribe at import time.
    The Manager queries this at runtime — knowledge of "who listens to what"
    lives in the Role (node), not in a central config.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._table: dict[str, list[str]] = {}
        return cls._instance

    def watch(self, node_name: str, *action_types: ActionType):
        """Register a node as a subscriber to one or more action types."""
        for at in action_types:
            key = str(at)
            if node_name not in self._table.setdefault(key, []):
                self._table[key].append(node_name)

    def get_subscribers(self, action_type: str) -> list[str]:
        """Return list of node names watching this action type."""
        return list(self._table.get(str(action_type), []))

    def all_subscriptions(self) -> dict[str, list[str]]:
        """Return snapshot of the full subscription table."""
        return {k: list(v) for k, v in self._table.items()}

    def reset(self):
        """Clear all registrations (useful for testing)."""
        self._table.clear()


# Module-level singleton
registry = SubscriptionRegistry()


def subscribe(*action_types: ActionType, node_name: str = None):
    """
    Decorator: registers the node function for the given action types.

    Args:
        action_types: ActionType values this node watches.
        node_name: Explicit graph node name. If not provided, inferred by
                   stripping the '_node' suffix from the function name.

    Example:
        @subscribe(ActionType.PRD_READY, node_name="generate")
        def code_generator_node(state): ...
        # → registers "generate" for "prd_ready"
    """
    def decorator(fn):
        name = node_name or getattr(fn, '_node_name', None)
        if name is None:
            # spec_writer_node → spec_writer
            fname = fn.__name__
            name = fname[:-5] if fname.endswith("_node") else fname
        registry.watch(name, *action_types)
        fn._watches = list(action_types)
        fn._node_name = name
        return fn
    return decorator


def make_action_message(
    content: str,
    action_type: ActionType,
    sender: str,
) -> AIMessage:
    """
    Create an AIMessage with pub-sub metadata in additional_kwargs.

    Every agent MUST use this to produce its output message so the
    Manager can read the action_type and route accordingly.
    """
    return AIMessage(
        content=content,
        additional_kwargs={
            "action_type": str(action_type),
            "sender": sender,
        },
    )
