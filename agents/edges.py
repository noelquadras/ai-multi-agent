"""
Conditional edge functions for the LangGraph agent workflow.

These functions determine routing between nodes based on state.
"""

from agents.state import AgentState
from agents.termination import DEFAULT_TERMINATION
from database import emit_event


def should_refine(state: AgentState) -> str:
    """
    Determine next node based on decision.
    
    Reads the structured decision_output if available, otherwise
    falls back to the raw decision string.
    
    Returns:
        "refine" if code needs refinement
        "document" if code is good enough to skip refinement
    """
    do = state.get("decision_output")
    if do:
        decision = do.get("decision", "NO")
    else:
        decision = state.get("decision", "NO").upper()
    
    if "YES" in decision:
        emit_event(state["task_id"], {
            "type": "log",
            "message": "🔄 Decision: Code needs refinement"
        })
        return "refine"
    else:
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Decision: Code is good, skipping refinement"
        })
        return "document"


def should_refine_after_analysis(state: AgentState) -> str:
    """
    Decide based on the Analyzer's output and composable termination conditions.
    
    Uses DEFAULT_TERMINATION (iteration limit, token budget, debug loop limit)
    to guard against runaway loops before checking the analysis verdict.
    """
    term_result = DEFAULT_TERMINATION(state)
    if term_result.should_stop:
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🛑 Stopping: {term_result.reason}"
        })
        return "document"

    ao = state.get("analysis_structured")
    if ao:
        verdict = ao.get("verdict", "PASS")
    else:
        analysis_text = state.get("analysis", "")
        if "REGENERATE" in analysis_text:
            verdict = "REGENERATE"
        elif "FIX_REQUIRED" in analysis_text:
            verdict = "FIX_REQUIRED"
        else:
            verdict = "PASS"

    if verdict == "REGENERATE":
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🔁 Analyzer: Approach is wrong — escalating to full REGENERATE"
        })
        return "generate"

    if verdict == "FIX_REQUIRED":
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🔄 Analyzer: Fix required — debug loop #{state.get('debug_loop_count', 0)}"
        })
        return "refine"

    return "document"
