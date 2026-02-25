"""
LangGraph agent nodes - each agent is implemented as a node function.
Supports both Ollama (local) and Groq (cloud) LLMs.

Refactored to use:
- llm.with_structured_output() instead of PydanticOutputParser
- trim_messages instead of manual _buffered_messages
- ChatPromptTemplate.from_messages instead of raw f-strings
- add_messages reducer (return only new messages, not full history)
"""

import re
import os
import json
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from langgraph.types import interrupt, Command
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from agents.state import AgentState
from agents.schemas import ReviewOutput, AnalysisOutput, DecisionOutput
from agents.spec_schema import SpecOutput
from agents.termination import DEFAULT_TERMINATION
from agents.artifacts import save_artifact, save_json_artifact
from agents.memory import AgentMemory
from database import emit_event, get_task_status, update_decision_signal, clear_decision_signal, get_rejection_feedback, update_rejection_feedback
from tools.executor import execute

# ===========================================
# LLM CONFIGURATION
# ===========================================

# Global LLM instances
_ollama_llm: Optional[ChatOllama] = None
_groq_llm = None
_current_model = "ollama"
_groq_api_key = ""


def get_ollama_llm():
    """Get or create Ollama LLM instance."""
    global _ollama_llm, _current_model
    
    # Determine model name
    # If _current_model is "ollama" (generic) or "groq", fallback to default
    # Otherwise use the specific model name provided (e.g. "llama3:latest")
    model_name = "mistral:7b-instruct"
    if _current_model and _current_model not in ["ollama", "groq"]:
        model_name = _current_model
        
    # Re-initialize if model changed or not initialized
    if _ollama_llm is None or getattr(_ollama_llm, "model", "") != model_name:
        print(f"Initializing Ollama with model: {model_name}")
        _ollama_llm = ChatOllama(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=0.7
        )

    return _ollama_llm


from agents.cancellation import cancellation_registry


def check_interrupts(task_id: str):
    """
    Check for cancellation and pause status using LangGraph-native primitives.

    Called at the start of every node for cooperative control:
      - **Cancellation** is still handled via the in-process
        ``cancellation_registry`` (threading.Event) because it needs
        sub-second latency.
      - **Pause** now uses ``interrupt()`` from ``langgraph.types``.
        Instead of blocking a thread in a ``while True: time.sleep(1)``
        loop, ``interrupt()`` suspends graph execution and persists the
        current state to the checkpointer.  The thread is released
        immediately.  When the UI/API resumes the task it calls
        ``graph.invoke(Command(resume=True), config)`` which re-enters
        the graph at exactly the node that was interrupted.
    """
    # 1. Cooperative cancellation (ExternalTermination pattern)
    if cancellation_registry.is_cancelled(task_id):
        raise RuntimeError(f"Task {task_id} cancelled by user")

    # 2. Check DB for terminal / paused status
    db_state = get_task_status(task_id)
    if not db_state:
        return  # Task row missing — nothing to check

    status = db_state.get("status")

    if status in ("failed", "completed", "cancelled"):
        raise RuntimeError(f"Task stopped with status: {status}")

    if status == "paused":
        # Suspend the graph without holding a thread.
        # The checkpointer persists state; the API resumes with
        # Command(resume=True) which re-enters this node.
        interrupt({"reason": "paused", "task_id": task_id})



def get_groq_llm():
    """Get or create Groq LLM instance."""
    global _groq_llm, _groq_api_key
    if _groq_llm is None and _groq_api_key:
        try:
            from langchain_groq import ChatGroq
            _groq_llm = ChatGroq(
                model="llama-3.3-70b-versatile",
                api_key=_groq_api_key,
                temperature=0.7
            )
        except ImportError:
            print("Warning: langchain-groq not installed. Using Ollama.")
            return get_ollama_llm()
        except Exception as e:
            print(f"Warning: Could not initialize Groq: {e}. Using Ollama.")
            return get_ollama_llm()
    return _groq_llm or get_ollama_llm()


def set_model_config(model: str, groq_api_key: str = ""):
    """Set the model configuration for this run."""
    global _current_model, _groq_api_key, _groq_llm
    _current_model = model
    _groq_api_key = groq_api_key
    if model == "groq" and groq_api_key:
        _groq_llm = None  # Reset to force re-initialization
        get_groq_llm()  # Initialize immediately


