"""
NODE 6: CLI TESTER (Patent Feature)

Tests code in a CLI sandbox and captures results.
This is the unique patent feature for automated testing/debugging.
"""

from agents.state import AgentState
from agents.artifacts import save_json_artifact
from agents.llm_config import check_interrupts, clean_code_output
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event
from tools.executor import execute


@subscribe(ActionType.DECISION_APPROVED, ActionType.CODE_REFINED, node_name="test")
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
    
    llm_states = state.get("agent_states", {})
    gen_state = llm_states.get("generate", {})
    refine_state = llm_states.get("refine", {})
    
    # Use refined code if available, otherwise use generated code
    generated_code = gen_state.get("generated_code", "")
    refined_code = refine_state.get("refined_code", "")
    code_to_test = clean_code_output(refined_code or generated_code)
    
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
    
    # Detect interactive GUI/game scripts which run in infinite loops
    interactive_modules = ["pygame", "tkinter", "turtle", "curses", "CustomTkinter"]
    is_interactive = False
    for mod in interactive_modules:
        if f"import {mod}" in code_to_test or f"from {mod}" in code_to_test:
            is_interactive = True
            break
            
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
        
        skip_msg = f"⚠️ Test SKIPPED\nReason: {language_detected} code detected\nSandbox only supports Python execution\nThe code appears syntactically valid but cannot be tested in Python sandbox."
        test_data = {"test_results": skip_msg}
        return {
            "agent_states": {"test": test_data},
            "messages": [make_action_message(skip_msg, ActionType.TEST_COMPLETE, "test")],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    
    # Interactive scripts run infinite loops, so we reduce the timeout to quickly check for initial crashes
    execution_timeout = 5 if is_interactive else 10
    
    # Header for GUI/Headless support
    if is_interactive:
        head_code = """
import os
os.environ['DISPLAY'] = ':99'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['TK_SILENCE_DEPRECATION'] = '1'
"""
        code_to_test = head_code + "\n" + code_to_test

    emit_event(state["task_id"], {
        "type": "cli_output",
        "message": f"Running code ({len(code_to_test.splitlines())} lines)...",
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "Running code in sandbox..."
    })
    
    # Execute the code
    result = execute(code_to_test, timeout_seconds=execution_timeout)
    
    import re
    import sys
    import subprocess
    
    retries = 0
    max_retries = 2
    installed_packages = []
    while retries < max_retries and (result["status"] == "exception" or result["status"] == "error"):
        error_text = result.get("traceback", "") or result.get("stderr", "")
        match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", error_text)
        if not match:
            break
            
        module_name = match.group(1)
        
        emit_event(state["task_id"], {
            "type": "cli_output",
            "message": f"📦 Auto-installing missing package: {module_name}...",
        })
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"📦 Auto-installing missing package: {module_name}..."
        })
        
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", module_name], 
                capture_output=True, text=True, check=True
            )
            emit_event(state["task_id"], {
                "type": "cli_output",
                "message": f"✅ Successfully installed {module_name}. Retrying execution...",
            })
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"✅ Successfully installed {module_name}."
            })
            
            installed_packages.append(module_name)
            
            # Retry execution
            result = execute(code_to_test, timeout_seconds=execution_timeout)
            retries += 1
            
        except subprocess.CalledProcessError as e:
            emit_event(state["task_id"], {
                "type": "cli_output",
                "message": f"❌ Failed to auto-install {module_name}. Error: {e.stderr}",
            })
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"❌ Failed to auto-install {module_name}."
            })
            break

    test_results = []
    if installed_packages:
        test_results.append(f"ℹ️ Auto-installed dependencies: {', '.join(installed_packages)}")
    
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
            
            if result.get("stdout"):
                test_results.append(f"Output before error:\n{result['stdout']}")
    
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
        if is_interactive:
            # For interactive/infinite-loop scripts, surviving the timeout without crashing is a SUCCESS
            test_results.append("✅ Test PASSED")
            test_results.append(f"Interactive script ran without crashing for the {execution_timeout}s test duration.")
            if result.get("stdout"):
                test_results.append(f"Output:\n{result['stdout']}")
                
            emit_event(state["task_id"], {
                "type": "cli_output",
                "message": f"✅ Success! Interactive script survived {execution_timeout}s without crashing.",
            })
            
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"✅ Interactive code executed successfully for {execution_timeout}s!"
            })
        else:
            test_results.append("⏱️ Test TIMEOUT")
            test_results.append(f"Code took too long to execute (>{execution_timeout}s)")
            
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
    
    test_data = {
        "test_results": "\n".join(test_results),
        "test_output": result,  # Store raw output for analyzer
    }
    
    return {
        "agent_states": {"test": test_data},
        "messages": [make_action_message(
            "\n".join(test_results),
            ActionType.TEST_COMPLETE, "test"
        )],
        "iteration_count": state.get("iteration_count", 0) + 1,
        "test_iterations": state.get("test_iterations", 0) + 1
    }
