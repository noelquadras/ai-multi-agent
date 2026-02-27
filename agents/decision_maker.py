"""
NODE 3: DECISION MAKER

Decides if code needs refinement. Uses a deterministic path when structured
review data is available; falls back to LLM only when needed.
"""

from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.schemas import ReviewOutput, DecisionOutput
from agents.llm_config import check_interrupts, get_llm, _trimmed_invoke
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event, get_task_status, update_decision_signal

_decision_maker_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a deterministic decision auditor."),
    ("human", (
        "Analyze ONLY the code below:\n\n"
        "{generated_code}\n\n"
        "Question: Does the code have bugs, security vulnerabilities, or incorrect behavior?\n"
        "Answer YES if it needs refinement, NO if it is good enough."
    )),
])


# ── Thin verdict → action_type wrapper ──────────────────────────────────
def _decision_to_action(decision: str) -> ActionType:
    """Map a YES/NO decision verdict to the corresponding action type.
    Routing logic lives here, NOT inside the LLM prompt."""
    if "YES" in decision:
        return ActionType.DECISION_REFINE
    return ActionType.DECISION_APPROVED


@subscribe(ActionType.REVIEW_READY, node_name="decide")
def decision_maker_node(state: AgentState) -> AgentState:
    """
    Decide if code needs refinement.
    
    Deterministic path: if structured review data is available, reads
    review.verdict directly — no LLM call needed.
    Fallback: calls the LLM only when structured review data is missing.
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "decision"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START decision]"
    })
    
    try:
        # 1. Check for Manual Override Signal (Approve/Reject from UI)
        db_state = get_task_status(state["task_id"])
        decision_signal = db_state.get("decision_signal") if db_state else None
        
        decision_output_dict = None
        
        llm_states = state.get("agent_states", {})
        review_state = llm_states.get("review", {})
        gen_state = llm_states.get("generate", {})
        
        if decision_signal == "APPROVED":
            decision = "NO"
            rationale = "Human override: APPROVED"
            emit_event(state["task_id"], {
                "type": "log",
                "message": "🚦 Human Signal: APPROVED (Skipping Refinement)"
            })
            update_decision_signal(state["task_id"], None)
            
        elif decision_signal == "REJECTED":
            decision = "YES"
            rationale = "Human override: REJECTED"
            emit_event(state["task_id"], {
                "type": "log",
                "message": "🚦 Human Signal: REJECTED (Forcing Refinement)"
            })
            update_decision_signal(state["task_id"], None)
            
        elif review_state.get("review_report_structured"):
            # 2. Deterministic decision from structured review — NO LLM call
            # review = ReviewOutput(**review_state["review_report_structured"])
            # decision = "YES" if review.verdict == "NEEDS_REFINE" else "NO"
            review = ReviewOutput(**review_state["review_report_structured"])
            make_iterations = state.get("make_iterations", 0)
            score = review.overall_score
            critical_count = len(review.critical_issues)

            # Practical approval policy
            if critical_count > 0:
                decision = "YES"
            elif score >= 7:
                decision = "NO"
            elif make_iterations >= 2:
                decision = "NO"
            else:
                decision = "YES"

            rationale = (f"Deterministic: verdict={review.verdict}, "
                         f"score={review.overall_score}/10, "
                         f"{len(review.critical_issues)} critical issue(s)")
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"⚡ Deterministic decision from structured review (no LLM call)"
            })
        else:
            # 3. Fallback: LLM decision with structured output
            messages = _decision_maker_prompt.format_messages(
                generated_code=gen_state.get("generated_code", "")
            )
            llm = get_llm(
                for_heavy_task=False, 
                override_model=state.get("agent_models", {}).get("decision", ""),
                base_model=state.get("model", "ollama")
            )
            structured_llm = llm.with_structured_output(DecisionOutput)
            
            try:
                result: DecisionOutput = structured_llm.invoke(messages)
                decision = result.decision
                rationale = result.rationale
                decision_output_dict = result.model_dump()
            except Exception:
                # Fallback: structured output failed, try raw invoke
                response = _trimmed_invoke(llm, messages)
                decision = response.content.strip().upper()
                rationale = "Parsed from raw LLM output"
        
        # Normalise to YES / NO
        if "YES" in decision:
            decision = "YES"
        elif "NO" in decision:
            decision = "NO"
        else:
            decision = "YES"  # Default to refinement if unclear
        
        # Build decision_output_dict if not already set
        if decision_output_dict is None:
            decision_output_dict = DecisionOutput(
                decision=decision,
                rationale=rationale
            ).model_dump()
        
        # ── Mutate execution_plan IN MAKE ────────────────────────────
        import copy
        exec_plan = copy.deepcopy(state.get("execution_plan", []))
        
        for step in exec_plan:
            if step["phase"] == "MAKE":
                if decision == "NO":
                    step["status"] = "completed"
                else:
                    step["status"] = "in_progress"
                break
                
        # ── Thin wrapper: verdict → action_type ────────────────────────────
        action = _decision_to_action(decision)

        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Decision: {decision} → {action} — {rationale}"
        })

        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "decision"
        })

        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END decision]"
        })

        decide_data = {
            "decision": decision,
            "decision_output": decision_output_dict
        }

        result_state = {
            "agent_states": {"decide": decide_data},
            "messages": [make_action_message(
                f"{decision}: {rationale}", action, "decide"
            )],
            "iteration_count": state.get("iteration_count", 0) + 1,
            "execution_plan": exec_plan
        }
        
        if decision == "YES":
            result_state["make_iterations"] = state.get("make_iterations", 0) + 1
            
        return result_state
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Decision making failed: {str(e)}"
        })
        return {
            "agent_states": {"decide": {"decision": "YES", "error": str(e)}},
            "errors": [{
                "type": "error",
                "agent": "decision",
                "timestamp": datetime.now().isoformat(),
                "data": {"error": str(e)}
            }],
            "messages": [make_action_message(
                f"Decision making failed: {str(e)}",
                ActionType.DECISION_REFINE, "decide"
            )]
        }