def get_llm(for_heavy_task: bool = False, override_model: str = ""):
    """
    Get the appropriate LLM based on configuration and task type.
    
    Args:
        for_heavy_task: If True, use the heavy-duty model (Groq for code gen).
                       If False, can use lighter model for simple tasks.
        override_model: If provided, specific model ID to use.
    """
    # 1. Use override model if provided
    if override_model:
        if "groq" in override_model.lower() or "llama" in override_model.lower():
            # It's likely a cloud/groq model
             if _groq_api_key:
                from langchain_groq import ChatGroq
                # Use the specific model name if possible, or fallback to default groq
                model_name = "llama-3.3-70b-versatile"
                return ChatGroq(model=model_name, api_key=_groq_api_key, temperature=0.7)
        
        # Assume it's a local Ollama model
        return ChatOllama(
            model=override_model,
            base_url="http://localhost:11434",
            temperature=0.7
        )

    # 2. Fallback to global default logic
    if _current_model == "groq" and for_heavy_task:
        return get_groq_llm()
    return get_ollama_llm()


def clean_code_output(text: str) -> str:
    """Extract code from markdown code blocks, ignoring text outside blocks."""
    if not text:
        return ""
    
    # Try to find code between triple backticks
    # Pattern: ```language\ncode\n```
    code_block_pattern = r"```(?:[a-zA-Z]+)?\s*\n(.*?)```"
    matches = re.findall(code_block_pattern, text, re.DOTALL)
    
    if matches:
        # Return the first code block found
        return matches[0].strip()
    
    # Fallback: if no code blocks found, try removing any explanatory text
    # and return everything after the first line that looks like code
    lines = text.split('\n')
    code_started = False
    code_lines = []
    
    for line in lines:
        # Skip explanatory text at the beginning
        if not code_started:
            # Detect start of code (import, def, class, etc.)
            if line.strip().startswith(('import ', 'from ', 'def ', 'class ', '#', '@')):
                code_started = True
                code_lines.append(line)
        else:
            code_lines.append(line)
    
    if code_lines:
        return '\n'.join(code_lines).strip()
    
    # Last resort: return as-is
    return text.strip()


# ===========================================
# NATIVE MESSAGE TRIMMING (replaces _buffered_messages)
# ===========================================

_trim = trim_messages(
    strategy="last",
    max_tokens=20,
    token_counter=len,
    start_on="human",
    include_system=True,
)


def _trimmed_invoke(llm, messages: list):
    """Trim messages to fit context window, then invoke the LLM."""
    trimmed = _trim.invoke(messages)
    return llm.invoke(trimmed)


# ==========================================
# NODE 0: SPEC WRITER (MetaGPT artifact-first)
# ==========================================

_spec_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a software architect who writes concise, actionable technical specs."),
    ("human", (
        "You are a Senior Software Architect.\n"
        "Given the requirements below, produce a concise technical specification.\n\n"
        "Requirements:\n{requirements}\n\n"
        "The spec must cover:\n"
        "1. Implementation approach — what strategy, libraries, and patterns to use\n"
        "2. File list — always [\"solution.py\"] for a single-file solution\n"
        "3. Class/function design — plain-English outline of the key abstractions\n"
        "4. Key edge cases — things the implementation MUST handle\n"
        "5. Complexity estimate — \"simple\", \"medium\", or \"complex\""
    )),
])


