"""
Simplified LLM-powered Manager Node + Router (The "Hub" in Hub-and-Spoke).
"""

from datetime import datetime
import json
import re
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.constants import Send
from langgraph.graph import END

from agents.state import AgentState
from agents.action_types import ActionType, registry
from agents.llm_config import get_llm
from database import emit_event

class RoutePhase(BaseModel):
    """Transition the workflow to a new phase or terminate."""
    next_phase: Literal["PLAN", "MAKE", "TEST", "DONE"] = Field(
        description="The next execution phase to enter. Use DONE to finish."
    )
    rationale: str = Field(description="Brief reasoning for this phase transition.")


class AskHuman(BaseModel):
    """Ask human when stuck or when escalating."""
    question: str = Field(description="The question or reasoning to present to the user.")


_manager_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a supervisory autonomous controller routing work strictly via Execution Phases. "
     "Your ONLY output must be a tool call in JSON format. Never output conversational text.\n\n"
     "Available Phases:\n"
     "- PLAN: Generates specs and execution plans.\n"
     "- MAKE: Deterministically generates, reviews, and refines code.\n"
     "- TEST: Runs the code in a sandbox and analyzes errors.\n"
     "- DONE: Terminates the workflow successfully.\n\n"
     "CRITICAL ROUTING RULES:\n"
     "1. You MUST use RoutePhase or AskHuman tool.\n"
     "2. You can determine the phase based on iteration counts, failure types, and execution plan states.\n"
     "3. Do NOT route to DONE unless TEST passed, PLAN & MAKE both completed at least once, acceptance_criteria is satisfied, and confidence_score >= 0.75.\n"
     ),
    ("human",
     "Original Requirements: {requirements}\n\n"
     "Current project state:\n"
     "- Plan iterations: {plan_iterations}\n"
     "- Make iterations: {make_iterations}\n"
     "- Test iterations: {test_iterations}\n"
     "- Failure type: {failure_type}\n"
     "- Confidence Score: {confidence_score}\n"
     "- Phase: {phase}\n"
     "- Acceptance Criteria: {acceptance_criteria}\n\n"
     "Execution Plan Step Statuses:\n"
     "{execution_plan_summary}\n\n"
     "Call the appropriate tool to route to the next phase."),
])


def _filter_state_for(state: AgentState, role_name: str) -> dict:
    """Filter state to recent messages for the target role to save context limit."""
    all_messages = list(state.get("messages", []))
    role_msgs = []
    other_msgs = []
    for msg in all_messages:
        sender = getattr(msg, "additional_kwargs", {}).get("sender", "")
        if sender == role_name:
            role_msgs.append(msg)
        else:
            other_msgs.append(msg)

    last_msg = all_messages[-1:] if all_messages else []
    combined = role_msgs + other_msgs[-5:] + last_msg

    seen_ids = set()
    deduped = []
    for msg in combined:
        msg_id = id(msg)
        if msg_id not in seen_ids:
            seen_ids.add(msg_id)
            deduped.append(msg)

    filtered = {**state}
    filtered["messages"] = deduped[-12:]
    return filtered


def _extract_manual_tools(msg):
    """Fallback payload extractor for local models when native tools fail."""
    if getattr(msg, "tool_calls", []):
        return msg
    content = msg.content or ""
    try:
        match = re.search(r'(\[.*?\]|\{.*?\})', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict): parsed = [parsed]
            extracted = []
            for tc in parsed:
                if "name" in tc:
                    extracted.append({
                        "name": tc["name"], 
                        "args": tc.get("args", tc.get("arguments", {})), 
                        "id": "call_manual"
                    })
            if extracted:
                return AIMessage(content=msg.content, tool_calls=extracted, additional_kwargs=msg.additional_kwargs)
    except Exception:
        pass
    return msg


