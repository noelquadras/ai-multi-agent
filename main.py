# main.py
import os
import re
import sqlite3
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.pregel._retry import RetryPolicy
from langgraph.prebuilt import ToolNode
from tools.langchain_tools import search_duckduckgo, search_serper, scrape_web_page
from agents.state import AgentState
from agents.nodes import (
    # Pub-Sub infrastructure
    manager_node,
    manager_router,
    registry,
    # Node functions (import triggers @subscribe registration)
    spec_writer_node,
    code_generator_node,
    code_reviewer_node,
    decision_maker_node,
    code_refiner_node,
    doc_writer_node,
    cli_tester_node,
    terminal_analyzer_node,
    classify_task_node,
    researcher_node,
    set_model_config,
)
from typing import Dict, Optional
from database import emit_event

load_dotenv()

# Configure environment
os.environ["OPENAI_API_KEY"] = "na"
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_MODEL_NAME"] = "mistral:7b-instruct"

# Groq API configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Durable checkpointer — persists graph state for resume-on-crash & replay
# NOTE: from_conn_string() is a context manager; use sqlite3.connect() directly.
_db_conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
_checkpointer = SqliteSaver(conn=_db_conn)

# Retry policy for transient LLM failures (timeouts, rate-limits, 503s)
_llm_retry = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0)


def clean_output(text: str) -> str:
    """Clean markdown code blocks from text."""
    if not text:
        return ""
    return re.sub(r"```[a-zA-Z]*|```", "", text).strip()


# Compiled graph cache — avoids re-building on every task
_compiled_graph = None