def spec_writer_node(state: AgentState) -> AgentState:
    """
    Produce a technical spec BEFORE code generation.
    
    Gives the code generator explicit architectural direction instead of
    letting the LLM invent everything from a raw requirements string.
    Persists the spec to disk (MetaGPT artifact-first pattern).
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "spec_writer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_START spec_writer]"
    })
    
    # Persist requirement text as the first artifact
    save_artifact(state["task_id"], "requirement.txt", state["requirements"])
    
    messages = _spec_writer_prompt.format_messages(requirements=state["requirements"])
    
    try:
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("spec_writer", ""))
        structured_llm = llm.with_structured_output(SpecOutput)
        
        spec_structured = None
        spec_doc_path = None
        try:
            spec: SpecOutput = structured_llm.invoke(messages)
            spec_structured = spec.model_dump()
            
            # Persist to disk (MetaGPT artifact-first pattern)
            from pathlib import Path
            spec_path = Path(f"tasks/{state['task_id']}/spec/design.json")
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(spec.model_dump_json(indent=2))
            spec_doc_path = str(spec_path)
            
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Spec written: {spec.complexity_estimate} complexity, "
                           f"{len(spec.key_edge_cases)} edge cases identified"
            })
        except Exception as parse_err:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Structured spec extraction failed, continuing without: {parse_err}"
            })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "spec_writer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END spec_writer]"
        })
        
        # Return only new messages — add_messages reducer handles appending
        return {
            "spec_doc_path": spec_doc_path,
            "spec_structured": spec_structured,
            "current_agent": "spec_writer",
            "messages": messages,  # new messages only; reducer appends
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Spec writer failed: {str(e)}"
        })
        # Non-fatal — downstream generate will still work without a spec
        return {
            "spec_doc_path": None,
            "spec_structured": None,
            "error": str(e),
            "current_agent": "spec_writer"
        }


# ==========================================
# NODE 1: CODE GENERATOR
# ==========================================

_code_generator_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert code generator focused on clean, maintainable code."),
    ("human", (
        "You are a Senior Software Developer.\n"
        "Generate complete, runnable PYTHON code for the following requirements:\n\n"
        "{requirements}\n"
        "{spec_section}\n\n"
        "CRITICAL OUTPUT FORMAT:\n"
        "```python\n"
        "# your code here\n"
        "```\n\n"
        "STRICT RULES:\n"
        "- Start IMMEDIATELY with ```python (no text before it)\n"
        "- Write ONLY Python code inside the block\n"
        "- End with ``` (no text after it)\n"
        "- NO explanations, NO comments outside the code block\n"
        "- Code must be syntactically correct and runnable\n"
        "- MUST be Python 3.11+ compatible\n"
        "- DO NOT use input(), open(), or file I/O (sandbox restrictions)\n"
        "- Use print() to show output\n"
        "- Do NOT leave TODOs or placeholder comments\n\n"
        "FORBIDDEN:\n"
        "❌ \"Here's a solution...\"\n"
        "❌ \"This code does...\"\n"
        "❌ Text before or after the code block\n"
        "✅ Start directly with: ```python"
    )),
])


def code_generator_node(state: AgentState) -> AgentState:
    """Generate initial code based on requirements and optional spec."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "coder"
    })
    
    model_name = state.get("model", "ollama")
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START coder] (using {model_name})"
    })
    
    # Build spec section if available
    spec_section = ""
    if state.get("spec_structured"):
        spec = SpecOutput(**state["spec_structured"])
        spec_section = (
            "\n--- TECHNICAL SPEC (follow this!) ---\n"
            f"- Approach: {spec.implementation_approach}\n"
            f"- Classes/Functions: {spec.class_design}\n"
            f"- Must handle: {', '.join(spec.key_edge_cases)}\n"
            f"- Complexity: {spec.complexity_estimate}\n"
            "---"
        )
    
    messages = _code_generator_prompt.format_messages(
        requirements=state["requirements"],
        spec_section=spec_section,
    )
    
    try:
        # Use heavy-duty model for code generation
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("coder", ""))
        response = _trimmed_invoke(llm, messages)
        code = response.content
        
        # Persist artifact to disk
        save_artifact(state["task_id"], "code/solution.py", clean_code_output(code))
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Generated {len(code)} characters of code"
        })
        
        # EMIT GENERATED CODE FOR FRONTEND PREVIEW
        emit_event(state["task_id"], {
            "type": "code_output",
            "agent": "coder",
            "code": clean_code_output(code)
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "coder"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END coder]"
        })
        
        return {
            "generated_code": code,
            "current_agent": "coder",
            "messages": [response],  # new messages only
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code generation failed: {str(e)}"
        })
        return {
            "error": str(e),
            "current_agent": "coder"
        }


# ==========================================
# NODE 2: CODE REVIEWER
# ==========================================
def _format_review_output(review: ReviewOutput) -> str:
    """Format a ReviewOutput into a human-readable markdown string."""
    lines = []
    lines.append(f"### Verdict: {review.verdict}  (Score: {review.overall_score}/10)")
    if review.critical_issues:
        lines.append("\n### Critical Issues")
        for issue in review.critical_issues:
            lines.append(f"- ❌ {issue}")
    if review.minor_issues:
        lines.append("\n### Minor Issues")
        for issue in review.minor_issues:
            lines.append(f"- ⚠️ {issue}")
    if review.fix_suggestions:
        lines.append("\n### Fix Suggestions")
        for suggestion in review.fix_suggestions:
            lines.append(f"- 🔧 {suggestion}")
    return "\n".join(lines)


_code_reviewer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a meticulous code reviewer focused on security, bugs, and best practices."),
    ("human", (
        "You are an Expert QA and Security Auditor.\n"
        "Review the following code critically:\n\n"
        "{generated_code}\n\n"
        "DO NOT write code. DO NOT rewrite the solution."
    )),
])