def manager_node(state: AgentState) -> dict:
    """Manager Phase Router Node. Decides which Phase to run next."""
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    
    # Check hard escalation policies explicitly before LLM acts
    make_iterations = state.get("make_iterations", 0)
    test_iterations = state.get("test_iterations", 0)
    plan_iterations = state.get("plan_iterations", 0)
    failure_type = state.get("failure_type")
    
    # Escalation Pre-Routing
    if plan_iterations > 2:
        msg = AskHuman(question="Maximum plan iterations exceeded. Humans must intervene.").model_dump()
        return {"messages": [AIMessage(content="", tool_calls=[{"name": "AskHuman", "args": msg, "id": "esc"}])], "current_agent": "manager"}
    if make_iterations > 3 and state.get("phase") != "PLAN":
        msg = RoutePhase(next_phase="PLAN", rationale="make_iterations > 3, escalating to PLAN phase for rethink.").model_dump()
        emit_event(task_id, {"type": "log", "message": f"Escalation: make_iterations ({make_iterations}) > 3. Re-entering PLAN."})
        return {"messages": [AIMessage(content="", tool_calls=[{"name": "RoutePhase", "args": msg, "id": "esc"}])], "current_agent": "manager"}
    if test_iterations > 2 and state.get("phase") != "PLAN":
        msg = RoutePhase(next_phase="PLAN", rationale="test_iterations > 2, escalating to PLAN phase for rethink.").model_dump()
        emit_event(task_id, {"type": "log", "message": f"Escalation: test_iterations ({test_iterations}) > 2. Re-entering PLAN."})
        return {"messages": [AIMessage(content="", tool_calls=[{"name": "RoutePhase", "args": msg, "id": "esc"}])], "current_agent": "manager"}
    if failure_type in ["logical_failure", "spec_mismatch"] and state.get("phase") != "PLAN":
        msg = RoutePhase(next_phase="PLAN", rationale=f"failure_type {failure_type} requires re-planning.").model_dump()
        emit_event(task_id, {"type": "log", "message": f"Escalation: failure_type was {failure_type}. Re-entering PLAN."})
        return {"messages": [AIMessage(content="", tool_calls=[{"name": "RoutePhase", "args": msg, "id": "esc"}])], "current_agent": "manager"}

    # Evaluate execution_plan summary
    exec_plan = state.get("execution_plan", [])
    ep_summary = "\\n".join([f"Step {s['step_id']} [{s['phase']}]: {s['status']} - {s['description']}" for s in exec_plan]) or "No execution plan yet."

    manager_state = state.get("agent_states", {}).get("manager", {})
    last_plan = manager_state.get("last_plan", [])
    last_plan_iterations = manager_state.get("last_plan_iterations", 0)
    
    # Check for unchanged plan escalation
    if plan_iterations > last_plan_iterations and last_plan_iterations > 0:
        if exec_plan and exec_plan == last_plan:
            msg = AskHuman(question="Infinite phase cycling detected: execution_plan remains unchanged across two PLAN phases.").model_dump()
            return {"messages": [AIMessage(content="", tool_calls=[{"name": "AskHuman", "args": msg, "id": "esc"}])], "current_agent": "manager"}

    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("manager", ""),
        base_model=state.get("model", "ollama")
    )
    manager_tools = [RoutePhase, AskHuman]
    
    try:
        llm_with_tools = llm.bind_tools(manager_tools)
    except Exception:
        llm_with_tools = llm

    formatted_prompts = _manager_prompt.format_messages(
        requirements=state.get("requirements", ""),
        plan_iterations=plan_iterations,
        make_iterations=make_iterations,
        test_iterations=test_iterations,
        failure_type=failure_type or "None",
        confidence_score=state.get("confidence_score", 0.0),
        phase=state.get("phase", "None"),
        acceptance_criteria=json.dumps(state.get("acceptance_criteria", {})),
        execution_plan_summary=ep_summary
    )

    filtered_state = _filter_state_for(state, "manager")
    run_messages = [formatted_prompts[0]] + filtered_state["messages"] + [formatted_prompts[1]]

    try:
        response = llm_with_tools.invoke(run_messages)
        response = _extract_manual_tools(response)
        
        retries = 0
        while not getattr(response, "tool_calls", []) and retries < 1:
            run_messages.append(response)
            run_messages.append(SystemMessage(content="You MUST use one of the provided tools (RoutePhase, AskHuman) and format as JSON array!"))
            response = _extract_manual_tools(llm_with_tools.invoke(run_messages))
            retries += 1
    except Exception as e:
        emit_event(task_id, {"type": "system_error", "error": f"LLM error: {e}"})
        response = AIMessage(content="", tool_calls=[{"name": "AskHuman", "args": {"question": "I had an internal error determining the next step."}, "id": "err"}])

    phase_update = {}
    if getattr(response, "tool_calls", []):
        for tc in response.tool_calls:
            if tc.get("name") == "RoutePhase":
                next_phase = tc.get("args", {}).get("next_phase", state.get("phase"))
                phase_update["phase"] = next_phase
                if state.get("phase") != "MAKE" and next_phase == "MAKE":
                    phase_update["failure_type"] = None

    return {
        "messages": [response],
        "current_agent": "manager",
        "agent_states": {"manager": {"last_plan": exec_plan, "last_plan_iterations": plan_iterations}},
        **phase_update
    }


