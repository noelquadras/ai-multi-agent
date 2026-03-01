"""
NODE 4: CODE REFINER

Refines code based on review feedback, sandbox errors, and user rejection
feedback. Maintains memory of past fixes to avoid repeating them.
"""

from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.schemas import ReviewOutput, AnalysisOutput
from agents.memory import AgentMemory
from agents.llm_config import check_interrupts, get_llm, clean_code_output, _trimmed_invoke
from agents.action_types import ActionType, subscribe, make_action_message
from agents.artifacts import save_code_version
from database import emit_event, get_rejection_feedback, update_rejection_feedback

_code_refiner_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a refactoring specialist who fixes code based on feedback."),
    ("human", (
        "You are a Code Refiner. Your ONLY job is to output fixed, runnable Python code.\n"
        "{memory_ctx}\n"
        "{structured_review_section}\n"
        "{sandbox_section}\n"
        "{user_feedback_section}\n"
        "## Code to fix:\n"
        "```python\n"
        "{code_to_fix}\n"
        "```\n\n"
        "Rules:\n"
        "1. Fix EVERY critical issue and ALL fix suggestions listed above.\n"
        "2. Fix the sandbox error if one is shown.\n"
        "3. If user feedback is provided, address it first.\n"
        "4. If previous failed attempts are listed, do NOT repeat the same fix — try a different approach.\n"
        "5. Output ONLY a single fenced ```python … ``` block. No prose, no comments outside the block."
    )),
])


