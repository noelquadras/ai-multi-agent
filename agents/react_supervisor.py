"""Pure ReAct Supervisor (intent-gated).

Flow:
1. Classify intent once (structured tool call).
2. QUICK_TASK -> direct route to coder.
3. AMBIGUOUS -> ask for clarification and wait briefly.
4. CONVERSATION -> chat + wait briefly for follow-up.
5. LONG_TASK -> ReAct loop using tool calls with convergence protection.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from agents.action_types import ActionType, make_action_message
from agents.context import TaskItem
from agents.llm_config import check_interrupts, get_llm
from agents.state import AgentState
from database import emit_event, get_human_messages


# ---------------------------------------------------------------------
# Plan structure
# ---------------------------------------------------------------------


@dataclass
class ReactPlan:
    goal: str
    tasks: List[TaskItem] = field(default_factory=list)

    def append(self, task: TaskItem) -> None:
        self.tasks.append(task)

    def complete(self, task_id: str) -> None:
        for t in self.tasks:
            if t.task_id == task_id:
                t.status = "completed"
                t.updated_at = datetime.now()

    def update(self, task_id: str, new_status: str) -> None:
        for t in self.tasks:
            if t.task_id == task_id:
                t.status = new_status  # type: ignore[assignment]
                t.updated_at = datetime.now()

    def is_finished(self) -> bool:
        return len(self.tasks) > 0 and all(t.status == "completed" for t in self.tasks)

    def get_next_task(self) -> Optional[TaskItem]:
        completed_ids = {t.task_id for t in self.tasks if t.status == "completed"}
        available = [
            t
            for t in self.tasks
            if t.status == "pending" and all(dep in completed_ids for dep in t.dependencies)
        ]
        if not available:
            return None

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def sort_key(t: TaskItem):
            return (priority_order.get(t.priority, 9), t.estimated_duration or 10**9)

        return sorted(available, key=sort_key)[0]


def ensure_task_object(obj: Any) -> TaskItem:
    if isinstance(obj, TaskItem):
        return obj
    if isinstance(obj, dict):
        # Back-compat: some plans used `task` instead of `description`.
        if "description" not in obj and "task" in obj:
            obj = {**obj, "description": obj.get("task")}
        return TaskItem(**obj)
    return TaskItem(description="Complete task")


def ensure_plan_object(obj: Any) -> ReactPlan:
    if isinstance(obj, ReactPlan):
        return obj
    if isinstance(obj, dict):
        tasks = [ensure_task_object(t) for t in obj.get("tasks", [])]
        return ReactPlan(goal=obj.get("goal", ""), tasks=tasks)
    if isinstance(obj, list):
        tasks = [ensure_task_object(t) for t in obj]
        return ReactPlan(goal="", tasks=tasks)
    return ReactPlan(goal="")


# ---------------------------------------------------------------------
# Intent tool
# ---------------------------------------------------------------------


class IntentTool(BaseModel):
    intent: Literal["QUICK_TASK", "CONVERSATION", "LONG_TASK", "AMBIGUOUS"]


def classify_intent(requirement: str, state: AgentState, task_id: str) -> str:
    llm = get_llm(
        for_heavy_task=False,
        override_model=(state.get("agent_models") or {}).get("supervisor", ""),
        base_model=state.get("model", "ollama"),
    ).bind_tools([IntentTool])

    response = llm.invoke(
        "Classify the user request. Return QUICK_TASK, CONVERSATION, LONG_TASK, or AMBIGUOUS.\n\n"
        f"User:\n{requirement}\n"
    )

    if not getattr(response, "tool_calls", []):
        emit_event(task_id, {"type": "intent_error", "message": "No tool call from intent classifier."})
        return "LONG_TASK"

    try:
        return response.tool_calls[0]["args"]["intent"]
    except Exception:
        emit_event(task_id, {"type": "intent_error", "message": "Malformed intent tool call."})
        return "LONG_TASK"


# ---------------------------------------------------------------------
# ReAct tools
# ---------------------------------------------------------------------


class PlannerTool(BaseModel):
    action: Literal["append", "complete", "update", "validate", "reprioritize"]
    task: TaskItem
    new_status: Optional[Literal["pending", "in_progress", "completed"]] = None

    def validate_action(self, react_plan: ReactPlan) -> dict:
        errors: List[str] = []

        if self.action in ("complete", "update", "reprioritize"):
            if not any(t.task_id == self.task.task_id for t in react_plan.tasks):
                valid_ids = [t.task_id for t in react_plan.tasks]
                errors.append(
                    f"Task ID '{self.task.task_id}' not found. "
                    f"Valid task IDs in current plan: {valid_ids}"
                )

        if self.action == "update" and not self.new_status:
            errors.append("new_status is required for update")

        if self.action == "append":
            for dep_id in self.task.dependencies:
                if not any(t.task_id == dep_id for t in react_plan.tasks):
                    errors.append(f"Dependency task {dep_id} not found")

        if self.task.estimated_duration and self.task.estimated_duration > 120:
            errors.append("Estimated duration exceeds 2 hours")

        return {"is_valid": len(errors) == 0, "errors": errors, "task_id": self.task.task_id}


class TriggerAgent(BaseModel):
    agent: Literal["spec_writer", "coder", "reviewer", "refiner", "tester", "analyzer"]
    objective: str
    context: Optional[dict] = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    estimated_duration: Optional[int] = None
    dependencies: List[str] = Field(default_factory=list)


class QuickResponse(BaseModel):
    response: str


class ClarificationTool(BaseModel):
    question: str


class EndWorkflow(BaseModel):
    summary: str


# ---------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------


_react_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an autonomous software supervisor. You MUST call exactly one tool. Do NOT output text.\n"
            "IMPORTANT RULES:\n"
            "1. Task IDs are auto-generated. When you see '[id=xxx]' in the plan, use that EXACT id for update/complete/reprioritize.\n"
            "2. Do NOT invent task IDs. Always reference IDs from the plan.\n"
            "3. After appending tasks, move on - call TriggerAgent to execute work. Do NOT keep re-appending or updating.\n"
            "4. If a task is already completed, do not update it again.\n",
        ),
        (
            "human",
            "Time: {time}\n\nRequirement:\n{requirements}\n\nPlan:\n{plan}\n\nRecent Events:\n{events}\n\nDecide next action.",
        ),
    ]
)


# ---------------------------------------------------------------------
# Supervisor node
# ---------------------------------------------------------------------


def react_supervisor_node(state: AgentState) -> dict:
    task_id = state.get("task_id", "unknown")
    check_interrupts(task_id)

    requirement = state.get("requirements", "")
    intent = state.get("intent")

    # Intent gate (set once)
    if not intent:
        intent = classify_intent(requirement, state, task_id)
        emit_event(task_id, {"type": "log", "message": f"Intent: {intent}"})
        return {"intent": intent}

    if intent == "QUICK_TASK":
        if state.get("quick_task_done"):
            emit_event(task_id, {"type": "log", "message": "Quick task complete."})
            return {"terminate": True}

        emit_event(task_id, {"type": "log", "message": "Quick task - sending directly to coder."})
        return {
            "quick_task_done": True,
            "messages": [
                make_action_message(
                    f"Quick task: {requirement}",
                    ActionType.CODE_READY,
                    "react_supervisor",
                )
            ],
        }

    if intent == "AMBIGUOUS":
        clarify_llm = get_llm(
            for_heavy_task=False,
            override_model=(state.get("agent_models") or {}).get("supervisor", ""),
            base_model=state.get("model", "ollama"),
        )
        clarify_resp = clarify_llm.invoke(
            "The following user request is ambiguous. Write a short, friendly clarification question (1-2 sentences) "
            "to help understand what they need.\n\n"
            f"User request:\n{requirement}"
        )
        question = getattr(clarify_resp, "content", "Could you please clarify your request?")

        emit_event(task_id, {"type": "clarification", "message": question})

        max_wait = 120
        poll_interval = 3
        waited = 0
        while waited < max_wait:
            check_interrupts(task_id)
            human_msgs = get_human_messages(task_id, mark_consumed=True)
            if human_msgs:
                user_reply = human_msgs[-1]["message"]
                emit_event(task_id, {"type": "log", "message": f"Received clarification: {user_reply}"})
                return {"requirements": f"{requirement}\n\nUser clarification: {user_reply}", "intent": None}
            time.sleep(poll_interval)
            waited += poll_interval

        emit_event(task_id, {"type": "log", "message": "No clarification received - ending."})
        return {"terminate": True}

    if intent == "CONVERSATION":
        chat_llm = get_llm(
            for_heavy_task=False,
            override_model=(state.get("agent_models") or {}).get("supervisor", ""),
            base_model=state.get("model", "ollama"),
        )
        chat_resp = chat_llm.invoke(
            "You are a helpful AI assistant. Have a natural conversation with the user. Keep your reply concise and friendly.\n\n"
            f"User:\n{requirement}"
        )
        reply = getattr(chat_resp, "content", "I'm here to help! Could you tell me more?")

        emit_event(task_id, {"type": "conversation", "message": reply})

        max_wait = 120
        poll_interval = 3
        waited = 0
        while waited < max_wait:
            check_interrupts(task_id)
            human_msgs = get_human_messages(task_id, mark_consumed=True)
            if human_msgs:
                user_reply = human_msgs[-1]["message"]
                emit_event(task_id, {"type": "log", "message": f"User said: {user_reply}"})
                return {
                    "requirements": f"{requirement}\n\nAssistant: {reply}\n\nUser: {user_reply}",
                    "intent": None,
                }
            time.sleep(poll_interval)
            waited += poll_interval

        emit_event(task_id, {"type": "log", "message": "Conversation timed out - ending."})
        return {"terminate": True}

    # LONG_TASK -> ReAct loop
    react_plan = ensure_plan_object(state.get("react_plan_obj") or state.get("react_plan"))
    events = state.get("events", [])
    recent_events = list(events[-6:])

    human_msgs = get_human_messages(task_id, mark_consumed=True)
    for hm in human_msgs:
        recent_events.append({"type": "human_message", "message": hm["message"]})
        emit_event(task_id, {"type": "log", "message": f"Read human message: {hm['message']}"})

    llm = get_llm(
        for_heavy_task=False,
        override_model=(state.get("agent_models") or {}).get("supervisor", ""),
        base_model=state.get("model", "ollama"),
    ).bind_tools([PlannerTool, TriggerAgent, EndWorkflow, QuickResponse, ClarificationTool])

    plan_summary = "\n".join(
        f"- [id={t.task_id}] {t.description} [{t.status}] (priority={t.priority})" for t in react_plan.tasks
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

    # Convergence protection
    meta = state.get("react_meta") or {"last_hash": "", "repeat": 0, "consecutive_errors": 0}
    if "consecutive_errors" not in meta:
        meta["consecutive_errors"] = 0
    signature = name + json.dumps(args, sort_keys=True)
    current_hash = hashlib.md5(signature.encode()).hexdigest()
    if current_hash == meta["last_hash"]:
        meta["repeat"] += 1
    else:
        meta["repeat"] = 0
    meta["last_hash"] = current_hash
    if meta["repeat"] >= 2:
        emit_event(task_id, {"type": "log", "message": "Convergence detected (identical calls)."})
        return {"terminate": True}
    if meta["consecutive_errors"] >= 3:
        emit_event(task_id, {"type": "log", "message": "Too many consecutive validation errors - breaking loop."})
        return {"terminate": True}

    updates: Dict[str, Any] = {"react_plan_obj": react_plan, "react_meta": meta}

    try:
        if name == "PlannerTool":
            # Ensure nested 'task' dict has a 'description' to avoid hard ValidationError
            if isinstance(args.get("task"), dict) and "description" not in args["task"]:
                args["task"]["description"] = args["task"].get("task", "Complete task")

            try:
                validated = PlannerTool(**args)
            except ValidationError as ve:
                emit_event(
                    task_id,
                    {"type": "tool_validation_error", "tool": "PlannerTool", "errors": [str(ve)]},
                )
                return updates

            validation_result = validated.validate_action(react_plan)
            if not validation_result["is_valid"]:
                meta["consecutive_errors"] = meta.get("consecutive_errors", 0) + 1
                emit_event(
                    task_id,
                    {
                        "type": "tool_validation_error",
                        "tool": "PlannerTool",
                        "errors": validation_result["errors"],
                    },
                )
                updates["react_meta"] = meta
                return updates

            # Reset error counter on successful action
            meta["consecutive_errors"] = 0

            if validated.action == "append":
                react_plan.append(validated.task)
                emit_event(
                    task_id,
                    {
                        "type": "task_appended",
                        "task_id": validated.task.task_id,
                        "description": validated.task.description,
                    },
                )
            elif validated.action == "complete":
                react_plan.complete(validated.task.task_id)
                emit_event(task_id, {"type": "task_completed", "task_id": validated.task.task_id})
            elif validated.action == "update":
                react_plan.update(validated.task.task_id, validated.new_status or "pending")
                emit_event(
                    task_id,
                    {
                        "type": "task_updated",
                        "task_id": validated.task.task_id,
                        "new_status": validated.new_status,
                    },
                )
            elif validated.action == "reprioritize":
                for t in react_plan.tasks:
                    if t.task_id == validated.task.task_id:
                        t.priority = validated.task.priority
                        t.updated_at = datetime.now()
                emit_event(
                    task_id,
                    {
                        "type": "task_reprioritized",
                        "task_id": validated.task.task_id,
                        "new_priority": validated.task.priority,
                    },
                )
            elif validated.action == "validate":
                updates["validation_result"] = validation_result
                return updates

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
            summary = args.get("summary", "")
            if summary:
                emit_event(task_id, {"type": "log", "message": f"Workflow ended: {summary}"})
            return updates

        if name == "QuickResponse":
            updates["terminate"] = True
            updates["messages"] = [
                make_action_message(
                    args.get("response", ""),
                    ActionType.DECISION_REFINE,
                    "react_supervisor",
                )
            ]
            return updates

        if name == "ClarificationTool":
            updates["terminate"] = True
            updates["messages"] = [
                make_action_message(
                    args.get("question", ""),
                    ActionType.DECISION_REFINE,
                    "react_supervisor",
                )
            ]
            return updates

    except ValidationError:
        emit_event(task_id, {"type": "tool_validation_error", "tool": name})
        return {"terminate": True}

    return updates


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
