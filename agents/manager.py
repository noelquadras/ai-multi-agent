"""
Simplified LLM-powered Manager Node + Router (The "Hub" in Hub-and-Spoke).
"""

from datetime import datetime
import json
import re
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.constants import Send
from langgraph.graph import END

from agents.state import AgentState
from agents.action_types import ActionType, registry
from agents.llm_config import get_llm
from database import emit_event

class DelegateTasks(BaseModel):
    """Delegate work to one or more agents."""
    next_agents: list[str] = Field(
        description="List of node names to invoke next. "
                    "Valid names: spec_writer, generate, review, decide, "
                    "refine, test, analyze_test, document, researcher. "
                    "Use empty list [] to end the workflow."
    )
    rationale: str = Field(default="", description="Brief reasoning for the decision.")


class FinishAndSummarize(BaseModel):
    """End the workflow when all tasks are complete."""
    summary: str = Field(description="Summary of the completed task.")


class AskHuman(BaseModel):
    """Ask human when stuck."""
    question: str = Field(description="The question to ask.")


_manager_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a project manager routing work between AI agents. "
     "Your ONLY output must be a tool call in JSON format. Never output conversational text.\n\n"
     "Available agents:\n"
     "- spec_writer: Writes technical specifications\n"
     "- generate: Generates code\n"
     "- review: Reviews code\n"
     "- decide: Decides if code needs refinement\n"
     "- refine: Fixes code based on feedback\n"
     "- test: Runs code in CLI sandbox\n"
     "- analyze_test: Analyzes test results\n"
     "- document: Writes documentation\n"
     "- researcher: Researches information from the web\n\n"
     "CRITICAL ROUTING RULES:\n"
     "1. If 'Has spec' is false, delegate to 'spec_writer'.\n"
     "2. If 'Has spec' but 'Has code' is false, delegate to 'generate'.\n"
     "3. If 'Has code' but 'Has review' is false, delegate to 'review'.\n"
     "4. If task is fully complete, use `FinishAndSummarize`.\n"
     "5. ONLY use the provided tools.\n"
     "6. If native tools fail, output EXACT JSON array:\n"
     '[{{"name": "DelegateTasks", "args": {{"next_agents": ["spec_writer"], "rationale": "reason"}}}}]'),
    ("human",
     "Original Requirements: {requirements}\n\n"
     "Last action: {action_type}\n"
     "Sender: {sender}\n"
     "Current project state:\n"
     "- Has spec: {has_spec}\n"
     "- Has code: {has_code}\n"
     "- Has review: {has_review}\n"
     "- Has test results: {has_tests}\n"
     "- Has research: {has_research}\n"
     "- Iteration count: {iteration_count}\n\n"
     "Call the appropriate tool to route the next step."),
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
    """Manager LLM step. Figures out what to do."""
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    last_action = ""
    sender = "unknown"

    if not messages:
        emit_event(task_id, {"type": "log", "message": "🧠 Manager: Cold start — first run"})
    else:
        last_msg = messages[-1]
        last_action = getattr(last_msg, "additional_kwargs", {}).get("action_type", "")
        sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "unknown")

    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("manager", ""),
        base_model=state.get("model", "ollama")
    )
    manager_tools = [DelegateTasks, FinishAndSummarize, AskHuman]
    
    # Try binding tools, but continue gracefully on failure
    try:
        llm_with_tools = llm.bind_tools(manager_tools)
    except Exception:
        llm_with_tools = llm

    try:
        llm_states = state.get("agent_states", {}) or {}
        has_spec = bool(llm_states.get("spec_writer", {}).get("spec_structured"))
        has_code = bool(llm_states.get("generate", {}).get("generated_code"))
        has_review = bool(llm_states.get("review", {}).get("review_report"))
        has_tests = bool(llm_states.get("test", {}).get("test_results"))
        has_research = bool(llm_states.get("researcher", {}).get("research_report"))
    except Exception:
        has_spec = has_code = has_review = has_tests = has_research = False

    formatted_prompts = _manager_prompt.format_messages(
        action_type=last_action or "none",
        sender=sender,
        requirements=state.get("requirements", ""),
        has_spec=has_spec,
        has_code=has_code,
        has_review=has_review,
        has_tests=has_tests,
        has_research=has_research,
        iteration_count=state.get("iteration_count", 0)
    )

    filtered_state = _filter_state_for(state, "manager")
    run_messages = [formatted_prompts[0]] + filtered_state["messages"] + [formatted_prompts[1]]

    try:
        response = llm_with_tools.invoke(run_messages)
        response = _extract_manual_tools(response)
        
        # Add basic retry loop if manual tools failed
        retries = 0
        while not getattr(response, "tool_calls", []) and retries < 1:
            run_messages.append(response)
            run_messages.append(SystemMessage(content="You MUST use one of the provided tools (DelegateTasks, FinishAndSummarize, AskHuman) and format as JSON array!"))
            response = _extract_manual_tools(llm_with_tools.invoke(run_messages))
            retries += 1
            
    except Exception as e:
        emit_event(task_id, {"type": "system_error", "error": f"LLM error: {e}"})
        response = AIMessage(content="", tool_calls=[{"name": "AskHuman", "args": {"question": "I had an internal error determining the next step."}, "id": "err"}])

    content = response.content or ""
    if content and not content.strip().startswith("[{"):
        emit_event(task_id, {"type": "log", "message": f"🧠 Manager thought: {content[:100]}"})

    metrics = state.get("agent_metrics", {})
    return {
        "messages": [response],
        "current_agent": "manager",
        "agent_metrics": metrics
    }


