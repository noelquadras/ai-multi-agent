"""
LangGraph agent nodes — re-export hub.

Each node has been extracted into its own module under agents/.
This file re-exports everything for backward compatibility so that
existing imports like ``from agents.nodes import code_generator_node``
continue to work.

NOTE: Importing the node modules triggers @subscribe() decorators,
which auto-register each node in the SubscriptionRegistry.
"""

# ── Shared utilities ────────────────────────────────────────────────────────
from agents.llm_config import (          # noqa: F401
    get_ollama_llm,
    get_groq_llm,
    set_model_config,
    get_llm,
    check_interrupts,
    clean_code_output,
    _trimmed_invoke,
)

# ── Pub-Sub infrastructure ──────────────────────────────────────────────────
from agents.action_types import (        # noqa: F401
    ActionType,
    registry,
    subscribe,
    make_action_message,
)
from agents.manager import manager_node, manager_router  # noqa: F401

# ── Node functions (import triggers @subscribe registration) ────────────────
from agents.spec_writer import spec_writer_node            # noqa: F401
from agents.code_generator import code_generator_node      # noqa: F401
from agents.code_reviewer import code_reviewer_node        # noqa: F401
from agents.decision_maker import decision_maker_node      # noqa: F401
from agents.code_refiner import code_refiner_node          # noqa: F401
from agents.doc_writer import doc_writer_node              # noqa: F401
from agents.cli_tester import cli_tester_node              # noqa: F401
from agents.terminal_analyzer import terminal_analyzer_node  # noqa: F401
from agents.classifier import classify_task_node           # noqa: F401
from agents.researcher import researcher_node              # noqa: F401
