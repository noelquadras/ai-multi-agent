"""
LangGraph agent nodes - each agent is implemented as a node function.
Supports both Ollama (local) and Groq (cloud) LLMs.
"""

import re
import os
import json
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_ollama import ChatOllama
from agents.state import AgentState
from agents.schemas import ReviewOutput, AnalysisOutput, DecisionOutput
from agents.termination import DEFAULT_TERMINATION
from database import emit_event, get_task_status, update_decision_signal, clear_decision_signal, get_rejection_feedback, update_rejection_feedback
import time
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


def check_interrupts(task_id: str):
    """
    Checks DB for pause status and waits if paused.
    To be called at the start of every node.
    """
    while True:
        state = get_task_status(task_id)
        if not state:
            break
        
        status = state.get("status")
        if status == "paused":
            # Just wait
            time.sleep(1)
            continue
        
        if status == "failed" or status == "completed":
            # Stop processing
            raise Exception(f"Task stopped with status: {status}")
            
        break



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


# ==========================================
# NODE 1: CODE GENERATOR
# ==========================================
def code_generator_node(state: AgentState) -> AgentState:
    """Generate initial code based on requirements."""
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
    
    prompt = f"""You are a Senior Software Developer.
Generate complete, runnable PYTHON code for the following requirements:

{state['requirements']}

CRITICAL OUTPUT FORMAT:
```python
# your code here
```

STRICT RULES:
- Start IMMEDIATELY with ```python (no text before it)
- Write ONLY Python code inside the block
- End with ``` (no text after it)
- NO explanations, NO comments outside the code block
- Code must be syntactically correct and runnable
- MUST be Python 3.11+ compatible
- DO NOT use input(), open(), or file I/O (sandbox restrictions)
- Use print() to show output

FORBIDDEN:
❌ "Here's a solution..."
❌ "This code does..."
❌ Text before or after the code block
✅ Start directly with: ```python
"""
    
    messages = [
        SystemMessage(content="You are an expert code generator focused on clean, maintainable code."),
        HumanMessage(content=prompt)
    ]
    
    try:
        # Use heavy-duty model for code generation
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("coder", ""))
        response = llm.invoke(messages)
        code = response.content
        
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
            **state,
            "generated_code": code,
            "current_agent": "coder",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code generation failed: {str(e)}"
        })
        return {
            **state,
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
    
    parser = PydanticOutputParser(pydantic_object=ReviewOutput)
    
    prompt = f"""You are an Expert QA and Security Auditor.
Review the following code critically:

{state['generated_code']}

DO NOT write code. DO NOT rewrite the solution.

{parser.get_format_instructions()}
"""
    
    messages = [
        SystemMessage(content="You are a meticulous code reviewer focused on security, bugs, and best practices."),
        HumanMessage(content=prompt)
    ]
    
    try:
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("reviewer", ""))
        response = llm.invoke(messages)
        
        # Parse structured output, fall back to raw string
        review_output_dict = None
        try:
            result: ReviewOutput = parser.parse(response.content)
            review_output_dict = result.model_dump()
            review = result.model_dump_json(indent=2)  # pretty JSON for SSE display
        except Exception:
            # Fallback: LLM didn't produce valid JSON
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
        
        return {
            **state,
            "review_report": review,
            "review_report_structured": review_output_dict,
            "current_agent": "reviewer",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code review failed: {str(e)}"
        })
        return {
            **state,
            "error": str(e),
            "current_agent": "reviewer"
        }


# ==========================================
# NODE 3: DECISION MAKER
# ==========================================
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
            # 3. Fallback: LLM decision (only when structured data is unavailable)
            parser = PydanticOutputParser(pydantic_object=DecisionOutput)
            prompt = f"""Analyze ONLY the code below:

{state['generated_code']}

Question: Does the code have bugs, security vulnerabilities, or incorrect behavior?
Answer YES if it needs refinement, NO if it is good enough.

{parser.get_format_instructions()}
"""
            messages = [
                SystemMessage(content="You are a deterministic decision auditor."),
                HumanMessage(content=prompt)
            ]
            llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("decision", ""))
            response = llm.invoke(messages)
            
            try:
                result: DecisionOutput = parser.parse(response.content)
                decision = result.decision
                rationale = result.rationale
                decision_output_dict = result.model_dump()
            except Exception:
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
            **state,
            "decision": decision,
            "decision_output": decision_output_dict,
            "current_agent": "decision",
            "messages": state.get("messages", []),
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Decision making failed: {str(e)}"
        })
        return {
            **state,
            "decision": "YES",  # Default to refinement on error
            "error": str(e),
            "current_agent": "decision"
        }


