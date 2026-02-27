"""
Autonomous LLM-Driven Orchestrator (The "Hub" in Hub-and-Spoke).

Replaces the registry-first manager with a MetaGPT-inspired think→act loop.
The LLM is the primary routing authority: it creates plans, dispatches agents,
revises workflows at runtime, and decides when to terminate.

Architecture:
  - orchestrator_node():  The think→act hub. Builds context, calls LLM for
                          structured OrchestratorOutput, parses commands,
                          updates plan, sets pending_dispatches.
  - orchestrator_router(): Conditional edge that reads pending_dispatches
                           and returns Send() objects or END.

Key differences from manager.py:
  - No registry lookup — LLM decides all routing dynamically
  - Explicit PlanStep[] tracked in state
  - Structured OrchestratorCommand parsing (spawn_agent, finish_task, etc.)
  - Self-evolving: orchestrator can revise its own plan after feedback
  - Iterative: each agent return triggers another think→act cycle
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langgraph.constants import Send
from langgraph.graph import END

from agents.state import AgentState
from agents.action_types import ActionType, make_action_message
from agents.command_schemas import (
    OrchestratorOutput,
    OrchestratorCommand,
    PlanStep,
    PlanRevision,
)
from agents.llm_config import get_llm
from agents.termination import DEFAULT_TERMINATION
from database import emit_event


# ─── Constants ──────────────────────────────────────────────────────────────
MAX_ORCHESTRATOR_LOOPS = 5  # Hard cap on think→act cycles per workflow
AVAILABLE_AGENTS = {
    "spec_writer": "Writes technical specifications (PRD) from user requirements",
    "generate": "Generates code from specifications or requirements",
    "review": "Reviews code for bugs, security issues, and quality",
    "decide": "Decides if code needs refinement or is approved",
    "refine": "Fixes and improves code based on review/test feedback",
    "test": "Runs code in a sandboxed CLI environment",
    "analyze_test": "Analyzes test results and decides next action",
    "document": "Writes documentation for the final code",
}


# ─── System Prompt ──────────────────────────────────────────────────────────
_ORCHESTRATOR_SYSTEM_PROMPT = """\
You are an autonomous project orchestrator managing a team of AI agents.
Your job is to reason about the current project state, create/update execution plans,
and dispatch work to the right agents at the right time.

## Available Agents
{agent_descriptions}

## Commands You Can Emit
- spawn_agent: Dispatch work to an agent. Args: {{"agent": "<agent_name>"}}
- revise_plan: Update the execution plan. Args: {{"steps": [...], "reasoning": "..."}}
- finish_task: Mark a plan step as done. Args: {{"step_id": <int>}}
- end_workflow: Terminate the workflow. Args: {{"reason": "..."}}

## Rules
1. You MUST create a plan on your first invocation (emit revise_plan with initial steps).
2. Each cycle, emit exactly ONE spawn_agent command (plus any finish_task/revise_plan as needed).
3. Do NOT spawn multiple agents in the same cycle.
4. After test failures or review rejections, you may revise the plan to add fix steps.
5. End the workflow only when all plan steps are done OR you've hit the iteration cap.
6. Maximum {max_loops} orchestration cycles allowed. Current cycle: {current_loop}.
7. Be cost-conscious: skip unnecessary agents for simple tasks.

## Output Format
Respond with valid JSON matching this schema:
{{
  "thinking": "your chain-of-thought reasoning",
  "commands": [
    {{"command": "...", "args": {{...}}, "rationale": "..."}}
  ],
  "plan_update": null or {{"steps": [...], "reasoning": "..."}}
}}
"""

# ─── Human Prompt ───────────────────────────────────────────────────────────
_ORCHESTRATOR_HUMAN_PROMPT = """\
## Current State
- Requirements: {requirements}
- Cycle: {current_loop} / {max_loops}
- Iteration Count: {iteration_count}
- Has Spec: {has_spec}
- Has Code: {has_code}
- Has Review: {has_review}
- Has Test Results: {has_tests}
- Debug Loops: {debug_loop_count}

## Current Plan
{plan_status}

## Last Agent Output
Sender: {last_sender}
Action: {last_action}
Content (truncated): {last_content}

## Orchestrator History
{command_history}

