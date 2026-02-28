"""
Pure ReAct Supervisor (Stable Intent-Gated Version)

Flow:
1. Classify intent (once, structured).
2. QUICK_TASK → direct response.
3. AMBIGUOUS → clarification.
4. LONG_TASK → ReAct loop.
5. Convergence + spam protection enabled.
"""

from typing import Literal, List
from datetime import datetime
import hashlib
import json
from dataclasses import dataclass, field
from pydantic import BaseModel, ValidationError
from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.action_types import ActionType, make_action_message
from agents.llm_config import get_llm, check_interrupts
from database import emit_event


# ─────────────────────────────────────────────
# PLAN STRUCTURE
# ─────────────────────────────────────────────

@dataclass
class TaskItem:
    task: str
    status: str = "pending"


@dataclass
class ReactPlan:
    goal: str
    tasks: List[TaskItem] = field(default_factory=list)

    def append(self, task: str):
        self.tasks.append(TaskItem(task=task))

    def complete(self, task: str):
        for t in self.tasks:
            if t.task == task:
                t.status = "completed"

    def update(self, task: str, new_status: str):
        for t in self.tasks:
            if t.task == task:
                t.status = new_status

    def is_finished(self):
        return len(self.tasks) > 0 and all(t.status == "completed" for t in self.tasks)


def ensure_plan_object(obj):
    if isinstance(obj, ReactPlan):
        return obj
    if isinstance(obj, dict):
        return ReactPlan(
            goal=obj.get("goal", ""),
            tasks=[TaskItem(**t) for t in obj.get("tasks", [])],
        )
    return ReactPlan(goal="Complete task")


# ─────────────────────────────────────────────
# INTENT TOOL
# ─────────────────────────────────────────────

class IntentTool(BaseModel):
    intent: Literal["QUICK_TASK", "CONVERSATION", "LONG_TASK", "AMBIGUOUS"]


def classify_intent(requirement: str, state: AgentState, task_id: str) -> str:
    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("supervisor", ""),
        base_model=state.get("model", "ollama"),
    ).bind_tools([IntentTool])

    response = llm.invoke(
        f"""Classify the user request.

Return QUICK_TASK, CONVERSATION, LONG_TASK, or AMBIGUOUS.

User:
{requirement}
"""
    )

    if not getattr(response, "tool_calls", []):
        emit_event(task_id, {"type": "intent_error", "message": "No tool call from intent classifier."})
        return "LONG_TASK"

    try:
        return response.tool_calls[0]["args"]["intent"]
    except Exception:
        emit_event(task_id, {"type": "intent_error", "message": "Malformed intent tool call."})
        return "LONG_TASK"


# ─────────────────────────────────────────────
# REACT TOOLS
# ─────────────────────────────────────────────

class PlannerTool(BaseModel):
    action: Literal["append", "complete", "update"]
    task: str
    new_status: Literal["pending", "in_progress", "completed"] = "pending"


class TriggerAgent(BaseModel):
    agent: Literal[
        "spec_writer",
        "coder",
        "reviewer",
        "refiner",
        "tester",
        "analyzer"
    ]
    objective: str


class QuickResponse(BaseModel):
    response: str


class ClarificationTool(BaseModel):
    question: str


class EndWorkflow(BaseModel):
    summary: str


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

_react_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an autonomous software supervisor.\n"
     "You MUST call exactly one tool.\n"
     "Do NOT output text."),
    ("human",
     "Time: {time}\n\n"
     "Requirement:\n{requirements}\n\n"
     "Plan:\n{plan}\n\n"
     "Recent Events:\n{events}\n\n"
     "Decide next action.")
])


# ─────────────────────────────────────────────
# SUPERVISOR NODE
# ─────────────────────────────────────────────