def manager_router(state: AgentState):
    """Edge router defining phase transitions from manager to subgraphs."""
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")

    if state.get("iteration_count", 0) >= 30:
        emit_event(task_id, {"type": "log", "message": "🛑 Max global iterations reached."})
        return END

    if not messages:
        return "PLAN_GRAPH"

    last_msg = messages[-1]

    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tc_raw in last_msg.tool_calls:
            tc = {str(k).strip().replace('"', '').replace("'", ""): v for k, v in tc_raw.items()}
            tool_name = tc.get("name")
            tool_args = tc.get("args", tc.get("arguments", {}))
            
            if tool_name == "AskHuman":
                emit_event(task_id, {"type": "log", "message": f"🛑 Manager requested human: {tool_args.get('question', '')}"})
                return END
                
            elif tool_name == "RoutePhase":
                next_phase = tool_args.get("next_phase", "DONE")
                rationale = tool_args.get("rationale", "")
                
                # Check DONE condition Enforcements before granting it
                if next_phase == "DONE":
                    if state.get("plan_iterations", 0) < 1 or state.get("make_iterations", 0) < 1:
                        emit_event(task_id, {"type": "log", "message": "⚠️ DONE rejected. Both PLAN and MAKE must complete at least once."})
                        return "PLAN_GRAPH"
                    if state.get("confidence_score", 0.0) < 0.75:
                        emit_event(task_id, {"type": "log", "message": f"⚠️ DONE rejected. Confidence Score {state.get('confidence_score', 0.0)} < 0.75."})
                        return "MAKE_GRAPH"
                    if state.get("failure_type"):
                        emit_event(task_id, {"type": "log", "message": f"⚠️ DONE rejected. Failing test state: {state.get('failure_type')}."})
                        return "TEST_GRAPH"
                        
                    emit_event(task_id, {"type": "log", "message": f"🏁 Workflow completed: {rationale}"})
                    return END
                
                emit_event(task_id, {"type": "log", "message": f"🧠 Authority RoutePhase: {next_phase} — {rationale}"})
                
                if next_phase == "PLAN":
                    return "PLAN_GRAPH"
                elif next_phase == "MAKE":
                    return "MAKE_GRAPH"
                elif next_phase == "TEST":
                    return "TEST_GRAPH"
                    
                return END
                
    # If returned a normal tool, manager calls tool node
    if isinstance(last_msg, ToolMessage) or getattr(last_msg, "type", "") == "tool":
        return "manager"
        
    # By default fallback to PLAN if lost
    return "PLAN_GRAPH"
