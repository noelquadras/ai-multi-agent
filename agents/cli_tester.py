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
        
        skip_msg = f"⚠️ Test SKIPPED\nReason: {language_detected} code detected\nSandbox only supports Python execution\nThe code appears syntactically valid but cannot be tested in Python sandbox."
        return {
            "test_results": skip_msg,
            "current_agent": "tester",
            "messages": [make_action_message(skip_msg, ActionType.TEST_COMPLETE, "test")],
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
        "messages": [make_action_message(
            "\n".join(test_results),
            ActionType.TEST_COMPLETE, "test"
        )],
        "iteration_count": state.get("iteration_count", 0) + 1
    }