def react_supervisor_node(state: AgentState) -> dict:
    task_id = state.get("task_id", "unknown")
    check_interrupts(task_id)

    requirement = state.get("requirements", "")
    intent = state.get("intent")

    # ─── INTENT GATE ─────────────────────────

    if not intent:
        intent = classify_intent(requirement, state, task_id)
        emit_event(task_id, {"type": "log", "message": f"Intent: {intent}"})
        return {"intent": intent}

    if intent == "QUICK_TASK":
        return {
            "terminate": True,
            # "messages": [
            #     make_action_message(
            #         requirement,
            #         ActionType.DECISION_REFINE,
            #         "react_supervisor"
            #     )
            # ]
        }

    if intent == "AMBIGUOUS":
        return {
            "terminate": True,
            # "messages": [
            #     make_action_message(
            #         "Please clarify your request.",
            #         ActionType.DECISION_REFINE,
            #         "react_supervisor"
            #     )
            # ]
        }

    if intent == "CONVERSATION":
        return {
            "terminate": True,
            # "messages": [
            #     make_action_message(
            #         requirement,
            #         ActionType.DECISION_REFINE,
            #         "react_supervisor"
            #     )
            # ]
        }

    # ─── LONG_TASK → REACT LOOP ───────────────────

    react_plan = ensure_plan_object(state.get("react_plan_obj"))
    events = state.get("events", [])
    recent_events = events[-6:]

    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("supervisor", ""),
        base_model=state.get("model", "ollama"),
    ).bind_tools([PlannerTool, TriggerAgent, EndWorkflow, QuickResponse, ClarificationTool])

    plan_summary = "\n".join(
        f"- {t.task} ({t.status})" for t in react_plan.tasks
    ) or "No tasks yet."

    response = llm.invoke(
        _react_prompt.format_messages(
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            requirements=requirement,
            plan=plan_summary,
            events=str(recent_events),
        )
    )

    if not getattr(response, "tool_calls", []):
        emit_event(task_id, {"type": "system_error", "error": "Supervisor produced no tool call."})
        return {"terminate": True}

    tool_call = response.tool_calls[0]
    name = tool_call["name"]
    args = tool_call["args"]

    emit_event(task_id, {"type": "tool_call", "name": name, "args": args})

    # ─── CONVERGENCE PROTECTION ──────────────

    meta = state.get("react_meta") or {"last_hash": "", "repeat": 0}

    signature = name + json.dumps(args, sort_keys=True)
    current_hash = hashlib.md5(signature.encode()).hexdigest()

    if current_hash == meta["last_hash"]:
        meta["repeat"] += 1
    else:
        meta["repeat"] = 0

    meta["last_hash"] = current_hash

    if meta["repeat"] >= 2:
        emit_event(task_id, {"type": "log", "message": "Convergence detected."})
        return {"terminate": True}

    updates = {"react_plan_obj": react_plan, "react_meta": meta}

    # ─── TOOL EXECUTION ──────────────────────

    try:
        if name == "PlannerTool":
            validated = PlannerTool(**args)

            if validated.action == "append":
                react_plan.append(validated.task)
            elif validated.action == "complete":
                react_plan.complete(validated.task)
            elif validated.action == "update":
                react_plan.update(validated.task, validated.new_status)

            if react_plan.is_finished():
                updates["terminate"] = True

            return updates

        if name == "TriggerAgent":
            validated = TriggerAgent(**args)

            mapping = {
                "spec_writer": ActionType.PRD_READY,
                "coder": ActionType.CODE_READY,
                "reviewer": ActionType.REVIEW_READY,
                "refiner": ActionType.DECISION_REFINE,
                "tester": ActionType.TEST_COMPLETE,
                "analyzer": ActionType.ANALYSIS_REGENERATE,
            }

            updates["messages"] = [
                make_action_message(
                    f"Supervisor triggered {validated.agent}: {validated.objective}",
                    mapping[validated.agent],
                    "react_supervisor",
                )
            ]
            return updates

        if name == "EndWorkflow":
            updates["terminate"] = True
            return updates

        if name == "QuickResponse":
            updates["terminate"] = True
            updates["messages"] = [
                make_action_message(args.get("response", ""), ActionType.DECISION_REFINE, "react_supervisor")
            ]
            return updates

        if name == "ClarificationTool":
            updates["terminate"] = True
            updates["messages"] = [
                make_action_message(args.get("question", ""), ActionType.DECISION_REFINE, "react_supervisor")
            ]
            return updates

    except ValidationError:
        emit_event(task_id, {"type": "tool_validation_error", "tool": name})
        return {"terminate": True}

    return updates


# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────

def react_supervisor_router(state: AgentState):
    from langgraph.graph import END

    if state.get("terminate"):
        return END

    messages = state.get("messages", [])
    if not messages:
        return "supervisor"

    last = messages[-1]
    sender = getattr(last, "additional_kwargs", {}).get("sender", "")
    action = getattr(last, "additional_kwargs", {}).get("action_type")

    if sender == "react_supervisor":
        mapping = {
            str(ActionType.PRD_READY): "spec_writer",
            str(ActionType.CODE_READY): "coder",
            str(ActionType.REVIEW_READY): "reviewer",
            str(ActionType.DECISION_REFINE): "refiner",
            str(ActionType.TEST_COMPLETE): "tester",
            str(ActionType.ANALYSIS_REGENERATE): "analyzer",
        }
        return mapping.get(action, "supervisor")

    return "supervisor"