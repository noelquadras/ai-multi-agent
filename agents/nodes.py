"""
LangGraph agent nodes - each agent is implemented as a node function.
Supports both Ollama (local) and Groq (cloud) LLMs.
"""

import re
import os
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from agents.state import AgentState
from database import emit_event, get_task_status, update_decision_signal
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
    global _ollama_llm
    if _ollama_llm is None:
        _ollama_llm = ChatOllama(
            model="mistral:7b-instruct",
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


def get_llm(for_heavy_task: bool = False):
    """
    Get the appropriate LLM based on configuration and task type.
    
    Args:
        for_heavy_task: If True, use the heavy-duty model (Groq for code gen).
                       If False, can use lighter model for simple tasks.
    """
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
        llm = get_llm(for_heavy_task=True)
        response = llm.invoke(messages)
        code = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Generated {len(code)} characters of code"
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
def code_reviewer_node(state: AgentState) -> AgentState:
    """Review generated code for issues."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "reviewer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START reviewer]"
    })
    
    prompt = f"""You are an Expert QA and Security Auditor.
Review the following code critically:

{state['generated_code']}

You MUST output in exactly this structured format:

### Summary
- Brief overview of code quality (2-3 sentences)

### Detailed Review
- List specific issues, bugs, or security concerns
- Mention style or maintainability problems
- Note any missing error handling

### Final Recommendations
- Bullet list of concrete improvements the refiner must apply

DO NOT write code.
DO NOT rewrite the solution.
DO NOT add extra sections.
"""
    
    messages = [
        SystemMessage(content="You are a meticulous code reviewer focused on security, bugs, and best practices."),
        HumanMessage(content=prompt)
    ]
    
    try:
        # Use local model for review (cheaper)
        llm = get_llm(for_heavy_task=False)
        response = llm.invoke(messages)
        review = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Review completed: {len(review)} characters"
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
    """Decide if code needs refinement."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "decision"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START decision]"
    })
    
    prompt = f"""Analyze ONLY the code below:

{state['generated_code']}

Question: Does the code have bugs, security vulnerabilities, or incorrect behavior?

STRICT OUTPUT RULE:
Output ONLY ONE WORD: YES or NO
NO punctuation. NO explanation. NO additional text.
"""
    
    messages = [
        SystemMessage(content="You are a deterministic decision auditor. Output only YES or NO."),
        HumanMessage(content=prompt)
    ]
    
    try:
        # 1. Check for Manual Override Signal (Approve/Reject from UI)
        db_state = get_task_status(state["task_id"])
        decision_signal = db_state.get("decision_signal") if db_state else None
        
        if decision_signal == "APPROVED":
            decision = "NO"
            emit_event(state["task_id"], {
                "type": "log",
                "message": "🚦 Human Signal: APPROVED (Skipping Refinement)"
            })
            # Clear signal
            update_decision_signal(state["task_id"], None)
            
        elif decision_signal == "REJECTED":
            decision = "YES"
            emit_event(state["task_id"], {
                "type": "log",
                "message": "🚦 Human Signal: REJECTED (Forcing Refinement)"
            })
            # Clear signal
            update_decision_signal(state["task_id"], None)
            
        else:
            # 2. Automated Decision (LLM)
            # Use local model for decision (simple task)
            llm = get_llm(for_heavy_task=False)
            response = llm.invoke(messages)
            decision = response.content.strip().upper()
        
        # Ensure it's YES or NO
        if "YES" in decision:
            decision = "YES"
        elif "NO" in decision:
            decision = "NO"
        else:
            decision = "YES"  # Default to refinement if unclear
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Decision: {decision}"
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
            "current_agent": "decision",
            "messages": state.get("messages", []) + messages + [response],
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
    
    prompt = f"""You are a Code Refiner specializing in fixing bugs and applying improvements.

Original Code:
{state['generated_code']}

Review Feedback:
{state['review_report']}

CLI Test Results (if any):
{state.get('test_results', 'No test results available.')}

Your task:
1. Read the original code
2. Read the review feedback carefully
3. Fix bugs identified in the Review Feedback AND any errors shown in the CLI Test Results.
4. Output ONLY the corrected code in a single code block

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
        llm = get_llm(for_heavy_task=True)
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
            "iteration_count": state.get("iteration_count", 0) + 1
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
        llm = get_llm(for_heavy_task=False)
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
        "message": "$ python main.py",
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
        "current_agent": "tester",
        "iteration_count": state.get("iteration_count", 0) + 1
    }


# ==========================================
# CONDITIONAL EDGE: Should Refine?
# ==========================================
def should_refine(state: AgentState) -> str:
    """
    Determine next node based on decision.
    
    Returns:
        "refine" if code needs refinement
        "document" if code is good enough to skip refinement
    """
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
# CONDITIONAL EDGE: Should Refine after Testing?
# ==========================================
def should_refine_after_test(state: AgentState) -> str:
    """
    Decide if we should go to documentation or loop back for fixes.
    """
    results = state.get("test_results", "")
    iteration_count = state.get("iteration_count", 0)

    # If the test passed, or we've tried too many times (e.g., 3), move to docs
    if "✅ Test PASSED" in results or iteration_count >= 15:
        return "document"
    
    # If it failed or timed out, send it back to the refiner
    return "refine"
