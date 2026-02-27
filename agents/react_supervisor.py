"""
Pure ReAct Supervisor (MetaGPT-style scaled down)

Observe → Think → Act loop.
No phases.
No nested graphs.
LLM decides everything.
"""

from typing import Literal, List
from datetime import datetime
import json
import hashlib
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from agents.state import AgentState
from agents.action_types import ActionType, make_action_message
from agents.llm_config import get_llm
from database import emit_event


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
     "Recent Events:\n{events}\n\n"
     "Decide next action."
    )
])


# ─────────────────────────────────────────────────────────────
# SUPERVISOR NODE
# ─────────────────────────────────────────────────────────────

def react_supervisor_node(state: AgentState) -> dict:
    task_id = state.get("task_id")

    if state.get("debug_loop_count", 0) > 40:
        emit_event(task_id, {"type": "system_error", "error": "Supervisor reached max react loops (40) — terminating."})
        return {"terminate": True}

    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("supervisor", ""),
        base_model=state.get("model", "ollama")
    )

    tools = [PlannerTool, TriggerAgent, EndWorkflow]
    llm = llm.bind_tools(tools)

    plan: List[dict] = state.get("react_plan") or []

    plan_summary = "\n".join(
        [f"- {p['task']} ({p['status']})" for p in plan]
    ) or "No tasks yet."

    recent_events = state.get("events", [])[-6:]

    messages = _react_prompt.format_messages(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        requirements=state.get("requirements", ""),
        plan=plan_summary,
        events=str(recent_events)
    )

    response = llm.invoke(messages)

    if not getattr(response, "tool_calls", []):
        emit_event(task_id, {"type": "system_error", "error": "Supervisor failed to call tool"})
        return {}

    tool_call = response.tool_calls[0]
    name = tool_call["name"]
    args = tool_call["args"]

    emit_event(task_id, {"type": "log", "message": f"🧠 ReAct: {name}"})

    # ────────────────────────────────
    # META-STABILITY LAYER
    # ────────────────────────────────

    meta = state.get("react_meta") or {
        "last_action_hash": "",
        "repeat_count": 0,
        "planner_append_streak": 0,
        "last_triggered_agent": "",
    }

    action_signature = name + json.dumps(args, sort_keys=True)
    action_hash = hashlib.md5(action_signature.encode()).hexdigest()

    # Convergence detection
    if action_hash == meta["last_action_hash"]:
        meta["repeat_count"] += 1
    else:
        meta["repeat_count"] = 0

    meta["last_action_hash"] = action_hash

    if meta["repeat_count"] >= 2:
        emit_event(task_id, {"type": "log", "message": "⚠ Convergence detected — terminating."})
        return {"terminate": True, "react_meta": meta}

    # Planner anti-spam
    if name == "PlannerTool" and args.get("action") == "append":
        meta["planner_append_streak"] += 1
    else:
        meta["planner_append_streak"] = 0

    if meta["planner_append_streak"] > 3:
        emit_event(task_id, {"type": "log", "message": "⚠ Planner append spam detected — forcing agent trigger."})
        return {
            "react_meta": meta,
            "messages": [
                make_action_message(
                    "Forced execution due to planner spam",
                    ActionType.CODE_READY,
                    "react_supervisor"
                )
            ]
        }

    # Action deduplication
    if name == "TriggerAgent":
        if args.get("agent") == meta["last_triggered_agent"]:
            meta["repeat_count"] += 1
        else:
            meta["repeat_count"] = 0

        meta["last_triggered_agent"] = args.get("agent")

        if meta["repeat_count"] >= 2:
            emit_event(task_id, {"type": "log", "message": "⚠ Agent spam detected — terminating."})
            return {"terminate": True, "react_meta": meta}


    # ───────────── PlannerTool ─────────────
    if name == "PlannerTool":
        new_plan = plan.copy()

        if args["action"] == "append":
            new_plan.append({"task": args["task"], "status": "pending"})

        elif args["action"] == "complete":
            for p in new_plan:
                if p["task"] == args["task"]:
                    p["status"] = "completed"
                    break

        elif args["action"] == "update":
            for p in new_plan:
                if p["task"] == args["task"]:
                    p["status"] = args["new_status"]
                    break

        return {"react_plan": new_plan, "react_meta": meta}


    # ───────────── TriggerAgent ─────────────
    if name == "TriggerAgent":

        mapping = {
            "spec_writer": ActionType.PRD_READY,
            "coder": ActionType.CODE_READY,
            "reviewer": ActionType.REVIEW_READY,
            "refiner": ActionType.DECISION_REFINE,
            "tester": ActionType.TEST_COMPLETE,
            "analyzer": ActionType.ANALYSIS_REGENERATE,
        }

        return {
            "react_meta": meta,
            "messages": [
                make_action_message(
                    f"Supervisor triggered {args['agent']}: {args['objective']}",
                    mapping[args["agent"]],
                    "react_supervisor"
                )
            ]
        }



    # ───────────── EndWorkflow ─────────────
    if name == "EndWorkflow":
        summary = args.get("summary", "Workflow completed")
        emit_event(task_id, {"type": "log", "message": f"🏁 Workflow ended: {summary}"})
        return {"terminate": True, "react_meta": meta}

    return {"react_meta": meta}


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