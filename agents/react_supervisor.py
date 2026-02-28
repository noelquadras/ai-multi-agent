"""
Pure ReAct Supervisor (Intent-Gated Version)

Flow:
1. Classify intent (once).
2. If QUICK → direct response.
3. If AMBIGUOUS → ask clarification.
4. If TASK → continue normal ReAct loop.
"""

from typing import Literal, List
from datetime import datetime
import json
import hashlib
from dataclasses import dataclass, field
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from agents.state import AgentState
from agents.action_types import ActionType, make_action_message
from agents.llm_config import get_llm, check_interrupts
from database import emit_event


# ─────────────────────────────────────────────────────────────
# STRUCTURED PLAN
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# INTENT CLASSIFIER
# ─────────────────────────────────────────────────────────────

class IntentTool(BaseModel):
    intent: Literal["QUICK", "TASK", "AMBIGUOUS"]


def classify_intent(requirement: str, state: AgentState) -> str:
    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("supervisor", ""),
        base_model=state.get("model", "ollama"),
    ).bind_tools([IntentTool])

    response = llm.invoke(
        f"""Classify the user's request.

Return QUICK, TASK, or AMBIGUOUS.

User request:
{requirement}
"""
    )

    if not getattr(response, "tool_calls", []):
        return "TASK"

    tool_call = response.tool_calls[0]
    return tool_call["args"].get("intent", "TASK")


# ─────────────────────────────────────────────────────────────
# REACT TOOLS
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# REACT PROMPT
# ─────────────────────────────────────────────────────────────

_react_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an autonomous software supervisor using ReAct reasoning.\n"
     "You MUST call exactly one tool.\n"
     "Do NOT output text.\n"),
    ("human",
     "Time: {time}\n\n"
     "Requirements:\n{requirements}\n\n"
     "Plan:\n{plan}\n\n"
     "Recent Events:\n{events}\n\n"
     "Decide next action."
    )
])


# ─────────────────────────────────────────────────────────────
# SUPERVISOR NODE
# ─────────────────────────────────────────────────────────────

def react_supervisor_node(state: AgentState) -> dict:
    task_id = state.get("task_id", "unknown")
    check_interrupts(task_id)

    requirement = state.get("requirements", "")

    # ─── 1️⃣ INTENT GATE ─────────────────────────────────────

    intent = state.get("intent", None)

    if not intent:
        intent = classify_intent(requirement, state)
        emit_event(task_id, {"type": "log", "message": f"Intent classified: {intent}"})
        return {"intent": intent}

    # QUICK → direct answer (no agents)
    if intent == "QUICK":
        quick_llm = get_llm(
            for_heavy_task=False,
            override_model=state.get("agent_models", {}).get("supervisor", ""),
            base_model=state.get("model", "ollama"),
        ).bind_tools([QuickResponse])

        resp = quick_llm.invoke(f"Provide a direct answer to the user request. User: {requirement}")
        answer = "I've handled your request."
        if getattr(resp, "tool_calls", []):
            answer = resp.tool_calls[0]["args"].get("response", answer)
        elif resp.content:
            answer = resp.content

        return {
            "terminate": True,
            "messages": [
                make_action_message(
                    answer,
                    ActionType.DECISION_REFINE,
                    "react_supervisor"
                )
            ]
        }

    # AMBIGUOUS → request clarification
    if intent == "AMBIGUOUS":
        amb_llm = get_llm(
            for_heavy_task=False,
            override_model=state.get("agent_models", {}).get("supervisor", ""),
            base_model=state.get("model", "ollama"),
        ).bind_tools([ClarificationTool])

        resp = amb_llm.invoke(f"The user request is ambiguous. Ask for clarification. User: {requirement}")
        question = "Could you please provide more details?"
        if getattr(resp, "tool_calls", []):
            question = resp.tool_calls[0]["args"].get("question", question)
        elif resp.content:
            question = resp.content

        return {
            "terminate": True,
            "messages": [
                make_action_message(
                    question,
                    ActionType.DECISION_REFINE,
                    "react_supervisor"
                )
            ]
        }

    # Only TASK reaches here
    # ─── 2️⃣ NORMAL REACT LOOP ───────────────────────────────

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

    messages = _react_prompt.format_messages(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        requirements=requirement,
        plan=plan_summary,
        events=str(recent_events),
    )

    response = llm.invoke(messages)

    if not getattr(response, "tool_calls", []):
        emit_event(task_id, {"type": "system_error", "error": "No tool call"})
        return {}

    tool_call = response.tool_calls[0]
    name = tool_call["name"]
    args = tool_call["args"]

    updates = {
        "react_plan_obj": react_plan
    }

    # ─── PlannerTool ─────────────────────────────────────────

    if name == "PlannerTool":
        if args["action"] == "append":
            react_plan.append(args["task"])
        elif args["action"] == "complete":
            react_plan.complete(args["task"])
        elif args["action"] == "update":
            react_plan.update(args["task"], args["new_status"])

        if react_plan.is_finished():
            updates["terminate"] = True

        return updates

    # ─── TriggerAgent ────────────────────────────────────────

    if name == "TriggerAgent":
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
                f"Supervisor triggered {args['agent']}: {args['objective']}",
                mapping[args["agent"]],
                "react_supervisor",
            )
        ]
        return updates

    # ─── EndWorkflow / QuickResponse / ClarificationTool ─────

    if name == "EndWorkflow":
        updates["messages"] = [
            make_action_message(args.get("summary", "Workflow complete"), ActionType.DECISION_APPROVED, "react_supervisor")
        ]
        updates["terminate"] = True
        return updates

    if name == "QuickResponse":
        updates["messages"] = [
            make_action_message(args.get("response", ""), ActionType.DECISION_REFINE, "react_supervisor")
        ]
        updates["terminate"] = True
        return updates

    if name == "ClarificationTool":
        updates["messages"] = [
            make_action_message(args.get("question", ""), ActionType.DECISION_REFINE, "react_supervisor")
        ]
        updates["terminate"] = True
        return updates

    return updates


# ─────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────

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