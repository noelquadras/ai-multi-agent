"""
Pure ReAct Supervisor (MetaGPT-style scaled down)

Observe → Think → Act loop.
No phases.
No nested graphs.
LLM decides everything.
"""

from typing import Literal, List, Any
from datetime import datetime
import json
import hashlib
from pydantic import BaseModel
from dataclasses import dataclass, field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from agents.state import AgentState
from agents.action_types import ActionType, make_action_message
from agents.llm_config import get_llm, check_interrupts
from database import emit_event, get_task_status, update_decision_signal


# ─────────────────────────────────────────────────────────────
# STRUCTURED PLAN OBJECT
# ─────────────────────────────────────────────────────────────

@dataclass
class TaskItem:
    task: str
    status: str = "pending"

@dataclass
class ReactPlan:
    goal: str
    tasks: List[TaskItem] = field(default_factory=list)
    current_index: int = 0

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
        return all(t.status == "completed" for t in self.tasks)


# ─────────────────────────────────────────────────────────────
# PLANNER TOOL (MetaGPT-style dynamic plan manipulation)
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



class EndWorkflow(BaseModel):
    summary: str


# ─────────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────────

_react_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an autonomous software supervisor using ReAct reasoning.\n"
     "Loop: Observe → Think → Act.\n\n"
     "You MUST call exactly one tool.\n"
     "Do NOT output conversational text.\n\n"
     "Available tools:\n"
     "- PlannerTool (manage task plan)\n"
     "- TriggerAgent (run an agent)\n"
     "- EndWorkflow\n"
     "If you lack information or are unsure, you must guess or make an autonomous decision."
    ),
    ("human",
     "Current Time: {time}\n\n"
     "Requirements:\n{requirements}\n\n"
     "Current Plan:\n{plan}\n\n"
     "Working Memory:\n{working_memory}\n\n"
     "Recent Events:\n{events}\n\n"
     "Decide next action."
    )
])


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def validate_tool_call(name: str, args: dict):
    if name == "PlannerTool":
        if "action" not in args or "task" not in args:
            raise ValueError("Invalid PlannerTool args")

    if name == "TriggerAgent":
        if "agent" not in args or "objective" not in args:
            raise ValueError("Invalid TriggerAgent args")


def classify_failure(events) -> str:
    last = str(events[-1].get("data") if hasattr(events[-1], "get") else events[-1]) if events else ""
    if "SyntaxError" in last:
        return "syntax"
    if "AssertionError" in last:
        return "logic"
    if "spec mismatch" in last.lower():
        return "spec"
    return "unknown"


def summarize_recent_events(events) -> str:
    """A simplistic summary for working memory compression."""
    if not events: return "No events."
    return f"Summarized {len(events)} events. Last event: {events[-1].get('type', 'unknown') if hasattr(events[-1], 'get') else 'unknown'}"


# ─────────────────────────────────────────────────────────────
# SUPERVISOR NODE
# ─────────────────────────────────────────────────────────────

