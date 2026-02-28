import os
import sqlite3
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.pregel._retry import RetryPolicy

from agents.state import AgentState
from agents.nodes import (
    spec_writer_node,
    code_generator_node,
    code_reviewer_node,
    decision_maker_node,
    code_refiner_node,
    cli_tester_node,
    terminal_analyzer_node,
    set_model_config,
)
from agents.react_supervisor import react_supervisor_node, react_supervisor_router
from database import emit_event

load_dotenv()

_db_conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
_checkpointer = SqliteSaver(conn=_db_conn)

_llm_retry = RetryPolicy(max_attempts=3)


def create_agent_graph():

    workflow = StateGraph(AgentState)

    # ─── Nodes ─────────────────────────────────
    workflow.add_node("supervisor", react_supervisor_node)

    workflow.add_node("spec_writer", spec_writer_node, retry=_llm_retry)
    workflow.add_node("coder", code_generator_node, retry=_llm_retry)
    workflow.add_node("reviewer", code_reviewer_node, retry=_llm_retry)
    workflow.add_node("refiner", code_refiner_node, retry=_llm_retry)
    workflow.add_node("tester", cli_tester_node)
    workflow.add_node("analyzer", terminal_analyzer_node)

    # ─── Entry ─────────────────────────────────
    workflow.set_entry_point("supervisor")

    # Agents always return to supervisor
    workflow.add_edge("spec_writer", "supervisor")
    workflow.add_edge("coder", "supervisor")
    workflow.add_edge("reviewer", "supervisor")
    workflow.add_edge("refiner", "supervisor")
    workflow.add_edge("tester", "supervisor")
    workflow.add_edge("analyzer", "supervisor")

    # Supervisor routing
    workflow.add_conditional_edges(
        "supervisor",
        react_supervisor_router,
        {
            "spec_writer": "spec_writer",
            "coder": "coder",
            "reviewer": "reviewer",
            "refiner": "refiner",
            "tester": "tester",
            "analyzer": "analyzer",
            "supervisor": "supervisor",
            END: END,
        },
    )

    return workflow.compile(checkpointer=_checkpointer)


def run_software_crew(
    requirements: str,
    task_id: str,
    model: str = "ollama",
    agent_models: dict | None = None,
    benchmark_test_code: str | None = None,
):

    set_model_config(model, "")

    graph = create_agent_graph()

    initial_state: AgentState = {
        "intent": None,
        "requirements": requirements,
        "task_id": task_id,
        "model": model,
        "agent_models": agent_models or {},
        "benchmark_test_code": benchmark_test_code,
        "events": [],
        "errors": [],
        "agent_states": {},
        "agent_metrics": {},
        "total_tokens_used": 0,
        "iteration_count": 0,
        "debug_loop_count": 0,
        "plan_iterations": 0,
        "make_iterations": 0,
        "test_iterations": 0,
        "execution_plan": [],
        "failure_type": None,
        "confidence_score": 0.0,
        "acceptance_criteria": {},
        "phase": None,
        "messages": [],
        "react_plan": [],
        "terminate": False,
        "current_agent": "supervisor",
    }

    config = {"configurable": {"thread_id": task_id}}

    final_state = graph.invoke(initial_state, config=config)

    emit_event(task_id, {"type": "task_completed"})

    return final_state