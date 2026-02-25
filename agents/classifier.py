"""
Task Classification Node.
Analyzes requirements to determine complexity and required execution path.
"""

from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from agents.state import AgentState, TaskProfile
from agents.action_types import ActionType, make_action_message
from agents.llm_config import get_llm
from database import emit_event


class TaskProfileOutput(BaseModel):
    """Structured output for task classification."""
    complexity: Literal["trivial", "standard", "complex"] = Field(
        description="Complexity level of the task."
    )
    needs_spec: bool = Field(
        description="Whether a technical specification (PRD) is required."
    )
    needs_review: bool = Field(
        description="Whether a code review is required."
    )
    needs_docs: bool = Field(
        description="Whether documentation is required."
    )
    needs_testing: bool = Field(
        description="Whether automated testing is required."
    )
    rationale: str = Field(
        description="Brief reasoning for this classification."
    )


_classifier_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert software architect. Analyze the user requirements and determine the optimal, minimal execution path.\n\n"
     "CRITICAL: You must provide your output as a structured tool call. \n"
     "All boolean fields (needs_spec, needs_review, needs_docs, needs_testing) MUST be JSON booleans: use 'true' or 'false' (without quotes). \n"
     "DO NOT use strings like \"true\" or \"false\".\n\n"
     "Classification Criteria:\n"
     "1. TRIVIAL:\n"
     "   - Single-file request, no architecture design, no persistence.\n"
     "   - No external APIs, clear output format.\n"
     "   - Example: 'print hello world', 'reverse a string'.\n"
     "   - Flags: needs_spec=false, needs_review=false, needs_docs=false.\n\n"
     "2. STANDARD:\n"
     "   - Moderate logic, possible edge cases.\n"
     "   - Small system but not architectural.\n"
     "   - Example: CLI app, CRUD logic, small API.\n"
     "   - Flags: needs_review=true, needs_testing=true, needs_spec=false (usually).\n\n"
     "3. COMPLEX:\n"
     "   - Multi-module, architecture design, concurrency, security-sensitive.\n"
     "   - External integrations.\n"
     "   - Example: 'REST API with Auth and DB', 'Distributed worker system', 'Gaming applications with logic and UI'.\n"
     "   - Flags: All true."),
    ("human", "Requirements: {requirements}")
])


def classify_task_node(state: AgentState) -> dict:
    """
    Analyzes task requirements and profiles the complexity.
    """
    task_id = state.get("task_id", "unknown")
    requirements = state.get("requirements", "")

    emit_event(task_id, {
        "type": "log",
        "message": "🔍 Classifier: Analyzing task complexity..."
    })

    try:
        llm = get_llm(
            for_heavy_task=False, 
            base_model=state.get("model", "ollama")
        )
        structured_llm = llm.with_structured_output(TaskProfileOutput)

        profile_output: TaskProfileOutput = structured_llm.invoke(
            _classifier_prompt.format_messages(requirements=requirements)
        )

        profile: TaskProfile = profile_output.model_dump()

        emit_event(task_id, {
            "type": "task_classified",
            "profile": profile
        })

        emit_event(task_id, {
            "type": "log",
            "message": f"🔍 Classifier: {profile['complexity'].upper()} — {profile['rationale']}"
        })

        # Return state update
        return {
            "task_profile": profile,
            "messages": [
                make_action_message(
                    content=f"Task classified as {profile['complexity']}. Rationale: {profile['rationale']}",
                    action_type=ActionType.TASK_CLASSIFIED,
                    sender="classifier"
                )
            ]
        }

    except Exception as e:
        emit_event(task_id, {
            "type": "log",
            "message": f"❌ Classifier Error: {str(e)}. Falling back to 'standard'."
        })
        fallback_profile: TaskProfile = {
            "complexity": "standard",
            "needs_spec": False,
            "needs_review": True,
            "needs_docs": False,
            "needs_testing": True,
            "rationale": f"Classifier failed: {str(e)}"
        }
        return {
            "task_profile": fallback_profile,
            "messages": [
                make_action_message(
                    content="Task classification failed, using fallback 'standard' profile.",
                    action_type=ActionType.TASK_CLASSIFIED,
                    sender="classifier"
                )
            ]
        }
