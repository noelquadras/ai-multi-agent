"""
LLM-powered Manager Node + Router (The "Hub" in Hub-and-Spoke).

Architecture:
  - manager_node():  A thin pass-through node that logs the incoming action.
                     Returns a state dict (required by LangGraph).
  - manager_router(): A conditional edge function that reads the last
                      message's action_type, queries the registry, and
                      returns Send() objects to dispatch to subscribers.
                      This is used with add_conditional_edges().

Cold-start: If no messages exist yet, routes directly to spec_writer.

Fallback: If the registry has no subscribers for an action type, the router
uses a lightweight LLM call with structured output to decide routing.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langgraph.constants import Send
from langgraph.graph import END

from agents.state import AgentState
from agents.action_types import ActionType, registry, make_action_message
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
    rationale: str = Field(
        default="",
        description="Brief reasoning for the routing decision."
    )


class FinishAndSummarize(BaseModel):
    """End the workflow when all tasks are complete, providing a final summary."""
    summary: str = Field(description="A comprehensive summary of the completed task and deliverables.")


class AskHuman(BaseModel):
    """Ask the human user a question when you are stuck, hit an infinite loop, or need clarification."""
    question: str = Field(description="The question to ask the user, including a brief summary of the situation.")


_manager_prompt = ChatPromptTemplate.from_messages([

    ("system",
     "You are a project manager routing work between AI agents. "
     "Given the last action and project state, decide which agent(s) to invoke next.\n\n"
     "Available agents and their roles:\n"
     "- spec_writer: Writes technical specifications from requirements\n"
     "- generate: Generates code from specs\n"
     "- review: Reviews code for bugs and security\n"
     "- decide: Decides if code needs refinement\n"
     "- refine: Fixes code based on feedback\n"
     "- test: Runs code in CLI sandbox\n"
     "- analyze_test: Analyzes test results\n"
     "- document: Writes documentation\n"
     "- researcher: Researches information from the web to help other agents\n\n"
     "CRITICAL ROUTING RULES:\n"
     "1. If 'Has spec' is false, you MUST delegate to 'spec_writer'.\n"
     "2. If 'Has spec' is true but 'Has code' is false, you MUST delegate to 'generate'. DO NOT delegate to 'review' yet.\n"
     "3. If 'Has code' is true but 'Has review' is false, you MUST delegate to 'review'.\n"
     "4. If last action is 'research_ready', re-delegate to the agent that requested the research (check the sender).\n"
     "5. You MUST use the `DelegateTasks` tool to route to the next agent.\n"
     "6. If the overall task is fully complete, use `FinishAndSummarize` to end the workflow and provide a summary.\n"
     "7. If you are stuck, hit an infinite loop, or need human intervention, use `AskHuman`.\n"
     "8. DO NOT output conversational text, explanations, or 'I will delegate this to...'\n"
     "9. ANY response that is not a tool call is a failure."),
    ("human",
     "Original Requirements: {requirements}\n\n"
     "Last action: {action_type}\n"
     "Sender: {sender}\n"
     "Current project state:\n"
     "- Task profile/complexity: {profile}\n"
     "- Has spec: {has_spec}\n"
     "- Has code: {has_code}\n"
     "- Has review: {has_review}\n"
     "- Has test results: {has_tests}\n"
     "- Has research: {has_research}\n"
     "- Iteration count: {iteration_count}\n\n"
     "Review the messages context, use tools if needed, and call DelegateTasks when ready to route."),
])


def _filter_state_for(state: dict, role_name: str) -> dict:
    """
    Return a copy of state with messages filtered to only those
    relevant to the target role.

    Keeps: last 12 messages total, prioritising messages from/to
    this role. This prevents context window waste when the team grows.
    
    NOTE: Creates a shallow copy of the state dict. Nested dicts like
    agent_states are shared (read-only from spokes), which is safe
    because each spoke only updates its own key via the reducer.
    """
    all_messages = list(state.get("messages", []))

    # Separate: messages involving this role vs others
    role_msgs = []
    other_msgs = []
    for msg in all_messages:
        sender = getattr(msg, "additional_kwargs", {}).get("sender", "")
        if sender == role_name:
            role_msgs.append(msg)
        else:
            other_msgs.append(msg)

    # Always include the last message (trigger) + role-relevant ones + recent context
    last_msg = all_messages[-1:] if all_messages else []
    combined = role_msgs + other_msgs[-5:] + last_msg

    # Deduplicate while preserving order
    seen_ids = set()
    deduped = []
    for msg in combined:
        msg_id = id(msg)
        if msg_id not in seen_ids:
            seen_ids.add(msg_id)
            deduped.append(msg)

    # Cap at 12 messages and create a new dict to avoid mutations
    filtered = {**state}
    filtered["messages"] = deduped[-12:]
    return filtered


def manager_node(state: AgentState) -> dict:
    """
    Manager node that actually thinks using an LLM configured with tools.
    Decides whether to search/gather information or delegate to other agents.
    """
    from langchain_core.messages import SystemMessage
    from agents.llm_config import _available_tools

    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    metrics = state.get("agent_metrics", {})
    last_action = ""
    sender = "unknown"

    if not messages:
        emit_event(task_id, {
            "type": "log",
            "message": "🧠 Manager: Cold start — first run"
        })
    else:
        last_msg = messages[-1]
        last_action = getattr(last_msg, "additional_kwargs", {}).get("action_type", "")
        sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "unknown")
        
    # Update metrics for the sender
    if sender != "unknown" and sender != "manager":
        # Note: Manager should be the one to update this in a single-writer system.
        current_metrics = metrics.copy()
        agent_metric = current_metrics.get(sender, {"calls": 0, "tokens": 0})
        agent_metric["calls"] += 1
        
        usage = getattr(last_msg, "usage_metadata", None)
        if usage:
            agent_metric["tokens"] += usage.get("total_tokens", 0)
        elif "usage" in last_msg.additional_kwargs: 
            usage = last_msg.additional_kwargs["usage"]
            agent_metric["tokens"] += usage.get("total_tokens", 0)
            
        current_metrics[sender] = agent_metric
        metrics = current_metrics

    # Check for errors in the incoming state (Anti-looping tracking)
    recent_errors = False
    for msg in messages[-1:]: # Only check the new ones
        if getattr(msg, "additional_kwargs", {}).get("error"):
             recent_errors = True
             pass # Errors should be in the 'errors' list now

    # Use dynamically provided model for the manager
    llm = get_llm(
        for_heavy_task=False,
        override_model=state.get("agent_models", {}).get("manager", ""),
        base_model=state.get("model", "ollama")
    )
    manager_tools = _available_tools + [DelegateTasks, FinishAndSummarize, AskHuman]
    llm_with_tools = llm.bind_tools(manager_tools)

    # Prepare system message context using single-writer sources
    llm_states = state.get("agent_states", {})
    
    # Extract common data for the manager
    has_spec = bool(llm_states.get("spec_writer", {}).get("spec_structured"))
    has_code = bool(llm_states.get("generate", {}).get("generated_code"))
    has_review = bool(llm_states.get("review", {}).get("review_report"))
    has_tests = bool(llm_states.get("test", {}).get("test_results"))
    has_research = bool(llm_states.get("researcher", {}).get("research_report"))

    sys_prompt = _manager_prompt.format_messages(
        action_type=last_action or "none",
        sender=sender,
        profile=state.get("task_profile"),
        has_spec=has_spec,
        has_code=has_code,
        has_review=has_review,
        has_tests=has_tests,
        has_research=has_research,
        iteration_count=state.get("iteration_count", 0),
    )[0] 
    
    human_prompt = _manager_prompt.format_messages(
        action_type=last_action or "none",
        sender=sender,
        profile=state.get("task_profile"),
        has_spec=has_spec,
        has_code=has_code,
        has_review=has_review,
        has_tests=has_tests,
        has_research=has_research,
        iteration_count=state.get("iteration_count", 0),
    )[1]

    # Combine context for the manager to think
    filtered_state = _filter_state_for(state, "manager")
    run_messages = [sys_prompt] + filtered_state["messages"] + [human_prompt]

    # Feature: Anti-looping / check duplicates (Inspired by MetaGPT role_zero check_duplicates)
    if recent_errors and sender not in ("unknown", "manager"):
        run_messages.append(SystemMessage(content=f"WARNING: The previous agent/tool '{sender}' returned an error or failed. Do not blindly delegate the exact same task to it again. Consider a different strategy, delegating to 'refine', or using 'AskHuman' if you are stuck in a loop."))

    # Helper to recover JSON-only tool calls from models like Mistral
    def extract_manual_tool_calls(msg):
        if getattr(msg, "tool_calls", []):
            return msg
        if not msg.content or not isinstance(msg.content, str):
            return msg
        import re, json
        from langchain_core.messages import AIMessage
        match = re.search(r'\[\s*\{.*?"name"\s*:\s*".*?".*?\}\s*\]', msg.content, re.DOTALL)
        if match:
            try:
                parsed_calls = json.loads(match.group(0))
                extracted = []
                for tc in parsed_calls:
                    if "name" in tc and ("arguments" in tc or "args" in tc):
                        args = tc.get("arguments", tc.get("args", {}))
                        if isinstance(args, str): args = json.loads(args)
                        extracted.append({"name": tc["name"], "args": args, "id": "call_manual"})
                if extracted:
                    return AIMessage(content=msg.content, tool_calls=extracted)
            except Exception:
                pass
        return msg

    # Standard invoke with internal retry for tool calling
    response = extract_manual_tool_calls(llm_with_tools.invoke(run_messages))
    
    # Internal Retry Logic
    retries = 0
    while not getattr(response, "tool_calls", []) and retries < 2:
        content = response.content or ""
        if not content.strip():
            break
            
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: Manager failed to use tools. Retrying ({retries + 1}/2)."
        })
        
        retry_msg = SystemMessage(
            content="You output conversational text instead of a tool call. You must use the DelegateTasks tool to route to the next agent. Please try again."
        )
        run_messages.append(response)
        run_messages.append(retry_msg)
        
        response = extract_manual_tool_calls(llm_with_tools.invoke(run_messages))
        retries += 1

    # Only log a thought if it's natural language, not a raw tool call list or empty
    content = response.content or ""
    if content and not content.strip().startswith("[{"):
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Manager thought: {content}"
        })

    # Record the routing event
    routing_event = {
        "type": "routing_decision",
        "agent": "manager",
        "timestamp": datetime.now().isoformat(),
        "data": {"next": getattr(response, "tool_calls", [])}
    }

    return {
        "messages": [response],
        "current_agent": "manager",
        "agent_metrics": metrics,
        "total_tokens_used": state.get("total_tokens_used", 0) + getattr(response.usage_metadata, "total_tokens", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else state.get("total_tokens_used", 0),
        "events": [routing_event]
    }


def manager_router(state: AgentState):
    """
    Conditional edge function — routes based on tool calls (DelegateTasks or search).
    """
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    profile = state.get("task_profile")

    # ── 0. Global safety net — hard cap on total iterations ────────────
    iteration_count = state.get("iteration_count", 0)
    if iteration_count >= 10:
        emit_event(task_id, {
            "type": "log",
            "message": f"🛑 Router: Hard stop — iteration limit reached ({iteration_count}). Requesting human intervention (AskHuman fallback)."
        })
        return END

    # ── 1. Cold start — check if we need classification ───────────────
    # If the ONLY message is from the cold start manager node
    if len(messages) <= 1:
        if profile is None or profile.get("complexity") is None:
            # We enforce task classification first if no profile exists
            emit_event(task_id, {
                "type": "log",
                "message": "🧠 Router: No profile found → routing to classify_task via COLD_START"
            })
            targets = registry.get_subscribers(str(ActionType.COLD_START))
            if targets:
                return [Send(t, _filter_state_for(state, t)) for t in targets]
            return [Send("classify_task", state)] # Fallback just in case

    # ── 2. Handle the Manager's output ─────────────────────────────────
    last_msg = messages[-1]
    
    # Check for tool calls
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        # Intercept System Tools
        for tc in last_msg.tool_calls:
            if tc["name"] == "FinishAndSummarize":
                summary = tc["args"].get("summary", "")
                emit_event(task_id, {
                    "type": "log",
                    "message": f"🏁 Router: Workflow completed. Summary: {summary}"
                })
                return END
                
            elif tc["name"] == "AskHuman":
                question = tc["args"].get("question", "")
                emit_event(task_id, {
                    "type": "log",
                    "message": f"🛑 Router: Manager requested human intervention: {question}"
                })
                return END
                
            elif tc["name"] == "DelegateTasks":
                next_agents = tc["args"].get("next_agents", [])
                rationale = tc["args"].get("rationale", "")
                
                emit_event(task_id, {
                    "type": "log",
                    "message": f"🧠 Router (Delegation): {next_agents} — {rationale}"
                })
                
                if not next_agents:
                    return END
                    
                # Trust the manager's intelligent routing. Just validate the names.
                allowed_nodes = {"spec_writer", "generate", "review", "decide", 
                                 "refine", "document", "test", "analyze_test", "classify_task", "researcher"}
                
                # Alias map for small LLM hallucinations
                aliases = {
                    "code_reviewer": "review", "code_generator": "generate", 
                    "tester": "test", "doc_writer": "document", 
                    "documentation": "document", "research": "researcher",
                    "code_refiner": "refine", "spec_generator": "spec_writer"
                }
                
                valid_agents = []
                for a in next_agents:
                    if a in allowed_nodes:
                        valid_agents.append(a)
                    elif a in aliases:
                        valid_agents.append(aliases[a])
                
                # Deduplicate
                valid_agents = list(dict.fromkeys(valid_agents))
                
                if valid_agents:
                    return [
                        Send(agent, _filter_state_for(state, agent))
                        for agent in valid_agents
                    ]
                else:
                    return END

        # Normal tool calls (e.g. search) go to 'tools' node
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: Native tool call detected, to 'tools'."
        })
        return "tools"
        
    # Check if this is a response FROM the tools node
    from langchain_core.messages import ToolMessage, AIMessage as _AIMsg
    if getattr(last_msg, "type", "") == "tool" or isinstance(last_msg, ToolMessage):
        # Find who originally requested the tool by scanning for the preceding
        # AIMessage with tool_calls. The sender metadata tells us which agent.
        requesting_agent = "manager"  # safe fallback
        for msg in reversed(messages[:-1]):  # skip the ToolMessage itself
            if isinstance(msg, _AIMsg) and getattr(msg, "tool_calls", []):
                requesting_agent = getattr(msg, "additional_kwargs", {}).get("sender", "manager")
                break
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: Tool response received → routing back to '{requesting_agent}'"
        })
        return [Send(requesting_agent, _filter_state_for(state, requesting_agent))]

    last_action = getattr(last_msg, "additional_kwargs", {}).get("action_type", "")
    sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "unknown")

    # ── 3. Research completed — route back to the original requester ────
    if last_action == str(ActionType.RESEARCH_READY):
        # Find who originally requested the research by scanning for NEEDS_RESEARCH
        requester = None
        for msg in reversed(messages):
            msg_action = getattr(msg, "additional_kwargs", {}).get("action_type", "")
            msg_sender = getattr(msg, "additional_kwargs", {}).get("sender", "")
            if msg_action == str(ActionType.NEEDS_RESEARCH) and msg_sender:
                requester = msg_sender
                break
        
        # Default to spec_writer if we can't find the requester
        target = requester or "spec_writer"
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: research_ready → routing back to '{target}' (original requester)"
        })
        return [Send(target, _filter_state_for(state, target))]

    # ── 4. Cost Awareness: Hard Caps ────────────────────────────────────
    if profile and profile.get("complexity") == "trivial":
        iteration_count = state.get("iteration_count", 0)
        if iteration_count >= 2:
            emit_event(task_id, {
                "type": "log",
                "message": f"⚠️ Router: Trivial task reached max iterations ({iteration_count}), ending."
            })
            return END

    # ── 4. Terminal actions ──────────────────────────────────────────────
    if last_action in (str(ActionType.DOCS_READY),):
        emit_event(task_id, {
            "type": "log",
            "message": "🧠 Router: docs_ready → workflow complete"
        })
        return END

    # ── 5. Unrecoverable Failure ──────────────────────────────
    # If the manager reaches this point, all internal retries failed.
    emit_event(task_id, {
        "type": "log",
        "message": f"🧠 Router: Manager returned text without delegation after internal retries, finishing."
    })
    return END
