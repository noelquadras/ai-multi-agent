# tools/executor.py
import subprocess
import tempfile
import json
import sys
import os
import textwrap
from crewai.tools import tool

# Whitelist of safe modules (you can extend carefully)
SAFE_MODULES = ["math", "random", "statistics"]

@tool("Execute Python Code (Sandboxed)")
def execute(code: str, timeout_seconds: int = 4):
    """
    Execute `code` inside a sandbox subprocess with:
      - builtin overrides to block open/input/os.system/subprocess
      - blocked imports except SAFE_MODULES
      - timeout (timeout_seconds)
    Returns a dict: {status, returncode, stdout, stderr, details}
    """

    # 1) Create wrapper script which sets up sandboxing then execs user code
    #    We pass the user's code embedded as a JSON string for safety.
    wrapper = textwrap.dedent(
        r'''
        import json, sys, builtins, io, traceback

        USER_CODE = json.loads(r''' + json.dumps(json.dumps(code)) + r''')

        # ----------------------------
        # Replace dangerous builtins
        # ----------------------------
        def disabled_input(*args, **kwargs):
            raise RuntimeError("input() is disabled in sandbox")

        def disabled_open(*args, **kwargs):
            raise RuntimeError("open() is disabled in sandbox")

        builtins.input = disabled_input
        builtins.open = disabled_open

        # Block os.system, subprocess in os module after import
        try:
            import os as _os
            _os.system = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.system is disabled in sandbox"))
            _os.popen = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("os.popen is disabled in sandbox"))
        except Exception:
            pass

        # Basic import guard (allow only SAFE_MODULES)
        SAFE_MODULES = set(%s)

        _orig_import = builtins.__import__
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            # Allow internal imports (level>0)
            if level != 0:
                return _orig_import(name, globals, locals, fromlist, level)
            # Allow module if in SAFE_MODULES or is a package submodule of safe module
            base = name.split(".")[0]
            if base in SAFE_MODULES:
                return _orig_import(name, globals, locals, fromlist, level)
            raise ImportError(f"Import blocked in sandbox: {name}")

        builtins.__import__ = safe_import

        # Capture stdout and stderr
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        real_stdout, real_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out_buf, err_buf

        # Optional: set resource limits if available (unix)
        try:
            import resource
            # 64MB address space (soft)
            resource.setrlimit(resource.RLIMIT_AS, (64 * 1024 * 1024, resource.RLIM_INFINITY))
            # 2 second cpu time
            resource.setrlimit(resource.RLIMIT_CPU, (2, 4))
        except Exception:
            # resource may be unavailable on Windows or restricted envs — continue
            pass

        result = {
            "status": "error",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "traceback": None,
        }

        try:
            # Execute code in its own local namespace
            local_ns = {}
            exec(USER_CODE, {}, local_ns)
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
        ''' % (json.dumps(SAFE_MODULES))
    )

    # 2) Write wrapper to temp file and run in subprocess using same Python executable
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
            "stderr": "Execution timed out after %s seconds" % timeout_seconds
        }
    except Exception as e:
        return {
            "status": "error",
            "returncode": None,
            "stdout": "",
            "stderr": "Executor internal error: %s" % str(e)
        }
    finally:
        try:
            os.remove(wrapper_path)
        except Exception:
            pass