def create_agent_graph():
    """
    Create (or return cached) the compiled LangGraph state graph.
    
    Pub-Sub Architecture (MetaGPT-style Hub-and-Spoke):
        START → manager (LLM-powered router)
        Every agent node → manager
        manager → (Send with filtered state) → subscriber nodes OR END
    
    Agents self-register via @subscribe decorators. To add a new agent:
    1. Create a new node file in agents/
    2. Decorate it with @subscribe(ActionType.SOME_ACTION)
    3. Import it here — registration happens automatically
    No edge changes needed.
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    # Initialize graph with state schema
    workflow = StateGraph(AgentState)
    
    # ── The Hub: LLM-powered Manager ────────────────────────────────────
    workflow.add_node("manager", manager_node)
    
    # ── The Spokes: Agent nodes ─────────────────────────────────────────
    # LLM-calling nodes get a retry policy for transient failures
    workflow.add_node("spec_writer", spec_writer_node, retry=_llm_retry)
    workflow.add_node("generate", code_generator_node, retry=_llm_retry)
    workflow.add_node("review", code_reviewer_node, retry=_llm_retry)
    workflow.add_node("decide", decision_maker_node, retry=_llm_retry)
    workflow.add_node("refine", code_refiner_node, retry=_llm_retry)
    workflow.add_node("document", doc_writer_node, retry=_llm_retry)
    workflow.add_node("test", cli_tester_node)  # no retry — deterministic executor
    workflow.add_node("analyze_test", terminal_analyzer_node, retry=_llm_retry)
    workflow.add_node("classify_task", classify_task_node, retry=_llm_retry)
    workflow.add_node("researcher", researcher_node, retry=_llm_retry)
    
    # ── Tool execution node ─────────────────────────────────────────────
    # Make tools available to the ToolNode
    tools = [search_duckduckgo, search_serper, scrape_web_page]
    tool_node = ToolNode(tools)
    workflow.add_node("tools", tool_node, retry=_llm_retry)
    
    # ── Edge wiring: Hub-and-Spoke ──────────────────────────────────────
    # Entry point: START → manager
    workflow.set_entry_point("manager")
    
    # Every spoke points back to the hub
    for node_name in ["spec_writer", "generate", "review", "decide",
                      "refine", "document", "test", "analyze_test",
                      "classify_task", "researcher"]:
        workflow.add_edge(node_name, "manager")
        
    # Tool node points back to the manager (so LLM can read tool output)
    workflow.add_edge("tools", "manager")
    
    # Manager routes via conditional edge — returns Send() objects, END, or "tools"
    workflow.add_conditional_edges("manager", manager_router)
    
    # Log the subscription table for debugging
    subs = registry.all_subscriptions()
    print(f"Subscription Table: {subs}", flush=True)
    
    compiled = workflow.compile(checkpointer=_checkpointer)
    _compiled_graph = compiled
    return compiled


def run_software_crew(requirements: str, task_id: str, model: str = "ollama", agent_models: Optional[Dict[str, str]] = None, benchmark_test_code: Optional[str] = None):
    """
    Execute the LangGraph agent workflow.
    
    Args:
        requirements: User's code requirements
        task_id: Unique task identifier
        model: LLM model to use ("ollama" or "groq")
        agent_models: Optional dictionary of specific models for each agent
        benchmark_test_code: Optional test code for benchmarking
        
    Returns:
        Final state with all agent outputs
    """
    # Configure model for this run
    set_model_config(model, GROQ_API_KEY)
    
    # Create the graph
    graph = create_agent_graph()
    
    # Initial state
    initial_state: AgentState = {
        "requirements": requirements,
        "task_id": task_id,
        "model": model,
        "agent_models": agent_models or {},
        "benchmark_test_code": benchmark_test_code,
        
        # Coordination & Event Sourced state
        "events": [],
        "errors": [],
        "agent_states": {},
        "task_profile": None,
        "agent_metrics": {},
        
        # Telemetry
        "total_tokens_used": 0,
        "iteration_count": 0,
        "debug_loop_count": 0,
        
        # Core
        "messages": [],
        "current_agent": "manager",
    }
    
    # Execute the graph — thread_id enables checkpointer resume/replay
    config = {"configurable": {"thread_id": task_id}}
    
    # Check if a checkpoint already exists for this task
    existing_state = graph.get_state(config)
    
    if existing_state.values:
        print(f"\n--- RESUMING LANGGRAPH WORKFLOW (Task: {task_id}) ---\n", flush=True)
        # Pass None as input to resume exactly where it left off
        final_state = graph.invoke(None, config=config)
    else:
        print(f"\n--- STARTING NEW LANGGRAPH WORKFLOW (Task: {task_id}) ---\n", flush=True)
        # Pass initial_state for a fresh run
        final_state = graph.invoke(initial_state, config=config)
    
    print("\n--- WORKFLOW COMPLETE ---\n", flush=True)
    
    # =========================
    # EMIT FINAL RESULTS
    # =========================
    
    # Final results extraction from isolated states
    llm_states = final_state.get("agent_states", {})
    gen_state = llm_states.get("generate", {})
    refine_state = llm_states.get("refine", {})
    review_state = llm_states.get("review", {})
    decide_state = llm_states.get("decide", {})
    doc_state = llm_states.get("document", {})
    test_state = llm_states.get("test", {})
    spec_state = llm_states.get("spec_writer", {})

    final_code = clean_output(refine_state.get("refined_code") or gen_state.get("generated_code") or "")
    
    emit_event(task_id, {
        "type": "code_output",
        "agent": "refiner",
        "code": final_code
    })
    
    emit_event(task_id, {
        "type": "review_output",
        "agent": "reviewer",
        "review": review_state.get("review_report", "")
    })
    
    emit_event(task_id, {
        "type": "decision_output",
        "agent": "decision",
        "decision": decide_state.get("decision", "")
    })
    
    if doc_state.get("documentation"):
        emit_event(task_id, {
            "type": "doc_output",
            "agent": "doc_writer",
            "documentation": doc_state["documentation"]
        })
    
    if test_state.get("test_results"):
        emit_event(task_id, {
            "type": "test_output",
            "agent": "tester",
            "results": test_state["test_results"]
        })
    
    if final_state.get("errors"):
        emit_event(task_id, {"type": "system_error", "error": f"Workflow had {len(final_state['errors'])} errors."})

    emit_event(task_id, {"type": "task_completed"})
    
    # Return results in expected format
    results = {
        "generated_code": clean_output(gen_state.get("generated_code", "")),
        "review_report": review_state.get("review_report", ""),
        "decision": decide_state.get("decision", ""),
        "refined_code": final_code,
        "documentation": doc_state.get("documentation", ""),
        "test_results": test_state.get("test_results", ""),
        "model_used": model,
        "iteration_count": final_state.get("iteration_count", 0),
        "debug_loop_count": final_state.get("debug_loop_count", 0),
        "total_tokens_used": final_state.get("total_tokens_used"),
        "spec_structured": spec_state.get("spec_structured"),
        "spec_doc_path": spec_state.get("spec_doc_path"),
        "review_report_structured": review_state.get("review_report_structured"),
        "decision_output": decide_state.get("decision_output"),
        "analysis_structured": test_state.get("analysis_structured"),
        "events": final_state.get("events", []),
        "errors": final_state.get("errors", [])
    }

    return results


if __name__ == "__main__":
    import uuid
    model = input("Model (ollama/groq) [ollama]: ").strip() or "ollama"
    req = input("Enter requirements: ")
    task_id = f"run_{uuid.uuid4().hex[:6]}"
    result = run_software_crew(req, task_id=task_id, model=model)
    print(result)