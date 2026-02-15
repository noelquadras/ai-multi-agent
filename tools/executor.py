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

# Add workspace root to sys.path to ensure project imports work
if {repr(workspace_root)} not in sys.path:
    sys.path.append({repr(workspace_root)})

USER_CODE = {repr(code)}

# ----------------------------
# Replace dangerous builtins
# ----------------------------
_orig_open = builtins.open

def disabled_input(*args, **kwargs):
    raise RuntimeError("input() is disabled in sandbox")

def disabled_open(*args, **kwargs):
    raise RuntimeError("open() is disabled in sandbox")

builtins.input = disabled_input
builtins.open = disabled_open

# Block dangerous os methods
try:
    import os as _os
    _os.system = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.system is disabled"))
    _os.popen = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.popen is disabled"))
    _os.execl = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.exec is disabled"))
    _os.execle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.exec is disabled"))
    _os.execlp = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.exec is disabled"))
    _os.execv = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.exec is disabled"))
    _os.execve = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.exec is disabled"))
    _os.execvp = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.exec is disabled"))
    _os.spawn = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.spawn is disabled"))
    # We allow some file ops if needed for agent tasks? For now keep strict.
    _os.remove = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.remove is disabled"))
    _os.unlink = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.unlink is disabled"))
    _os.rmdir = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.rmdir is disabled"))
    _os.mkdir = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.mkdir is disabled"))
    _os.makedirs = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.makedirs is disabled"))
except Exception:
    pass

# Import guard - block dangerous modules
BLOCKED_MODULES = set({repr(BLOCKED_MODULES)})

_orig_import = builtins.__import__
def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    base = name.split(".")[0]
    if base in BLOCKED_MODULES:
        raise ImportError(f"Module '{{name}}' is blocked in sandbox for security")
    return _orig_import(name, globals, locals, fromlist, level)

builtins.__import__ = safe_import

# Capture stdout and stderr
out_buf = io.StringIO()
err_buf = io.StringIO()
real_stdout, real_stderr = sys.stdout, sys.stderr
sys.stdout, sys.stderr = out_buf, err_buf

result = {{
    "status": "error",
    "returncode": None,
    "stdout": "",
    "stderr": "",
    "traceback": None,
}}

try:
    # Execute code in its own local namespace
    local_ns = {{}}
    exec(USER_CODE, {{}}, local_ns)
    result["status"] = "success"
    result["returncode"] = 0
except SystemExit as e:
    # Handle sys.exit()
    code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
    result["returncode"] = code
    result["status"] = "success" if code == 0 else "error"
except BaseException as e:
    # include traceback
    tb = traceback.format_exc()
    result["status"] = "exception"
    result["returncode"] = 1
    result["traceback"] = tb
finally:
    # restore stdout/stderr
    sys.stdout, sys.stderr = real_stdout, real_stderr
    result["stdout"] = out_buf.getvalue()
    result["stderr"] = err_buf.getvalue()
    print(json.dumps(result, default=str))
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
            
            # Find the JSON object (last occurrence of { ... })
            # Since print(json.dumps) is at the end, it should be near the end.
            # It might be followed by prompts like "> "
            # Regex to capture { ... } spanning lines? No, json.dumps is single line by default.
            
            # 2. Use a Greedy Regex to find the JSON object.
            # This looks for the FIRST '{' and the LAST '}' in the entire blob,
            # ignoring the PowerShell "noise" surrounding it.
            match = re.search(r'(\{.*\})', clean_output, re.DOTALL)
            
            if match:
                candidate = match.group(1)
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    # If there's extra junk inside the braces, try to find the 
                    # shortest valid JSON string from the end (more robust)
                    try:
                        # Find the last occurrence of a closing brace
                        last_brace = candidate.rfind('}')
                        # Find the matching opening brace before it
                        first_brace = candidate.find('{')
                        parsed = json.loads(candidate[first_brace:last_brace+1])
                    except Exception:
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
