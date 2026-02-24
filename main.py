# main.py
import os
import re
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
    doc_writer_node,
    cli_tester_node,
    terminal_analyzer_node,
    should_refine,
    should_refine_after_analysis,
    set_model_config
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
_compiled_graphs: dict[bool, object] = {}


def create_agent_graph(include_cli_test: bool = True):
    """
    Create (or return cached) the compiled LangGraph state graph.
    
    Graph structure:
        START → spec_writer → generate → review → decide → [conditional] → test → document → END
                                                            ↓
                                                         refine → test → document
    
    Args:
        include_cli_test: Whether to include CLI testing node (patent feature)
    """
    if include_cli_test in _compiled_graphs:
        return _compiled_graphs[include_cli_test]

    # Initialize graph with state schema
    workflow = StateGraph(AgentState)
    
    # Add nodes — LLM-calling nodes get a retry policy for transient failures
    workflow.add_node("spec_writer", spec_writer_node, retry=_llm_retry)
    workflow.add_node("generate", code_generator_node, retry=_llm_retry)
    workflow.add_node("review", code_reviewer_node, retry=_llm_retry)
    workflow.add_node("decide", decision_maker_node, retry=_llm_retry)
    workflow.add_node("refine", code_refiner_node, retry=_llm_retry)
    workflow.add_node("document", doc_writer_node, retry=_llm_retry)
    
    if include_cli_test:
        workflow.add_node("test", cli_tester_node)  # no retry — deterministic executor
        workflow.add_node("analyze_test", terminal_analyzer_node, retry=_llm_retry)
    
    # Define edges (workflow connections)
    workflow.set_entry_point("spec_writer")
    
    # Sequential flow
    workflow.add_edge("spec_writer", "generate")
    workflow.add_edge("generate", "review")
    workflow.add_edge("review", "decide")
    
    # Conditional edge: refine or skip to documentation
    if include_cli_test:
        workflow.add_conditional_edges(
            "decide",
            should_refine,
            {
                "refine": "refine",
                "document": "test"  # Skip refine, go to test
            }
        )
        workflow.add_edge("refine", "test")
        
        # New Analyzer Step
        workflow.add_edge("test", "analyze_test")
        
        workflow.add_conditional_edges(
            "analyze_test",
            should_refine_after_analysis,
            {
                "refine": "refine",      # Targeted fix
                "generate": "generate",  # Full regeneration (HandoffMessage pattern)
                "document": "document"   # Move forward
            }
        )
    else:
        workflow.add_conditional_edges(
            "decide",
            should_refine,
            {
                "refine": "refine",
                "document": "document"
            }
        )
        workflow.add_edge("refine", "document")
    
    workflow.add_edge("document", END)
    
    compiled = workflow.compile(checkpointer=_checkpointer)
    _compiled_graphs[include_cli_test] = compiled
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
    
    # Create the graph with CLI testing enabled
    graph = create_agent_graph(include_cli_test=True)
    
    # Initial state
    initial_state: AgentState = {
        "requirements": requirements,
        "task_id": task_id,
        "model": model,
        "agent_models": agent_models or {},
        "benchmark_test_code": benchmark_test_code,
        "generated_code": "",
        "review_report": "",
        "decision": "",
        "refined_code": "",
        "documentation": "",
        "test_results": "",
        "messages": [],
        "current_agent": "",
        "error": None,
        "iteration_count": 0,
        "debug_loop_count": 0,
        "total_tokens_used": None,
        # Spec writer output
        "spec_doc_path": None,
        "spec_structured": None,
        # Structured Pydantic outputs
        "review_report_structured": None,
        "decision_output": None,
        "analysis_structured": None,
        # Per-agent memory
        "refiner_memory": None,
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
    
    # Final code (use refined if available, otherwise generated)
    final_code = clean_output(final_state.get("refined_code") or final_state["generated_code"])
    
    emit_event(task_id, {
        "type": "code_output",
        "agent": "refiner",
        "code": final_code
    })
    
    emit_event(task_id, {
        "type": "review_output",
        "agent": "reviewer",
        "review": final_state["review_report"]
    })
    
    emit_event(task_id, {
        "type": "decision_output",
        "agent": "decision",
        "decision": final_state["decision"]
    })
    
    emit_event(task_id, {
        "type": "doc_output",
        "agent": "doc_writer",
        "documentation": final_state["documentation"]
    })
    
    # Emit test results if available
    if final_state.get("test_results"):
        emit_event(task_id, {
            "type": "test_output",
            "agent": "tester",
            "results": final_state["test_results"]
        })
    
    emit_event(task_id, {"type": "task_completed"})
    
    # Return results in expected format
    results = {
        "generated_code": clean_output(final_state["generated_code"]),
        "review_report": final_state["review_report"],
        "decision": final_state["decision"],
        "refined_code": final_code,
        "documentation": final_state["documentation"],
        "test_results": final_state.get("test_results", ""),
        "model_used": model,
        # Telemetry fields consumed by the benchmark harness
        "iteration_count": final_state.get("iteration_count", 0),
        "debug_loop_count": final_state.get("debug_loop_count", 0),
        "total_tokens_used": final_state.get("total_tokens_used"),
        # Structured Pydantic outputs
        "spec_structured": final_state.get("spec_structured"),
        "spec_doc_path": final_state.get("spec_doc_path"),
        "review_report_structured": final_state.get("review_report_structured"),
        "decision_output": final_state.get("decision_output"),
        "analysis_structured": final_state.get("analysis_structured"),
    }

    return results


if __name__ == "__main__":
    model = input("Model (ollama/groq) [ollama]: ").strip() or "ollama"
    req = input("Enter requirements: ")
    result = run_software_crew(req, task_id="debug", model=model)
    print(result)