def code_reviewer_node(state: AgentState) -> AgentState:
    """Review generated code for issues using structured Pydantic output."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "reviewer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START reviewer]"
    })
    
    messages = _code_reviewer_prompt.format_messages(generated_code=state["generated_code"])
    
    try:
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("reviewer", ""))
        structured_llm = llm.with_structured_output(ReviewOutput)
        
        # Parse structured output, fall back to raw string
        review_output_dict = None
        try:
            result: ReviewOutput = structured_llm.invoke(messages)
            review_output_dict = result.model_dump()
            review = result.model_dump_json(indent=2)  # pretty JSON for SSE display
        except Exception:
            # Fallback: with_structured_output failed, try raw invoke
            response = _trimmed_invoke(llm, messages)
            review = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Review completed: {len(review)} characters"
                       + (f" (structured, score={review_output_dict['overall_score']})"
                          if review_output_dict else " (raw)")
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "reviewer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END reviewer]"
        })
        
        # Persist review artifact
        n = state.get("iteration_count", 0)
        if review_output_dict:
            save_json_artifact(state["task_id"], f"reviews/review_{n:03d}.json", review_output_dict)
        else:
            save_artifact(state["task_id"], f"reviews/review_{n:03d}.txt", review)
        
        return {
            "review_report": review,
            "review_report_structured": review_output_dict,
            "current_agent": "reviewer",
            "messages": messages,  # new messages only
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code review failed: {str(e)}"
        })
        return {
            "error": str(e),
            "current_agent": "reviewer"
        }


# ==========================================
# NODE 3: DECISION MAKER
# ==========================================

_decision_maker_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a deterministic decision auditor."),
    ("human", (
        "Analyze ONLY the code below:\n\n"
        "{generated_code}\n\n"
        "Question: Does the code have bugs, security vulnerabilities, or incorrect behavior?\n"
        "Answer YES if it needs refinement, NO if it is good enough."
    )),
])


def decision_maker_node(state: AgentState) -> AgentState:
    """
    Decide if code needs refinement.
    
    Deterministic path: if structured review data is available, reads
    review.verdict directly — no LLM call needed.
    Fallback: calls the LLM only when structured review data is missing.
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "decision"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START decision]"
    })
    
    try:
        # 1. Check for Manual Override Signal (Approve/Reject from UI)
        db_state = get_task_status(state["task_id"])
        decision_signal = db_state.get("decision_signal") if db_state else None
        
        decision_output_dict = None
        
        if decision_signal == "APPROVED":
            decision = "NO"
            rationale = "Human override: APPROVED"
            emit_event(state["task_id"], {
                "type": "log",
                "message": "🚦 Human Signal: APPROVED (Skipping Refinement)"
            })
            update_decision_signal(state["task_id"], None)
            
        elif decision_signal == "REJECTED":
            decision = "YES"
            rationale = "Human override: REJECTED"
            emit_event(state["task_id"], {
                "type": "log",
                "message": "🚦 Human Signal: REJECTED (Forcing Refinement)"
            })
            update_decision_signal(state["task_id"], None)
            
        elif state.get("review_report_structured"):
            # 2. Deterministic decision from structured review — NO LLM call
            review = ReviewOutput(**state["review_report_structured"])
            decision = "YES" if review.verdict == "NEEDS_REFINE" else "NO"
            rationale = (f"Deterministic: verdict={review.verdict}, "
                         f"score={review.overall_score}/10, "
                         f"{len(review.critical_issues)} critical issue(s)")
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"⚡ Deterministic decision from structured review (no LLM call)"
            })
        else:
            # 3. Fallback: LLM decision with structured output
            messages = _decision_maker_prompt.format_messages(
                generated_code=state["generated_code"]
            )
            llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("decision", ""))
            structured_llm = llm.with_structured_output(DecisionOutput)
            
            try:
                result: DecisionOutput = structured_llm.invoke(messages)
                decision = result.decision
                rationale = result.rationale
                decision_output_dict = result.model_dump()
            except Exception:
                # Fallback: structured output failed, try raw invoke
                response = _trimmed_invoke(llm, messages)
                decision = response.content.strip().upper()
                rationale = "Parsed from raw LLM output"
        
        # Normalise to YES / NO
        if "YES" in decision:
            decision = "YES"
        elif "NO" in decision:
            decision = "NO"
        else:
            decision = "YES"  # Default to refinement if unclear
        
        # Build decision_output_dict if not already set
        if decision_output_dict is None:
            decision_output_dict = DecisionOutput(
                decision=decision,
                rationale=rationale
            ).model_dump()
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Decision: {decision} — {rationale}"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "decision"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END decision]"
        })
        
        return {
            "decision": decision,
            "decision_output": decision_output_dict,
            "current_agent": "decision",
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Decision making failed: {str(e)}"
        })
        return {
            "decision": "YES",  # Default to refinement on error
            "error": str(e),
            "current_agent": "decision"
        }