@subscribe(ActionType.DECISION_REFINE, ActionType.ANALYSIS_FIX, node_name="refine")
def code_refiner_node(state: AgentState) -> AgentState:
    """Refine code based on review feedback."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "refiner"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START refiner]"
    })
    
    # Get user rejection feedback if any
    user_feedback = get_rejection_feedback(state["task_id"])
    feedback_section = ""
    if user_feedback:
        feedback_section = (
            f"\nUser Rejection Feedback:\n{user_feedback}\n\n"
            "IMPORTANT: The user has explicitly rejected the previous code. "
            "Address their feedback above as your top priority."
        )
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"📝 User feedback received: {user_feedback[:100]}..."
        })
        # Clear feedback after reading
        update_rejection_feedback(state["task_id"], None)
    
    # ── Structured prompt (Path A) ─────────────────────────────────────────
    # When structured data is available use it directly — no LLM re-parsing
    # of prose walls of text.
    llm_states = state.get("agent_states", {})
    review_state = llm_states.get("review", {})
    test_state = llm_states.get("test", {})
    analyze_state = llm_states.get("analyze_test", {})
    gen_state = llm_states.get("generate", {})
    refine_state = llm_states.get("refine", {})
    
    ro = review_state.get("review_report_structured")
    # 'analysis_structured' usually comes from analyze_test
    ao = analyze_state.get("analysis_structured") or test_state.get("analysis_structured")

    if ro:
        review = ReviewOutput(**ro)
        critical_block = "\n".join(f"- {i}" for i in review.critical_issues) or "- None"
        suggestions_block = "\n".join(f"- {s}" for s in review.fix_suggestions) or "- None"
        score_line = f"Score: {review.overall_score}/10 | Verdict: {review.verdict}"
    else:
        # Path B fallback — raw prose
        critical_block = ""
        suggestions_block = review_state.get("review_report", "No review available.")
        score_line = ""

    if ao:
        analysis = AnalysisOutput(**ao)
        if analysis.verdict == "FIX_REQUIRED":
            hint_block = "\n".join(f"- {h}" for h in (analysis.fix_hints or [])) or "- No hints"
            error_block = (
                f"Error type : {analysis.error_type}\n"
                f"Root cause : {analysis.root_cause}\n"
                f"Hints      :\n{hint_block}"
            )
        else:
            error_block = "Sandbox: PASS — no runtime error."
    else:
        # fallback string
        analysis_str = analyze_state.get("analysis", "") or test_state.get("analysis", "No analysis available.")
        error_block = analysis_str

    # Base code: always refine from the latest refined version, not the original
    code_to_fix = refine_state.get("refined_code") or gen_state.get("generated_code", "")

    # ── Build prompt variables ──────────────────────────────────────────────
    memory_ctx = ""
    if refine_state.get("refiner_memory"):
        mem = AgentMemory(role="refiner", entries=list(refine_state["refiner_memory"]))
        memory_ctx = mem.as_system_context()

    if ro:
        structured_review_section = (
            f"## Code review ({score_line})\n\n"
            f"### Critical issues (ALL must be resolved):\n{critical_block}\n\n"
            f"### Fix suggestions:\n{suggestions_block}"
        )
    else:
        structured_review_section = f"## Review feedback:\n{suggestions_block}"

    sandbox_section = f"## Sandbox execution result:\n{error_block}"

    user_feedback_section = ""
    if user_feedback:
        user_feedback_section = f"## ⚠️ User rejection feedback (TOP PRIORITY):\n{user_feedback}"

    messages = _code_refiner_prompt.format_messages(
        memory_ctx=memory_ctx,
        structured_review_section=structured_review_section,
        sandbox_section=sandbox_section,
        user_feedback_section=user_feedback_section,
        code_to_fix=code_to_fix,
    )
    
    try:
        # Use heavy-duty model for refining
        llm = get_llm(
            for_heavy_task=True, 
            override_model=state.get("agent_models", {}).get("refiner", ""),
            base_model=state.get("model", "ollama")
        )
        response = _trimmed_invoke(llm, messages)
        refined_code = response.content
        clean_refined = clean_code_output(refined_code)
        _, version_filename = save_code_version(state["task_id"], clean_refined)
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "refiner"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END refiner]"
        })

        # Emit code_output so frontend picks up the refined version
        emit_event(state["task_id"], {
            "type": "code_output",
            "agent": "refiner",
            "code": clean_refined,
            "filename": version_filename
        })
        
        # Build memory entry summarising what was fixed
        issues_fixed = []
        if ro and ro.get("critical_issues"):
            issues_fixed.extend(ro["critical_issues"][:3])  # top 3
        if ao and ao.get("verdict") == "FIX_REQUIRED":
            issues_fixed.append(f"{ao['error_type']}: {ao['root_cause']}")
        if not issues_fixed:
            issues_fixed.append("general refinement from review feedback")
        
        iteration = state.get("debug_loop_count", 0)
        memory_entry = f"Iteration {iteration}: fixed [{', '.join(issues_fixed)}]"
        new_memory = (refine_state.get("refiner_memory") or []) + [memory_entry]
        
        refine_data = {
            "refined_code": refined_code,
            "refiner_memory": new_memory
        }
        
        # Check if analysis dictated a fix
        analysis_str = analyze_state.get("analysis", "") or test_state.get("analysis", "")
        
        return {
            "agent_states": {"refine": refine_data},
            "messages": [make_action_message(
                f"Refined code ({len(refined_code)} chars), fixed: {', '.join(issues_fixed[:2])}",
                ActionType.CODE_REFINED, "refine"
            )],
            "iteration_count": state.get("iteration_count", 0) + 1,
            # Increment debug loop count if we were triggered by the analyzer
            "debug_loop_count": (
                state.get("debug_loop_count", 0) + 1
                if "FIX_REQUIRED" in analysis_str
                else state.get("debug_loop_count", 0)
            ),
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code refinement failed: {str(e)}"
        })
        return {
            "agent_states": {"refine": {"refined_code": gen_state.get("generated_code", ""), "error": str(e)}},
            "errors": [{
                "type": "error",
                "agent": "refiner",
                "timestamp": datetime.now().isoformat(),
                "data": {"error": str(e)}
            }],
            "messages": [make_action_message(
                f"Code refinement failed: {str(e)}",
                ActionType.CODE_REFINED, "refine"
            )]
        }