What should happen next?
"""


# ─── Helper Functions ───────────────────────────────────────────────────────

def _format_agent_descriptions() -> str:
    """Format available agents into a readable list for the system prompt."""
    return "\n".join(
        f"- {name}: {desc}" for name, desc in AVAILABLE_AGENTS.items()
    )


def _format_plan_status(plan: list[dict] | None) -> str:
    """Format the current plan into a readable status string."""
    if not plan:
        return "No plan created yet. You MUST create one."
    
    lines = []
    for step in plan:
        status_icon = {
            "pending": "⬜",
            "in_progress": "🔄",
            "done": "✅",
            "skipped": "⏭️",
        }.get(step.get("status", "pending"), "❓")
        
        deps = step.get("depends_on", [])
        dep_str = f" (depends on: {deps})" if deps else ""
        lines.append(
            f"{status_icon} Step {step['step_id']}: [{step['status']}] "
            f"{step['description']} → agent: {step['agent']}{dep_str}"
        )
    return "\n".join(lines)


def _format_command_history(history: list[dict] | None) -> str:
    """Format past orchestrator commands for context."""
    if not history:
        return "No previous commands."
    
    # Show last 5 commands to limit context size
    recent = history[-5:]
    lines = []
    for entry in recent:
        cmd = entry.get("command", "?")
        args = entry.get("args", {})
        lines.append(f"- {cmd}({json.dumps(args)})")
    return "\n".join(lines)


def _filter_state_for(state: dict, role_name: str) -> dict:
    """
    Return a copy of state with messages filtered to only those
    relevant to the target role.

    Keeps: last 10 messages total, prioritising messages from/to
    this role. This prevents context window waste when the team grows.
    """
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

    # Deduplicate while preserving order
    seen_ids = set()
    deduped = []
    for msg in combined:
        msg_id = id(msg)
        if msg_id not in seen_ids:
            seen_ids.add(msg_id)
            deduped.append(msg)

    filtered = dict(state)
    filtered["messages"] = deduped[-10:]
    return filtered


def _get_next_plan_step(plan: list[dict]) -> dict | None:
    """Find the next actionable plan step (first pending with all deps done)."""
    done_ids = {s["step_id"] for s in plan if s["status"] in ("done", "skipped")}
    for step in plan:
        if step["status"] == "pending":
            deps = set(step.get("depends_on", []))
            if deps.issubset(done_ids):
                return step
    return None


def _apply_commands(
    state: dict,
    output: OrchestratorOutput,
    task_id: str,
) -> dict:
    """
    Process orchestrator commands and return state updates.
    
    Handles: spawn_agent, finish_task, revise_plan, end_workflow.
    Returns a dict of state updates to merge.
    """
    plan = list(state.get("plan") or [])
    history = list(state.get("orchestrator_history") or [])
    pending_dispatches: list[str] = []
    should_end = False

    for cmd in output.commands:
        # Record in history
        history.append({
            "command": cmd.command,
            "args": cmd.args,
            "rationale": cmd.rationale,
        })

        if cmd.command == "spawn_agent":
            agent_name = cmd.args.get("agent", "")
            if agent_name in AVAILABLE_AGENTS:
                pending_dispatches.append(agent_name)
                # Mark the corresponding plan step as in_progress
                for step in plan:
                    if step["agent"] == agent_name and step["status"] == "pending":
                        step["status"] = "in_progress"
                        break
                emit_event(task_id, {
                    "type": "log",
                    "message": f"🧠 Orchestrator: Dispatching to '{agent_name}' — {cmd.rationale}"
                })
            else:
                emit_event(task_id, {
                    "type": "log",
                    "message": f"⚠️ Orchestrator: Unknown agent '{agent_name}', skipping"
                })

        elif cmd.command == "finish_task":
            step_id = cmd.args.get("step_id")
            if step_id is not None:
                for step in plan:
                    if step["step_id"] == step_id:
                        step["status"] = "done"
                        emit_event(task_id, {
                            "type": "log",
                            "message": f"✅ Orchestrator: Step {step_id} marked done"
                        })
                        break

        elif cmd.command == "revise_plan":
            # Full plan replacement
            new_steps = cmd.args.get("steps", [])
            if new_steps:
                plan = []
                for i, s in enumerate(new_steps):
                    plan.append({
                        "step_id": s.get("step_id", i + 1),
                        "description": s.get("description", ""),
                        "agent": s.get("agent", ""),
                        "status": s.get("status", "pending"),
                        "depends_on": s.get("depends_on", []),
                    })
                emit_event(task_id, {
                    "type": "log",
                    "message": f"📋 Orchestrator: Plan revised with {len(plan)} steps — {cmd.args.get('reasoning', '')}"
                })

        elif cmd.command == "end_workflow":
            should_end = True
            emit_event(task_id, {
                "type": "log",
                "message": f"🏁 Orchestrator: Ending workflow — {cmd.args.get('reason', 'complete')}"
            })

    # Also apply inline plan_update if present
    if output.plan_update:
        plan = []
        for s in output.plan_update.steps:
            plan.append(s.model_dump())
        emit_event(task_id, {
            "type": "log",
            "message": f"📋 Orchestrator: Inline plan update — {output.plan_update.reasoning}"
        })

    updates = {
        "plan": plan,
        "orchestrator_history": history,
        "orchestrator_thinking": output.thinking,
        "pending_dispatches": pending_dispatches if not should_end else [],
    }

    # If ending, clear dispatches
    if should_end:
        updates["pending_dispatches"] = []

    return updates


def _parse_orchestrator_output(raw: str) -> OrchestratorOutput:
    """
    Parse the LLM's raw response into an OrchestratorOutput.
    
    Handles both clean JSON and markdown-wrapped JSON (```json ... ```).
    Falls back to a safe end_workflow command if parsing fails entirely.
    """
    import re

    # Strip markdown code fences if present
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return OrchestratorOutput.model_validate_json(cleaned)
    except Exception:
        pass

    # Try to find JSON object in the response
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            return OrchestratorOutput.model_validate_json(json_match.group())
        except Exception:
            pass

    # Absolute fallback: end workflow
    return OrchestratorOutput(
        thinking=f"Failed to parse LLM output. Raw: {raw[:200]}",
        commands=[OrchestratorCommand(
            command="end_workflow",
            args={"reason": "Failed to parse orchestrator output"},
            rationale="Parsing failure fallback",
        )],
    )


# ─── Main Node & Router ────────────────────────────────────────────────────

def orchestrator_node(state: AgentState) -> dict:
    """
    The autonomous orchestrator — think→act hub.
    
    On each invocation:
    1. Builds full context (plan, agent outputs, metrics)
    2. Calls LLM with structured output prompt
    3. Parses OrchestratorOutput commands
    4. Updates plan, sets pending_dispatches for the router
    5. Checks termination conditions
    """
    messages = state.get("messages", [])
    task_id = state.get("task_id", "unknown")
    metrics = state.get("agent_metrics", {})
    plan = state.get("plan") or []
    iteration_count = state.get("iteration_count", 0)

    # ── Metrics tracking ──────────────────────────────────────────────
    if messages:
        last_msg = messages[-1]
        sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "unknown")
        if sender not in ("unknown", "orchestrator"):
            agent_metric = metrics.get(sender, {"calls": 0, "tokens": 0})
            agent_metric["calls"] += 1
            usage = getattr(last_msg, "usage_metadata", None)
            if usage:
                agent_metric["tokens"] += usage.get("total_tokens", 0)
            elif hasattr(last_msg, "additional_kwargs") and "usage" in last_msg.additional_kwargs:
                usage = last_msg.additional_kwargs["usage"]
                agent_metric["tokens"] += usage.get("total_tokens", 0)
            metrics[sender] = agent_metric

    # ── Termination check ─────────────────────────────────────────────
    term_result = DEFAULT_TERMINATION(state)
    if term_result.should_stop:
        emit_event(task_id, {
            "type": "log",
            "message": f"🛑 Orchestrator: Termination triggered — {term_result.reason}"
        })
        return {
            "current_agent": "orchestrator",
            "agent_metrics": metrics,
            "pending_dispatches": [],
            "orchestrator_thinking": f"Terminated: {term_result.reason}",
            "iteration_count": iteration_count + 1,
        }

    # ── Check orchestrator loop cap ───────────────────────────────────
    current_loop = iteration_count + 1
    if current_loop > MAX_ORCHESTRATOR_LOOPS:
        emit_event(task_id, {
            "type": "log",
            "message": f"🛑 Orchestrator: Max loops ({MAX_ORCHESTRATOR_LOOPS}) reached, ending"
        })
        return {
            "current_agent": "orchestrator",
            "agent_metrics": metrics,
            "pending_dispatches": [],
            "orchestrator_thinking": f"Max orchestrator loops ({MAX_ORCHESTRATOR_LOOPS}) reached",
            "iteration_count": current_loop,
        }

    # ── Build context ─────────────────────────────────────────────────
    last_sender = "none"
    last_action = "none"
    last_content = "First invocation — no prior output"
    if messages:
        last_msg = messages[-1]
        last_sender = getattr(last_msg, "additional_kwargs", {}).get("sender", "unknown")
        last_action = getattr(last_msg, "additional_kwargs", {}).get("action_type", "unknown")
        last_content = last_msg.content[:500] if hasattr(last_msg, "content") else ""

    emit_event(task_id, {
        "type": "log",
        "message": f"🧠 Orchestrator: Thinking... (cycle {current_loop}/{MAX_ORCHESTRATOR_LOOPS})"
    })

    # ── LLM call ──────────────────────────────────────────────────────
    try:
        llm = get_llm(
            for_heavy_task=False,
            base_model=state.get("model", "ollama"),
        )

        system_prompt = _ORCHESTRATOR_SYSTEM_PROMPT.format(
            agent_descriptions=_format_agent_descriptions(),
            max_loops=MAX_ORCHESTRATOR_LOOPS,
            current_loop=current_loop,
        )

        human_prompt = _ORCHESTRATOR_HUMAN_PROMPT.format(
            requirements=state.get("requirements", "")[:1000],
            current_loop=current_loop,
            max_loops=MAX_ORCHESTRATOR_LOOPS,
            iteration_count=iteration_count,
            has_spec=bool(state.get("spec_structured")),
            has_code=bool(state.get("generated_code")),
            has_review=bool(state.get("review_report")),
            has_tests=bool(state.get("test_results")),
            debug_loop_count=state.get("debug_loop_count", 0),
            plan_status=_format_plan_status(plan),
            last_sender=last_sender,
            last_action=last_action,
            last_content=last_content,
            command_history=_format_command_history(
                state.get("orchestrator_history")
            ),
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt),
        ])

        chain = prompt | llm
        raw_response = chain.invoke({})

        # Extract content from AIMessage or string
        raw_text = raw_response.content if hasattr(raw_response, "content") else str(raw_response)

        # Parse structured output
        output = _parse_orchestrator_output(raw_text)

        emit_event(task_id, {
            "type": "log",
            "message": f"🧠 Orchestrator: {len(output.commands)} command(s) — "
                       f"{', '.join(c.command for c in output.commands)}"
        })

        # Apply commands to state
        updates = _apply_commands(state, output, task_id)
        updates["current_agent"] = "orchestrator"
        updates["agent_metrics"] = metrics
        updates["iteration_count"] = current_loop

        return updates

    except Exception as e:
        emit_event(task_id, {
            "type": "log",
            "message": f"❌ Orchestrator: LLM call failed — {e}"
        })
        return {
            "current_agent": "orchestrator",
            "agent_metrics": metrics,
            "pending_dispatches": [],
            "orchestrator_thinking": f"LLM error: {e}",
            "iteration_count": current_loop,
        }


def orchestrator_router(state: AgentState):
    """
    Conditional edge function — reads pending_dispatches from orchestrator_node
    and returns Send() objects or END.
    
    This is the routing authority: the orchestrator_node sets WHAT to dispatch,
    this function executes the dispatch via LangGraph's Send().
    """
    pending = state.get("pending_dispatches") or []
    task_id = state.get("task_id", "unknown")

    if not pending:
        # Check if the plan is fully done
        plan = state.get("plan") or []
        all_done = plan and all(
            s.get("status") in ("done", "skipped") for s in plan
        )
        if all_done and plan:
            emit_event(task_id, {
                "type": "log",
                "message": "🏁 Orchestrator Router: All plan steps complete → END"
            })
        else:
            emit_event(task_id, {
                "type": "log",
                "message": "🏁 Orchestrator Router: No pending dispatches → END"
            })
        return END

    emit_event(task_id, {
        "type": "log",
        "message": f"🧠 Orchestrator Router: Dispatching to {pending}"
    })

    return [
        Send(agent, _filter_state_for(state, agent))
        for agent in pending
        if agent in AVAILABLE_AGENTS
    ]
