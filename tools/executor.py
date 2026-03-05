import json
import os
import sys
import shutil
import asyncio
from terminal_service import manager as terminal_manager

# Blocklist of dangerous modules that could escape the sandbox
BLOCKED_MODULES = [
    "subprocess", "multiprocessing",  # Process creation
    "socket", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib",  # Network
    "ssl", "asyncio",  # Network-related
    "ctypes", "cffi",  # Low-level access
    "pickle", "shelve", "marshal",  # Code execution via deserialization
    "importlib", "zipimport",  # Dynamic imports
    "shutil",  # File operations
    "tempfile",  # File creation
    "glob", "pathlib",  # File system traversal
    "sqlite3",  # Database access
    "webbrowser",  # Opening URLs
    "code", "codeop", "compile",  # Code execution
]

async def _execute_impl(code: str, timeout_seconds: int):
    """
    Async implementation of execute logic.
    """
    workspace_root = os.getcwd() 
    # Use ../../temp_run as requested (outside ai-multi-agent)
    temp_dir = os.path.abspath(os.path.join(workspace_root, "..", "..", "temp_run"))
    os.makedirs(temp_dir, exist_ok=True)
    
    # Create wrapper script which sets up sandboxing then execs user code
    wrapper = f'''
import json, sys, builtins, io, traceback, os
import threading
import _thread

# Add workspace root to sys.path
if {repr(workspace_root)} not in sys.path:
    sys.path.append({repr(workspace_root)})

USER_CODE = {repr(code)}

# ----------------------------
# Hardened Disabled Functions
# ----------------------------
def disabled_input(*args, **kwargs):
    # Instead of raising an error that can be caught by a generic Exception block,
    # we raise a custom BaseException so it bypasses normal catch blocks 
    # but still allows the finally block to execute and return JSON.
    class SandboxInputError(BaseException): pass
    raise SandboxInputError("SANDBOX_ERROR: input() is not allowed in automated testing. Please mock input() using unittest.mock or provide predefined inputs.")

builtins.input = disabled_input
# Do the same for open if you want it strictly disabled
# builtins.open = ... 

# Capture stdout and stderr
out_buf = io.StringIO()
err_buf = io.StringIO()
sys.stdout, sys.stderr = out_buf, err_buf

result = {{
    "status": "error",
    "returncode": 1,
    "stdout": "",
    "stderr": "",
    "traceback": None,
}}

# Setup a hard timeout using a background thread that interrupts main
def timeout_handler():
    # Only interrupt if we haven't finished execution
    _thread.interrupt_main()

# Give the internal timeout 0.5s less than the external timeout to cleanly return JSON
internal_timeout = max(1.0, float({timeout_seconds}) - 0.5)
timer = threading.Timer(internal_timeout, timeout_handler)
timer.daemon = True
timer.start()

try:
    exec(USER_CODE, {{'__builtins__': builtins}}, {{}})
    result["status"] = "success"
    result["returncode"] = 0
except SystemExit as e:
    result["returncode"] = e.code if isinstance(e.code, int) else 0
    result["status"] = "success" if result["returncode"] == 0 else "error"
except KeyboardInterrupt:
    # This is triggered by our timer!
    result["status"] = "timeout"
    result["returncode"] = None
    result["stderr"] = f"Execution timed out after {{internal_timeout}} seconds"
except BaseException:
    result["traceback"] = traceback.format_exc()
    result["status"] = "exception"
finally:
    timer.cancel()
    # RESTORE and PRINT JSON no matter what
    final_stdout = out_buf.getvalue()
    final_stderr = err_buf.getvalue()
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    
    result["stdout"] = final_stdout
    if not result["stderr"]:
        result["stderr"] = final_stderr
    # Adding markers to help the Regex find the JSON
    print(f"__START_JSON__\\n{{json.dumps(result)}}\\n__END_JSON__")
'''
    
    import uuid
    wrapper_filename = f"agent_exec_{uuid.uuid4().hex[:8]}.py"
    wrapper_path = os.path.join(temp_dir, wrapper_filename)
    
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(wrapper)
        
    try:
        session_id = "project_terminal_v1"
        session = terminal_manager.get_or_create_session(session_id)
        
        rel_path = os.path.relpath(wrapper_path, workspace_root)
        
        # Use absolute path to avoid issues if CWD changes in terminal
        abs_path = os.path.abspath(wrapper_path)
        
        # Determine if we should cd first? 
        # "cd workspace; python rel_path" might be cleaner for display but changes CWD state permanently.
        # "python abs_path" is safe but verbose.
        # Let's try to be smart: if terminal tracks CWD, use relative. But it doesn't robustly.
        # Compromise: use absolute path for reliability.
        command = f'python "{abs_path}"'
        
        # Run command in terminal with timeout
        result_data = await session.run_command(command, timeout=float(timeout_seconds))
        
        stdout_raw = result_data["output"]
        exit_code = result_data["exit_code"]
        
        # Parse the JSON from the wrapper
        parsed = None
        if stdout_raw:
            # Strip ANSI codes logic
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_output = ansi_escape.sub('', stdout_raw)
            
            # Use this regex to extract the JSON from the mess
            # It looks for the LAST occurrence of the JSON block
            json_pattern = re.compile(r'__START_JSON__\s*(\{.*?\})\s*__END_JSON__', re.DOTALL)
            all_matches = json_pattern.findall(clean_output)

            if all_matches:
                # Take the LAST match, as previous ones might be echos or artifacts
                candidate = all_matches[-1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    pass

            # lines = clean_output.strip().splitlines()
            # for line in reversed(lines):
            #     line = line.strip()
            #     if not line: continue
            #     # Basic check if it looks like JSON
            #     if "{" in line and "}" in line:
            #         try:
            #             # Extract from first { to last }
            #             start = line.find("{")
            #             end = line.rfind("}") + 1
            #             candidate = line[start:end]
            #             parsed = json.loads(candidate)
            #             break
            #         except Exception:
            #             pass
        
        if parsed is None:
            return {
                "status": "error",
                "returncode": exit_code,
                "stdout": stdout_raw,
                "stderr": f"Wrapper failed or no JSON output. Exit code: {exit_code}"
            }
            
        parsed["subprocess_returncode"] = exit_code
        
        if "[TIMEOUT]" in stdout_raw:
             return {
                "status": "timeout",
                "returncode": None,
                "stdout": stdout_raw.replace("[TIMEOUT]", ""),
                "stderr": f"Execution timed out after {timeout_seconds} seconds"
            }
            
        return parsed

    except Exception as e:
        return {
            "status": "error",
            "returncode": None,
            "stdout": "",
            "stderr": f"Executor internal error: {str(e)}"
        }
    finally:
        try:
            if os.path.exists(wrapper_path):
                os.remove(wrapper_path)
        except Exception:
            pass

def execute(code: str, timeout_seconds: int = 10):
    """
    Synchronous wrapper for executing code in the terminal session (on the main loop).
    """
    # Check if we have a main loop
    loop = terminal_manager.main_loop
    
    if not loop:
        # Fallback: try getting running loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # We are in a thread with no loop, and manager has no loop set.
            # Create a new loop for this thread?
            # But we want to reuse session bound to main loop!
            # If manager has no main loop, we assume we are standalone script?
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            terminal_manager.set_main_loop(loop)

    # Use run_coroutine_threadsafe
    import concurrent.futures
    future = asyncio.run_coroutine_threadsafe(_execute_impl(code, timeout_seconds), loop)
    try:
        return future.result(timeout=timeout_seconds + 5) # generous timeout for wrapper overhead
    except concurrent.futures.TimeoutError:
         return {
            "status": "timeout",
            "returncode": None,
            "stdout": "",
            "stderr": f"Execution request timed out after {timeout_seconds + 5} seconds (threadsafe wait)"
        }
    except Exception as e:
         return {
            "status": "error",
            "returncode": None,
            "stdout": "",
            "stderr": f"Executor threadsafe error: {str(e)}"
        }
