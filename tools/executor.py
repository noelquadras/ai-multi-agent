# tools/executor.py
import subprocess
import tempfile
import sys
import os
import textwrap

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

def execute(code: str, timeout_seconds: int = 10):
    """
    Execute `code` inside a sandbox subprocess with:
      - builtin overrides to block open/input/os.system
      - blocked dangerous imports
      - timeout (timeout_seconds)
    Returns a dict: {status, returncode, stdout, stderr, details}
    """

    # Create wrapper script which sets up sandboxing then execs user code
    wrapper = f'''
import json, sys, builtins, io, traceback

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
except Exception as e:
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

    # Write wrapper to temp file and run in subprocess
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(wrapper)
        wrapper_path = tf.name

    try:
        # run subprocess
        proc = subprocess.run(
            [sys.executable, wrapper_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        # parse wrapper JSON printed to stdout
        parsed = None
        if stdout:
            try:
                parsed = json.loads(stdout.splitlines()[-1])
            except Exception:
                parsed = None

        if parsed is None:
            # fallback if wrapper failed to print expected JSON
            return {
                "status": "error",
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr or "No structured result from wrapper"
            }

        # Attach captured process stderr if any
        if stderr:
            parsed.setdefault("process_stderr", "")
            parsed["process_stderr"] += stderr

        # Put the actual subprocess return code too
        parsed["subprocess_returncode"] = proc.returncode

        return parsed

    except subprocess.TimeoutExpired as te:
        return {
            "status": "timeout",
            "returncode": None,
            "stdout": te.stdout or "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "returncode": None,
            "stdout": "",
            "stderr": f"Executor internal error: {str(e)}"
        }
    finally:
        try:
            os.remove(wrapper_path)
        except Exception:
            pass