# ==========================================
# NODE 4: CODE REFINER
# ==========================================

_code_refiner_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a refactoring specialist who fixes code based on feedback."),
    ("human", (
        "You are a Code Refiner. Your ONLY job is to output fixed, runnable Python code.\n"
        "{memory_ctx}\n"
        "{structured_review_section}\n"
        "{sandbox_section}\n"
        "{user_feedback_section}\n"
        "## Code to fix:\n"
        "```python\n"
        "{code_to_fix}\n"
        "```\n\n"
        "Rules:\n"
        "1. Fix EVERY critical issue and ALL fix suggestions listed above.\n"
        "2. Fix the sandbox error if one is shown.\n"
        "3. If user feedback is provided, address it first.\n"
        "4. If previous failed attempts are listed, do NOT repeat the same fix — try a different approach.\n"
        "5. Output ONLY a single fenced ```python … ``` block. No prose, no comments outside the block."
    )),
])


def code_refiner_node(state: AgentState) -> AgentState:
    """Refine code based on review feedback."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "refiner"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START refiner]"
    })
    
    # Get user rejection feedback if any
    user_feedback = get_rejection_feedback(state["task_id"])
    feedback_section = ""
    if user_feedback:
        feedback_section = (
            f"\nUser Rejection Feedback:\n{user_feedback}\n\n"
            "IMPORTANT: The user has explicitly rejected the previous code. "
            "Address their feedback above as your top priority."
        )
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"📝 User feedback received: {user_feedback[:100]}..."
        })
        # Clear feedback after reading
        update_rejection_feedback(state["task_id"], None)
    
    # ── Structured prompt (Path A) ─────────────────────────────────────────
    # When structured data is available use it directly — no LLM re-parsing
    # of prose walls of text.
    ro = state.get("review_report_structured")
    ao = state.get("analysis_structured")

    if ro:
        review = ReviewOutput(**ro)
        critical_block = "\n".join(f"- {i}" for i in review.critical_issues) or "- None"
        suggestions_block = "\n".join(f"- {s}" for s in review.fix_suggestions) or "- None"
        score_line = f"Score: {review.overall_score}/10 | Verdict: {review.verdict}"
    else:
        # Path B fallback — raw prose
        critical_block = ""
        suggestions_block = state.get("review_report", "No review available.")
        score_line = ""

    if ao:
        analysis = AnalysisOutput(**ao)
        if analysis.verdict == "FIX_REQUIRED":
            hint_block = "\n".join(f"- {h}" for h in (analysis.fix_hints or [])) or "- No hints"
            error_block = (
                f"Error type : {analysis.error_type}\n"
                f"Root cause : {analysis.root_cause}\n"
                f"Hints      :\n{hint_block}"
            )
        else:
            error_block = "Sandbox: PASS — no runtime error."
    else:
        error_block = state.get("analysis", "No analysis available.")

    # Base code: always refine from the latest refined version, not the original
    code_to_fix = state.get("refined_code") or state["generated_code"]

    # ── Build prompt variables ──────────────────────────────────────────────
    memory_ctx = ""
    if state.get("refiner_memory"):
        mem = AgentMemory(role="refiner", entries=list(state["refiner_memory"]))
        memory_ctx = mem.as_system_context()

    if ro:
        structured_review_section = (
            f"## Code review ({score_line})\n\n"
            f"### Critical issues (ALL must be resolved):\n{critical_block}\n\n"
            f"### Fix suggestions:\n{suggestions_block}"
        )
    else:
        structured_review_section = f"## Review feedback:\n{suggestions_block}"

    sandbox_section = f"## Sandbox execution result:\n{error_block}"

    user_feedback_section = ""
    if user_feedback:
        user_feedback_section = f"## ⚠️ User rejection feedback (TOP PRIORITY):\n{user_feedback}"

    messages = _code_refiner_prompt.format_messages(
        memory_ctx=memory_ctx,
        structured_review_section=structured_review_section,
        sandbox_section=sandbox_section,
        user_feedback_section=user_feedback_section,
        code_to_fix=code_to_fix,
    )
    
    try:
        # Use heavy-duty model for refining
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("refiner", ""))
        response = _trimmed_invoke(llm, messages)
        refined_code = response.content
        
        # Try to execute the code if it's Python
        cleaned_code = clean_code_output(refined_code)
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Attempting to execute refined code..."
        })
        
        result = execute(cleaned_code, timeout_seconds=4)
        
        if result["status"] == "success":
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"✅ Code executed successfully!"
            })
            if result.get("stdout"):
                emit_event(state["task_id"], {
                    "type": "log",
                    "message": f"Output: {result['stdout']}"
                })
        else:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"⚠️ Execution failed: {result.get('stderr', 'Unknown error')}"
            })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "refiner"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END refiner]"
        })
        
        # Build memory entry summarising what was fixed
        issues_fixed = []
        ro = state.get("review_report_structured")
        if ro and ro.get("critical_issues"):
            issues_fixed.extend(ro["critical_issues"][:3])  # top 3
        ao = state.get("analysis_structured")
        if ao and ao.get("verdict") == "FIX_REQUIRED":
            issues_fixed.append(f"{ao['error_type']}: {ao['root_cause']}")
        if not issues_fixed:
            issues_fixed.append("general refinement from review feedback")
        
        iteration = state.get("debug_loop_count", 0)
        memory_entry = f"Iteration {iteration}: fixed [{', '.join(issues_fixed)}]"
        new_memory = (state.get("refiner_memory") or []) + [memory_entry]
        
        return {
            "refined_code": refined_code,
            "refiner_memory": new_memory,
            "current_agent": "refiner",
            "messages": [response],  # new messages only
            "iteration_count": state.get("iteration_count", 0) + 1,
            # Increment debug loop count if we were triggered by the analyzer
            "debug_loop_count": (
                state.get("debug_loop_count", 0) + 1
                if "FIX_REQUIRED" in state.get("analysis", "")
                else state.get("debug_loop_count", 0)
            ),
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code refinement failed: {str(e)}"
        })
        return {
            "refined_code": state["generated_code"],  # Fallback to original
            "error": str(e),
            "current_agent": "refiner"
        }


# ==========================================
# NODE 5: DOCUMENTATION WRITER
# ==========================================

_doc_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a documentation expert who creates clear, comprehensive technical documentation."),
    ("human", (
        "You are a Senior Technical Writer.\n\n"
        "Write PROFESSIONAL documentation for the following code:\n\n"
        "{final_code}\n\n"
        "Documentation MUST include:\n"
        "• **Overview**: What the code does\n"
        "• **Features**: Key functionality\n"
        "• **Requirements & Dependencies**: What's needed to run it\n"
        "• **Installation**: How to set it up\n"
        "• **Usage Examples**: How to use it\n"
        "• **Implementation Details**: How it works internally\n"
        "• **Known Limitations**: Any constraints\n"
        "• **Future Improvements**: Potential enhancements\n\n"
        "Output MUST be clean, well-formatted markdown suitable for a README."
    )),
])


def doc_writer_node(state: AgentState) -> AgentState:
    """Generate professional documentation."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "doc_writer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START doc_writer]"
    })
    
    # Use refined code if available, otherwise use generated code
    final_code = state.get("refined_code") or state["generated_code"]
    
    messages = _doc_writer_prompt.format_messages(final_code=final_code)
    
    try:
        # Use local model for documentation (cheaper)
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("doc_writer", ""))
        response = _trimmed_invoke(llm, messages)
        docs = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Documentation generated: {len(docs)} characters"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "doc_writer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END doc_writer]"
        })
        
        # Persist documentation artifact
        save_artifact(state["task_id"], "docs/README.md", docs)
        
        return {
            "documentation": docs,
            "current_agent": "doc_writer",
            "messages": [response],  # new messages only
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Documentation generation failed: {str(e)}"
        })
        return {
            "documentation": "# Documentation\n\nFailed to generate documentation.",
            "error": str(e),
            "current_agent": "doc_writer"
        }