# ==========================================
# NODE 4: CODE REFINER
# ==========================================
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
        feedback_section = f"""
User Rejection Feedback:
{user_feedback}

IMPORTANT: The user has explicitly rejected the previous code. Address their feedback above as your top priority.
"""
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"📝 User feedback received: {user_feedback[:100]}..."
        })
        # Clear feedback after reading
        update_rejection_feedback(state["task_id"], None)
    
    # Build review section — prefer structured output if available
    review_section = ""
    ro = state.get("review_report_structured")
    if ro:
        parts = [f"Verdict: {ro['verdict']}  (Score: {ro['overall_score']}/10)"]
        if ro.get("critical_issues"):
            parts.append("Critical Issues:\n" + "\n".join(f"  - {i}" for i in ro["critical_issues"]))
        if ro.get("fix_suggestions"):
            parts.append("Fix Suggestions:\n" + "\n".join(f"  - {s}" for s in ro["fix_suggestions"]))
        review_section = "\n".join(parts)
    else:
        review_section = state["review_report"]

    # Build analysis section — prefer structured output if available
    analysis_section = ""
    ao = state.get("analysis_structured")
    if ao:
        parts = [f"Verdict: {ao['verdict']}"]
        if ao["verdict"] == "FIX_REQUIRED":
            parts.append(f"Error Type: {ao['error_type']}")
            parts.append(f"Root Cause: {ao['root_cause']}")
            if ao.get("fix_hints"):
                parts.append("Fix Hints:\n" + "\n".join(f"  - {h}" for h in ao["fix_hints"]))
        analysis_section = "\n".join(parts)
    else:
        analysis_section = state.get("analysis", "No analysis available.")

    prompt = f"""You are a Code Refiner specializing in fixing bugs and applying improvements.

Original Code:
{state['generated_code']}

Review Feedback:
{review_section}

CLI Test Results (if any):
{state.get('test_results', 'No test results available.')}

Analyzer Feedback (if any):
{analysis_section}
{feedback_section}
Your task:
1. Read the original code
2. Read the review feedback carefully
3. Fix bugs identified in the Review Feedback AND any errors shown in the CLI Test Results.
4. If user feedback is provided, address it as the TOP priority.
5. Output ONLY the corrected code in a single code block

STRICT OUTPUT RULE:
- Output ONLY a single fenced code block
- NO explanations
- NO comments about what you changed
- Just the final, corrected code
"""
    
    messages = [
        SystemMessage(content="You are a refactoring specialist who fixes code based on feedback."),
        HumanMessage(content=prompt)
    ]
    
    try:
        # Use heavy-duty model for refining
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("refiner", ""))
        response = llm.invoke(messages)
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
        
        return {
            **state,
            "refined_code": refined_code,
            "current_agent": "refiner",
            "messages": state.get("messages", []) + messages + [response],
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
            **state,
            "refined_code": state["generated_code"],  # Fallback to original
            "error": str(e),
            "current_agent": "refiner"
        }


# ==========================================
# NODE 5: DOCUMENTATION WRITER
# ==========================================
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
    
    prompt = f"""You are a Senior Technical Writer.

Write PROFESSIONAL documentation for the following code:

{final_code}

Documentation MUST include:
• **Overview**: What the code does
• **Features**: Key functionality
• **Requirements & Dependencies**: What's needed to run it
• **Installation**: How to set it up
• **Usage Examples**: How to use it
• **Implementation Details**: How it works internally
• **Known Limitations**: Any constraints
• **Future Improvements**: Potential enhancements

Output MUST be clean, well-formatted markdown suitable for a README.
"""
    
    messages = [
        SystemMessage(content="You are a documentation expert who creates clear, comprehensive technical documentation."),
        HumanMessage(content=prompt)
    ]
    
    try:
        # Use local model for documentation (cheaper)
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("doc_writer", ""))
        response = llm.invoke(messages)
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
        
        return {
            **state,
            "documentation": docs,
            "current_agent": "doc_writer",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Documentation generation failed: {str(e)}"
        })
        return {
            **state,
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
            **state,
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
    
    return {
        **state,
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
    traceback = test_output.get("traceback", "")
    
    # If successful, skip analysis — return structured PASS immediately
    if returncode == 0 and not traceback:
        pass_output = AnalysisOutput(
            verdict="PASS", error_type="none", root_cause="", fix_hints=[]
        )
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Analyzer: Code executed successfully. No fix needed."
        })
        return {
            **state,
            "analysis": "PASS",
            "analysis_structured": pass_output.model_dump(),
            "decision": "NO",
            "current_agent": "analyzer"
        }
    
    # Analyze the error with structured output
    parser = PydanticOutputParser(pydantic_object=AnalysisOutput)
    
    prompt = f"""You are a Python Debugging Expert.
    
The code executed but failed with the following output:

RETURN CODE: {returncode}

STDOUT:
{stdout}

STDERR:
{stderr}

TRACEBACK:
{traceback}

Analyze the error carefully.

{parser.get_format_instructions()}
"""

    messages = [
        SystemMessage(content="You are a smart debugger. Analyze runtime errors."),
        HumanMessage(content=prompt)
    ]
    
    try:
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("analyzer", ""))
        response = llm.invoke(messages)
        
        # Parse structured output, fall back to raw string
        analysis_output_dict = None
        try:
            result: AnalysisOutput = parser.parse(response.content)
            analysis = f"{result.verdict}: {result.root_cause}" if result.verdict == "FIX_REQUIRED" else "PASS"
            analysis_output_dict = result.model_dump()
        except Exception:
            # Fallback: LLM didn't produce valid JSON
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
            **state,
            "analysis": analysis,
            "analysis_structured": analysis_output_dict,
            "current_agent": "analyzer",
            "messages": state.get("messages", []) + messages + [response]
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
            **state,
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
        needs_fix = ao.get("verdict") == "FIX_REQUIRED"
    else:
        needs_fix = "FIX_REQUIRED" in state.get("analysis", "")

    if needs_fix:
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"🔄 Analyzer: Fix required — debug loop #{state.get('debug_loop_count', 0)}"
        })
        return "refine"

    return "document"