def manager_router(state: AgentState):
    """Edge router. Dispatches standard Send requests based on tools chosen."""
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")

    if state.get("iteration_count", 0) >= 15:
        emit_event(task_id, {"type": "log", "message": "🛑 Max iterations reached."})
        return END

    if len(messages) <= 1:
        # Initial task classification
        targets = registry.get_subscribers(str(ActionType.COLD_START))
        if targets:
            return [Send(t, _filter_state_for(state, t)) for t in targets]
        return [Send("classify_task", state)]

    last_msg = messages[-1]

    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tc_raw in last_msg.tool_calls:
            tc = {str(k).strip().replace('"', '').replace("'", ""): v for k, v in tc_raw.items()}
            tool_name = tc.get("name")
            tool_args = tc.get("args", tc.get("arguments", {}))
            
            if tool_name == "FinishAndSummarize":
                emit_event(task_id, {"type": "log", "message": f"🏁 Workflow completed: {tool_args.get('summary', '')}"})
                return END
                
            elif tool_name == "AskHuman":
                emit_event(task_id, {"type": "log", "message": f"🛑 Manager requested human: {tool_args.get('question', '')}"})
                return END
                
            elif tool_name == "DelegateTasks":
                next_agents = tool_args.get("next_agents", [])
                rationale = tool_args.get("rationale", "")
                emit_event(task_id, {"type": "log", "message": f"🧠 Router (Delegation): {next_agents} — {rationale}"})
                
                if not next_agents:
                    return END
                    
                allowed = {"spec_writer", "generate", "review", "decide", "refine", "document", "test", "analyze_test", "classify_task", "researcher"}
                valid_agents = [a for a in next_agents if a in allowed]
                
                if valid_agents:
                    # Return distinct agents to send states to
                    return [Send(agent, _filter_state_for(state, agent)) for agent in dict.fromkeys(valid_agents)]
                return END

        emit_event(task_id, {"type": "log", "message": "🧠 Native tool call detected."})
        return "tools"

    if isinstance(last_msg, ToolMessage) or getattr(last_msg, "type", "") == "tool":
        requesting_agent = "manager"
        for msg in reversed(messages[:-1]):
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", []):
                requesting_agent = getattr(msg, "additional_kwargs", {}).get("sender", "manager")
                break
        emit_event(task_id, {"type": "log", "message": f"🧠 Tool response -> returning to '{requesting_agent}'"})
        return [Send(requesting_agent, _filter_state_for(state, requesting_agent))]

    last_action = getattr(last_msg, "additional_kwargs", {}).get("action_type", "")
    if last_action == str(ActionType.RESEARCH_READY):
        requester = next((getattr(m, "additional_kwargs", {}).get("sender", "") for m in reversed(messages) if getattr(m, "additional_kwargs", {}).get("action_type", "") == str(ActionType.NEEDS_RESEARCH)), "spec_writer")
        target = requester or "spec_writer"
        emit_event(task_id, {"type": "log", "message": f"🧠 research_ready → back to '{target}'"})
        return [Send(target, _filter_state_for(state, target))]

    return END