# ==========================================
# NODE 6: CLI TESTER (Patent Feature)
# ==========================================
def cli_tester_node(state: AgentState) -> AgentState:
    """
    Test code in CLI and capture results.
    This is the unique patent feature for automated testing/debugging.
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "tester"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_START tester]"
    })
    
    # Use refined code if available, otherwise use generated code
    code_to_test = clean_code_output(state.get("refined_code") or state["generated_code"])
    
    # If benchmark test code is provided, append it to the code to test
    if state.get("benchmark_test_code"):
        code_to_test += "\n\n" + state["benchmark_test_code"]
    
    # Detect if this is Python code (simple heuristic)
    is_python = not any([
        code_to_test.strip().startswith("import java."),
        code_to_test.strip().startswith("package "),
        "public class " in code_to_test,
        "public static void main" in code_to_test,
        code_to_test.strip().startswith("#include "),
        code_to_test.strip().startswith("function "),
        code_to_test.strip().startswith("const "),
        code_to_test.strip().startswith("let "),
    ])
    
    if not is_python:
        # Non-Python code detected - skip execution with helpful message
        language_detected = "Unknown"
        if "public class " in code_to_test or "import java." in code_to_test:
            language_detected = "Java"
        elif "#include " in code_to_test:
            language_detected = "C/C++"
        elif "function " in code_to_test or "const " in code_to_test:
            language_detected = "JavaScript"
        
        emit_event(state["task_id"], {
            "type": "cli_output",
            "message": f"⚠️ Skipped: {language_detected} code detected (Python-only sandbox)",
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"⚠️ {language_detected} code detected - sandbox only supports Python"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "tester"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END tester]"
        })
        
        return {
            "test_results": f"⚠️ Test SKIPPED\nReason: {language_detected} code detected\nSandbox only supports Python execution\nThe code appears syntactically valid but cannot be tested in Python sandbox.",
            "current_agent": "tester",
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    
    emit_event(state["task_id"], {
        "type": "cli_output",
        "message": f"Running code ({len(code_to_test.splitlines())} lines)...",
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "Running code in sandbox..."
    })
    
    # Execute the code
    result = execute(code_to_test, timeout_seconds=10)
    
    test_results = []
    
    if result["status"] == "success" and result.get("returncode") == 0:
        test_results.append("✅ Test PASSED")
        test_results.append(f"Return code: 0")
        if result.get("stdout"):
            test_results.append(f"Output:\n{result['stdout']}")
    
        emit_event(state["task_id"], {
            "type": "cli_output",
            "message": f"✅ Success! {result.get('stdout', 'No output')}",
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Code executed successfully!"
        })
    elif result["status"] == "exception" or result["status"] == "error":
            test_results.append("❌ Test FAILED")
            test_results.append(f"Error Type: {result.get('status').upper()}")
    
            # this is the part that will show "AttributeError: 'set' object has no attribute 'count'"
            if result.get("traceback"):
                test_results.append(f"Traceback:\n{result['traceback']}")
            elif result.get("stderr"):
                test_results.append(f"Error:\n{result['stderr']}")

            emit_event (state["task_id"], {
                "type": "cli_output",
                "message": f"❌ Error: {result.get('stderr', 'Python Execution Failed')}",
            })

    elif result["status"] == "timeout":
        test_results.append("⏱️ Test TIMEOUT")
        test_results.append(f"Code took too long to execute (>10s)")
        
        emit_event(state["task_id"], {
            "type": "cli_output",
            "message": "⏱️ Timeout: Code took too long to execute",
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": "⏱️ Execution timed out"
        })
    else:
        test_results.append("❌ Test FAILED")
        test_results.append(f"Status: {result['status']}")
        if result.get("stderr"):
            test_results.append(f"Error:\n{result['stderr']}")
        if result.get("traceback"):
            test_results.append(f"Traceback:\n{result['traceback']}")
        
        emit_event(state["task_id"], {
            "type": "cli_output",
            "message": f"❌ Error: {result.get('stderr', result.get('traceback', 'Unknown error'))}",
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"❌ Execution failed: {result.get('stderr', 'Unknown error')}"
        })
    
    emit_event(state["task_id"], {
        "type": "agent_end",
        "agent": "tester"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_END tester]"
    })
    
    # Persist test output artifact
    n = state.get("iteration_count", 0)
    save_json_artifact(state["task_id"], f"test_outputs/run_{n:03d}.json", result)
    
    return {
        "test_results": "\n".join(test_results),
        "test_output": result,  # Store raw output for analyzer
        "current_agent": "tester",
        "iteration_count": state.get("iteration_count", 0) + 1
    }


# ==========================================
# CONDITIONAL EDGE: Should Refine?
# ==========================================
def should_refine(state: AgentState) -> str:
    """
    Determine next node based on decision.
    
    Reads the structured decision_output if available, otherwise
    falls back to the raw decision string.
    
    Returns:
        "refine" if code needs refinement
        "document" if code is good enough to skip refinement
    """
    do = state.get("decision_output")
    if do:
        decision = do.get("decision", "NO")
    else:
        decision = state.get("decision", "NO").upper()
    
    if "YES" in decision:
        emit_event(state["task_id"], {
            "type": "log",
            "message": "🔄 Decision: Code needs refinement"
        })
        return "refine"
    else:
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Decision: Code is good, skipping refinement"
        })
        return "document"


# ==========================================
# NODE 7: TERMINAL ANALYZER
# ==========================================

_terminal_analyzer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a smart debugger. Analyze runtime errors."),
    ("human", (
        "You are a Python Debugging Expert.\n\n"
        "The code executed but failed with the following output:\n\n"
        "RETURN CODE: {returncode}\n\n"
        "STDOUT:\n{stdout}\n\n"
        "STDERR:\n{stderr}\n\n"
        "TRACEBACK:\n{traceback}\n\n"
        "Analyze the error carefully."
    )),
])


def terminal_analyzer_node(state: AgentState) -> AgentState:
    """
    Analyze the raw terminal output to determine if code needs refinement
    and what specific fixes are required.  Uses structured Pydantic output.
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "analyzer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_START analyzer]"
    })
    
    test_output = state.get("test_output", {})
    returncode = test_output.get("returncode")
    stdout = test_output.get("stdout", "")
    stderr = test_output.get("stderr", "")
    traceback_str = test_output.get("traceback", "")
    
    # If successful, skip analysis — return structured PASS immediately
    if returncode == 0 and not traceback_str:
        pass_output = AnalysisOutput(
            verdict="PASS", error_type="none", root_cause="", fix_hints=[]
        )
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Analyzer: Code executed successfully. No fix needed."
        })
        return {
            "analysis": "PASS",
            "analysis_structured": pass_output.model_dump(),
            "decision": "NO",
            "current_agent": "analyzer"
        }
    
    # Analyze the error with structured output
    messages = _terminal_analyzer_prompt.format_messages(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        traceback=traceback_str,
    )
    
    try:
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("analyzer", ""))
        structured_llm = llm.with_structured_output(AnalysisOutput)
        
        # Parse structured output, fall back to raw string
        analysis_output_dict = None
        try:
            result: AnalysisOutput = structured_llm.invoke(messages)
            analysis = f"{result.verdict}: {result.root_cause}" if result.verdict == "FIX_REQUIRED" else "PASS"
            analysis_output_dict = result.model_dump()
        except Exception:
            # Fallback: structured output failed, try raw invoke
            response = _trimmed_invoke(llm, messages)
            analysis = response.content.strip()
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🔍 Analyzer: {analysis}"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "analyzer"
        })
         
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END analyzer]"
        })
        
        return {
            "analysis": analysis,
            "analysis_structured": analysis_output_dict,
            "current_agent": "analyzer",
            "messages": messages  # new messages only
        }
        
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Analysis failed: {str(e)}"
        })
        fallback_output = AnalysisOutput(
            verdict="FIX_REQUIRED",
            error_type="runtime",
            root_cause="Analyzer failed, please check logs manually.",
            fix_hints=[]
        )
        return {
            "analysis": "FIX_REQUIRED: Analyzer failed, please check logs manually.",
            "analysis_structured": fallback_output.model_dump(),
            "error": str(e),
            "current_agent": "analyzer"
        }