def react_supervisor_node(state: AgentState) -> dict:
    task_id = state.get("task_id", "unknown")
    check_interrupts(task_id)

    # initialize_structures_if_missing
    budget = state.get("budget") or {
        "max_loops": 50,
        "planner_calls": 0,
        "max_planner_calls": 10,
    }
    react_plan_obj = state.get("react_plan_obj") or ReactPlan(goal="Complete task")
    working_memory = state.get("working_memory", "")
    decision_trace = state.get("decision_trace", [])
    artifact_registry = state.get("artifact_registry", {})
    last_failure_type = state.get("last_failure_type", "")
    
    events = state.get("events", [])
    recent_events = events[-6:]

    # enforce_budget
    debug_loop_count = state.get("debug_loop_count", 0)
    if debug_loop_count > budget.get("max_loops", 50):
        emit_event(task_id, {"type": "log", "message": "Max loops reached. Generating summary."})
        return {"terminate": True}
        
    if budget.get("planner_calls", 0) > budget.get("max_planner_calls", 10):
        emit_event(task_id, {"type": "log", "message": "⚠ Max planner calls budget reached — forcing agent trigger."})
        return {
            "budget": budget,
            "messages": [
                make_action_message(
                    "Forced execution due to budget",
                    ActionType.CODE_READY,
                    "react_supervisor"
                )
            ]
        }

    # compress_memory_if_needed
    if debug_loop_count > 0 and debug_loop_count % 8 == 0:
        summary = summarize_recent_events(recent_events)
        decision_trace.append(summary)
        working_memory = summary
        emit_event(task_id, {"type": "log", "message": "🧠 Compressed working memory."})

    # Human interaction overrides
    db_state = get_task_status(task_id)
    decision_signal = db_state.get("decision_signal") if db_state else None
    feedback = db_state.get("rejection_feedback") if db_state else ""
    additional_human_message = None
    if decision_signal == "APPROVED":
        emit_event(task_id, {"type": "log", "message": "👍 User approved the current progress."})
        update_decision_signal(task_id, None)
        additional_human_message = HumanMessage(content="User Notification: The user has APPROVED the current progress/code. You may proceed with the next step in the plan.")
    elif decision_signal == "REJECTED":
        reason = f" Feedback: {feedback}" if feedback else ""
        emit_event(task_id, {"type": "log", "message": f"👎 User REJECTED the current progress.{reason}"})
        update_decision_signal(task_id, None)
        additional_human_message = HumanMessage(content=f"User Notification: The user has REJECTED the current progress.{reason} Please fix the issues mentioned or rethink your approach.")

    # route_failure_if_present
    last_failure_type = classify_failure(events)
    if last_failure_type == "syntax":
        emit_event(task_id, {"type": "log", "message": "⚠ Syntax error detected — forcing coder."})
        return {"last_failure_type": "none", "messages": [make_action_message("Fix syntax", ActionType.CODE_READY, "react_supervisor")]}
    elif last_failure_type == "logic":
        emit_event(task_id, {"type": "log", "message": "⚠ Logic error detected — forcing reviewer."})
        return {"last_failure_type": "none", "messages": [make_action_message("Review logic", ActionType.REVIEW_READY, "react_supervisor")]}
    elif last_failure_type == "spec":
        last_failure_type = "none" # Handled directly by LLM

    # llm
    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("supervisor", ""),
        base_model=state.get("model", "ollama")
    )
    tools = [PlannerTool, TriggerAgent, EndWorkflow]
    llm = llm.bind_tools(tools)

    plan_summary = "\n".join(
        [f"- {p.task} ({p.status})" for p in react_plan_obj.tasks]
    ) or "No tasks yet."

    messages_to_invoke = _react_prompt.format_messages(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        requirements=state.get("requirements", ""),
        plan=plan_summary,
        working_memory=working_memory,
        events=str(recent_events)
    )

    if additional_human_message:
        messages_to_invoke.append(additional_human_message)

    response = llm.invoke(messages_to_invoke)

    # ensure_valid_tool_call
    if not getattr(response, "tool_calls", []):
        response = llm.invoke(messages_to_invoke + [HumanMessage(content="You must call one of the provided tools. Check the tool bindings.")])
        if not getattr(response, "tool_calls", []):
            emit_event(task_id, {"type": "system_error", "error": "Supervisor failed to call tool completely."})
            return {}

    tool_call = response.tool_calls[0]
    name = tool_call["name"]
    args = tool_call["args"]

    try:
        validate_tool_call(name, args)
    except Exception as e:
        emit_event(task_id, {"type": "system_error", "error": f"Invalid tool call: {e}"})
    
    emit_event(task_id, {"type": "log", "message": f"🧠 ReAct: {name}"})

    # update_meta_stability
    meta = state.get("react_meta") or {
        "last_action_hash": "",
        "repeat_count": 0,
        "planner_append_streak": 0,
        "last_triggered_agent": "",
        "plan_stagnation": 0,
        "last_plan_hash": "",
    }

    action_signature = name + json.dumps(args, sort_keys=True)
    action_hash = hashlib.md5(action_signature.encode()).hexdigest()

    if action_hash == meta["last_action_hash"]:
        meta["repeat_count"] += 1
    else:
        meta["repeat_count"] = 0

    meta["last_action_hash"] = action_hash

    if meta["repeat_count"] >= 2:
        emit_event(task_id, {"type": "log", "message": "⚠ Convergence detected — terminating."})
        return {"terminate": True, "react_meta": meta}

    if name == "TriggerAgent":
        if args.get("agent") == meta["last_triggered_agent"]:
            meta["repeat_count"] += 1
        else:
            meta["repeat_count"] = 0
        meta["last_triggered_agent"] = args.get("agent")

        if meta["repeat_count"] >= 2:
            emit_event(task_id, {"type": "log", "message": "⚠ Agent spam detected — terminating."})
            return {"terminate": True, "react_meta": meta}

    # detect_plan_stagnation
    plan_signature = hashlib.md5(
        json.dumps([(t.task, t.status) for t in react_plan_obj.tasks]).encode()
    ).hexdigest()

    if plan_signature == meta.get("last_plan_hash", ""):
        meta["plan_stagnation"] = meta.get("plan_stagnation", 0) + 1
    else:
        meta["plan_stagnation"] = 0

    meta["last_plan_hash"] = plan_signature

    if meta["plan_stagnation"] > 3:
        emit_event(task_id, {"type": "log", "message": "⚠ Plan stagnation detected — forcing reviewer."})
        meta["plan_stagnation"] = 0 
        return {
            "react_meta": meta,
            "messages": [
                make_action_message(
                    "Forced review due to plan stagnation",
                    ActionType.REVIEW_READY,
                    "react_supervisor"
                )
            ]
        }

    # execute_tool
    updates = {
        "react_meta": meta,
        "react_plan_obj": react_plan_obj,
        "budget": budget,
        "working_memory": working_memory,
        "decision_trace": decision_trace,
        "last_failure_type": last_failure_type,
        "artifact_registry": artifact_registry
    }

    if name == "PlannerTool":
        budget["planner_calls"] += 1
        if args.get("action") == "append":
            react_plan_obj.append(args["task"])
            meta["planner_append_streak"] = meta.get("planner_append_streak", 0) + 1
        else:
            meta["planner_append_streak"] = 0

        if args.get("action") == "complete":
            react_plan_obj.complete(args["task"])
        elif args.get("action") == "update":
            react_plan_obj.update(args["task"], args.get("new_status", "pending"))

        if meta.get("planner_append_streak", 0) > 3:
            emit_event(task_id, {"type": "log", "message": "⚠ Planner append spam detected — forcing agent trigger."})
            updates["messages"] = [
                make_action_message(
                    "Forced execution due to planner spam",
                    ActionType.CODE_READY,
                    "react_supervisor"
                )
            ]
            return updates

        return updates


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
                mapping[args['agent']],
                "react_supervisor"
            )
        ]
        return updates


    if name == "EndWorkflow":
        summary = args.get("summary", "Workflow completed")
        emit_event(task_id, {"type": "log", "message": f"🏁 Workflow ended: {summary}"})
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

    last_msg = messages[-1]
    sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "")

    if sender == "react_supervisor":
        action = getattr(last_msg, "additional_kwargs", {}).get("action_type")

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