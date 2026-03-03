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
        
        # Parse structured output, fall back to raw string
        review_output_dict = None
        try:
            result: ReviewOutput = structured_llm.invoke(messages)
            review_output_dict = result.model_dump()
            review = result.model_dump_json(indent=2)  # pretty JSON for SSE display
        except Exception:
            # Fallback: with_structured_output failed, try raw invoke
            response = _trimmed_invoke(llm, messages)
            review = response.content
        
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
        })

        review_summary = f"Review: score={review_output_dict['overall_score']}/10, verdict={review_output_dict['verdict']}" if review_output_dict else f"Review: {len(review)} chars (raw)"
        
        review_data = {
            "review_report": review,
            "review_report_structured": review_output_dict
        }
        
        return {
            "agent_states": {"review": review_data},
            "messages": [make_action_message(review_summary, ActionType.REVIEW_READY, "review")],
            "iteration_count": state.get("iteration_count", 0) + 1,
            "confidence_score": (review_output_dict.get("overall_score", 0) / 10.0) if review_output_dict else 0.5
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
