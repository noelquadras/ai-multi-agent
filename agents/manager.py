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

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langgraph.constants import Send
from langgraph.graph import END

from agents.state import AgentState
from agents.action_types import ActionType, registry, make_action_message
from agents.llm_config import get_llm
from database import emit_event


class ManagerDecision(BaseModel):
    """Structured output from the Manager LLM for routing decisions."""
    next_agents: list[str] = Field(
        description="List of node names to invoke next. "
                    "Valid names: spec_writer, generate, review, decide, "
                    "refine, test, analyze_test, document. "
                    "Use empty list [] to end the workflow."
    )
    rationale: str = Field(
        default="",
        description="Brief reasoning for the routing decision."
    )


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
     "- document: Writes documentation\n\n"
     "Return empty list to end the workflow."),
    ("human",
     "Last action: {action_type}\n"
     "Sender: {sender}\n"
     "Message: {content}\n\n"
     "Current project state:\n"
     "- Has spec: {has_spec}\n"
     "- Has code: {has_code}\n"
     "- Has review: {has_review}\n"
     "- Has test results: {has_tests}\n"
     "- Iteration count: {iteration_count}\n\n"
     "Which agent(s) should run next?"),
])


def _filter_state_for(state: dict, role_name: str) -> dict:
    """
    Return a copy of state with messages filtered to only those
    relevant to the target role.

    Keeps: last 10 messages total, prioritising messages from/to
    this role. This prevents context window waste when the team grows.
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

    # Cap at 10 messages
    filtered = dict(state)
    filtered["messages"] = deduped[-10:]
    return filtered


def manager_node(state: AgentState) -> dict:
    """
    Thin pass-through node — logs the incoming action, updates metrics,
    and returns state updates.
    """
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    metrics = state.get("agent_metrics", {})

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
            agent_metric = metrics.get(sender, {"calls": 0, "tokens": 0})
            agent_metric["calls"] += 1
            
            # Extract token usage if available (LangChain 0.2+ usage_metadata)
            usage = getattr(last_msg, "usage_metadata", None)
            if usage:
                agent_metric["tokens"] += usage.get("total_tokens", 0)
            elif "usage" in last_msg.additional_kwargs: # Older/Provider-specific
                usage = last_msg.additional_kwargs["usage"]
                agent_metric["tokens"] += usage.get("total_tokens", 0)
                
            metrics[sender] = agent_metric

        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Manager: Received '{last_action}' from '{sender}'"
        })

    return {
        "current_agent": "manager",
        "agent_metrics": metrics
    }


def manager_router(state: AgentState):
    """
    Conditional edge function — reads the last message's action_type,
    queries the registry, and returns Send() objects.

    Cost-aware: Limits iterations for trivial tasks.
    Profile-aware: Skips agents based on classification flags.
    """
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    profile = state.get("task_profile")

    # ── 1. Cold start — check if we need classification ───────────────
    if not messages:
        if profile is None or profile.get("complexity") is None:
            emit_event(task_id, {
                "type": "log",
                "message": "🧠 Router: No profile found → routing to classify_task"
            })
            return [Send("classify_task", state)]
        
        # If we have a profile but no messages (unlikely in this flow, but for safety)
        emit_event(task_id, {
            "type": "log",
            "message": "🧠 Router: Cold start with existing profile"
        })
        # Determine starting node if messages empty but profile exists
        if profile.get("needs_spec"):
            return [Send("spec_writer", state)]
        return [Send("generate", state)]

    # ── 2. Read last action ────────────────────────────────────────────────
    last_msg = messages[-1]
    last_action = getattr(last_msg, "additional_kwargs", {}).get("action_type", "")
    sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "unknown")

    # ── 3. Cost Awareness: Hard Caps ────────────────────────────────────
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

    # ── 5. Registry lookup & Profile-based Filtering ──────────────────────
    subscribers = registry.get_subscribers(last_action)
    
    if profile:
        filtered = []
        for agent in subscribers:
            # Skip check
            skip_reason = None
            if agent == "spec_writer" and not profile.get("needs_spec"):
                skip_reason = "needs_spec=False"
            elif agent == "review" and not profile.get("needs_review"):
                skip_reason = "needs_review=False"
            elif agent == "document" and not profile.get("needs_docs"):
                skip_reason = "needs_docs=False"
            elif agent == "test" and not profile.get("needs_testing"):
                skip_reason = "needs_testing=False"
            
            # TASK_CLASSIFIED specialized logic: ensure correct starting point
            if last_action == str(ActionType.TASK_CLASSIFIED):
                if profile["complexity"] == "complex":
                    if agent == "generate": 
                        continue # Complex must go through spec_writer first
                else:
                    if agent == "spec_writer":
                        continue # Trivial/Standard go straight to generate
            
            if skip_reason:
                emit_event(task_id, {
                    "type": "log",
                    "message": f"🧠 Router: Skipping {agent} ({skip_reason})"
                })
                continue
                
            filtered.append(agent)
        subscribers = filtered

    if subscribers:
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: Dispatching to {subscribers}"
        })
        return [
            Send(role, _filter_state_for(state, role))
            for role in subscribers
        ]

    # ── 6. LLM fallback (only if registry is empty) ──────────────────────
    # Avoid LLM fallback if we already have a successful classification path
    if profile and last_action in (str(ActionType.TASK_CLASSIFIED), str(ActionType.CODE_READY), str(ActionType.PRD_READY)):
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: No subscribers for '{last_action}' under current profile, ending."
        })
        return END

    emit_event(task_id, {
        "type": "log",
        "message": f"🧠 Router: No registry entry for '{last_action}' — asking LLM"
    })

    try:
        llm = get_llm(
            for_heavy_task=False, 
            base_model=state.get("model", "ollama")
        )
        structured_llm = llm.with_structured_output(ManagerDecision)

        prompt_messages = _manager_prompt.format_messages(
            action_type=last_action or "none",
            sender=sender,
            content=last_msg.content[:500] if hasattr(last_msg, "content") else "",
            has_spec=bool(state.get("spec_structured")),
            has_code=bool(state.get("generated_code")),
            has_review=bool(state.get("review_report")),
            has_tests=bool(state.get("test_results")),
            iteration_count=state.get("iteration_count", 0),
        )

        decision: ManagerDecision = structured_llm.invoke(prompt_messages)

        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router (LLM): {decision.next_agents} — {decision.rationale}"
        })

        if not decision.next_agents:
            return END

        return [
            Send(agent, _filter_state_for(state, agent))
            for agent in decision.next_agents
        ]

    except Exception as e:
        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Router: LLM fallback failed ({e}), ending workflow"
        })
        return END
