"""
NODE 2: CODE REVIEWER

Reviews generated code for security, bugs, and best practices
using structured Pydantic output.
"""

from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.schemas import ReviewOutput
from agents.artifacts import save_json_artifact, save_artifact
from agents.llm_config import check_interrupts, get_llm, _trimmed_invoke
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event


def _format_review_output(review: ReviewOutput) -> str:
    """Format a ReviewOutput into a human-readable markdown string."""
    lines = []
    lines.append(f"### Verdict: {review.verdict}  (Score: {review.overall_score}/10)")
    if review.critical_issues:
        lines.append("\n### Critical Issues")
        for issue in review.critical_issues:
            lines.append(f"- ❌ {issue}")
    if review.minor_issues:
        lines.append("\n### Minor Issues")
        for issue in review.minor_issues:
            lines.append(f"- ⚠️ {issue}")
    if review.fix_suggestions:
        lines.append("\n### Fix Suggestions")
        for suggestion in review.fix_suggestions:
            lines.append(f"- 🔧 {suggestion}")
    return "\n".join(lines)


_code_reviewer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a meticulous code reviewer focused on security, bugs, and best practices."),
    ("human", (
        "You are an Expert QA and Security Auditor.\n"
        "Review the following code critically:\n\n"
        "{generated_code}\n\n"
        "DO NOT write code. DO NOT rewrite the solution."
    )),
])


@subscribe(ActionType.CODE_READY, node_name="review")
def code_reviewer_node(state: AgentState) -> AgentState:
    """Review generated code for issues using structured Pydantic output."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "reviewer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START reviewer]"
    })
    
    llm_states = state.get("agent_states", {})
    gen_state = llm_states.get("generate", {})
    generated_code = gen_state.get("generated_code", "")
    
    messages = _code_reviewer_prompt.format_messages(generated_code=generated_code)
    
    try:
        llm = get_llm(
            for_heavy_task=False, 
            override_model=state.get("agent_models", {}).get("reviewer", ""),
            base_model=state.get("model", "ollama")
        )
        structured_llm = llm.with_structured_output(ReviewOutput)

        # ── Streaming pass: show tokens in real-time ─────────────────────
        from database import broadcast_event
        accumulated_text = ""
        try:
            for chunk in llm.stream(messages):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    accumulated_text += token
                    broadcast_event(state["task_id"], {
                        "type": "review_stream",
                        "agent": "reviewer",
                        "chunk": token,
                        "done": False,
                    })
            # Signal stream end
            broadcast_event(state["task_id"], {
                "type": "review_stream",
                "agent": "reviewer",
                "chunk": "",
                "done": True,
            })
        except Exception as stream_err:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Review streaming failed, falling back to invoke: {stream_err}"
            })
            if not accumulated_text:
                response = _trimmed_invoke(llm, messages)
                accumulated_text = response.content

        # ── Structured parse pass ────────────────────────────────────────
        # Parse structured output, fall back to raw string
        review_output_dict = None
        try:
            result: ReviewOutput = structured_llm.invoke(messages)
            review_output_dict = result.model_dump()
            review = result.model_dump_json(indent=2)  # pretty JSON for SSE display
        except Exception:
            # Fallback: with_structured_output failed, use accumulated text
            review = accumulated_text
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Review completed: {len(review)} characters"
                       + (f" (structured, score={review_output_dict['overall_score']})"
                          if review_output_dict else " (raw)")
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "reviewer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END reviewer]"
        })
        
        # Persist review artifact
        n = state.get("iteration_count", 0)
        if review_output_dict:
            save_json_artifact(state["task_id"], f"reviews/review_{n:03d}.json", review_output_dict)
        else:
            save_artifact(state["task_id"], f"reviews/review_{n:03d}.txt", review)
        
        # Build a human-readable review for the frontend
        if review_output_dict:
            review_display = _format_review_output(ReviewOutput(**review_output_dict))
        else:
            review_display = review
        
        # Save as latest (overwrite to keep only the newest)
        save_artifact(state["task_id"], "reviews/review_latest.md", review_display)

        emit_event(state["task_id"], {
            "type": "review_output",
            "agent": "reviewer",
            "review": review_display,
            "filename": "review.md"
        })

        review_data = {
            "review_report": review,
            "review_report_structured": review_output_dict
        }
        
        # Route directly to refiner when structured verdict says NEEDS_REFINE;
        # otherwise surface to supervisor as REVIEW_READY (approve / raw fallback).
        verdict = (review_output_dict or {}).get("verdict", "APPROVE")
        if verdict == "NEEDS_REFINE":
            next_action = ActionType.DECISION_REFINE
            review_summary = (
                f"Review NEEDS_REFINE — score={review_output_dict['overall_score']}/10, "
                f"{len(review_output_dict.get('critical_issues', []))} critical issues → calling refiner"
            )
            # ── MARKER: refiner_needed ────────────────────────────────────────────
            # Raised here; cleared only after code_refiner_node completes.
            emit_event(state["task_id"], {
                "type": "refiner_needed",
                "message": "Review verdict is NEEDS_REFINE. code_refiner MUST be called before ending.",
                "critical_issues": (review_output_dict or {}).get("critical_issues", []),
                "score": (review_output_dict or {}).get("overall_score"),
            })
            refiner_needed_flag = True
        else:
            next_action = ActionType.REVIEW_READY
            review_summary = (
                f"Review APPROVED — score={review_output_dict['overall_score']}/10"
                if review_output_dict
                else f"Review: {len(review)} chars (raw)"
            )
            refiner_needed_flag = False
        
        return {
            "agent_states": {"review": review_data},
            "messages": [make_action_message(review_summary, next_action, "review")],
            "iteration_count": state.get("iteration_count", 0) + 1,
            "confidence_score": (review_output_dict.get("overall_score", 0) / 10.0) if review_output_dict else 0.5,
            # ── MARKERS ─────────────────────────────────────────────────────────────────
            "refiner_needed": refiner_needed_flag,  # True = refiner must run
            "refiner_done": False,                  # reset: new review cycle
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code review failed: {str(e)}"
        })
        return {
            "errors": [{
                "type": "error",
                "agent": "reviewer",
                "timestamp": datetime.now().isoformat(),
                "data": {"error": str(e)}
            }],
            "messages": [make_action_message(
                f"Code review failed: {str(e)}",
                ActionType.REVIEW_READY, "review"
            )]
        }