# ==========================================
# CONDITIONAL EDGE: Should Refine after Analysis?
# ==========================================
def should_refine_after_analysis(state: AgentState) -> str:
    """
    Decide based on the Analyzer's output and composable termination conditions.
    
    Uses DEFAULT_TERMINATION (iteration limit, token budget, debug loop limit)
    to guard against runaway loops before checking the analysis verdict.
    """
    # Check all termination conditions (iteration, token budget, debug loops)
    term_result = DEFAULT_TERMINATION(state)
    if term_result.should_stop:
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🛑 Stopping: {term_result.reason}"
        })
        return "document"

    # Prefer structured output
    ao = state.get("analysis_structured")
    if ao:
        verdict = ao.get("verdict", "PASS")
    else:
        analysis_text = state.get("analysis", "")
        if "REGENERATE" in analysis_text:
            verdict = "REGENERATE"
        elif "FIX_REQUIRED" in analysis_text:
            verdict = "FIX_REQUIRED"
        else:
            verdict = "PASS"

    if verdict == "REGENERATE":
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🔁 Analyzer: Approach is wrong — escalating to full REGENERATE"
        })
        return "generate"

    if verdict == "FIX_REQUIRED":
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🔄 Analyzer: Fix required — debug loop #{state.get('debug_loop_count', 0)}"
        })
        return "refine"

    return "document"
