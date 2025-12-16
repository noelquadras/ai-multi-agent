# tools/sandbox_subprocess.py
import subprocess
import tempfile
import sys
import os
import threading
import time
import shutil

def _set_resource_limits():
    """
    Called in child process (Unix only) before exec to limit resources.
    """
    try:
        import resource
        # Limit address space to 200MB (soft limit)
        resource.setrlimit(resource.RLIMIT_AS, (200 * 1024 * 1024, resource.RLIM_INFINITY))
        # Limit CPU time to 5 seconds
        resource.setrlimit(resource.RLIMIT_CPU, (5, 10))
        # Limit file size (bytes)
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, resource.RLIM_INFINITY))
    except Exception:
        # resource may not be available on Windows or some environments
        pass

def run_code_in_subprocess(code: str,
                           timeout: int = 8,
                           working_dir: str | None = None,
                           python_executable: str | None = None,
                           env: dict | None = None,
                           stream_consumer=None):
    """
    Execute the provided Python `code` in a temporary file inside a subprocess.
    Streams stdout/stderr line-by-line to `stream_consumer(line, is_stderr:bool)` if provided.
    Returns a dict with final status and collected output.

    Parameters:
      code: source code string to execute
      timeout: maximum total seconds to allow subprocess to run
      working_dir: directory to set as cwd inside the subprocess (or None)
      python_executable: which python to run (default: sys.executable)
      env: custom environment variables dict (merged with os.environ)
      stream_consumer: optional callable called as stream_consumer(line, is_stderr: bool)
    """

    python_executable = python_executable or sys.executable
    if working_dir is None:
        working_dir = os.getcwd()

    # Create temp directory to run in
    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    script_path = os.path.join(tmpdir, "sandbox_exec.py")

    # Wrap code to prevent interactive input and to show an explicit banner
    wrapped_code = (
        "import sys\n"
        "import builtins\n"
        "builtins.input = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('input() disabled in sandbox'))\n"
        "try:\n"
        "    # user code begins\n"
        + code.replace("\r\n", "\n")
        + "\n    # user code ends\n"
        "except Exception as __e:\n"
        "    import traceback\n"
        "    traceback.print_exc()\n"
        "    raise\n"
    )

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(wrapped_code)

    # Build the subprocess invocation
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    # On Windows, preexec_fn is not supported; on Unix, use to set resource limits
    preexec_fn = None
    if os.name != "nt":
        preexec_fn = _set_resource_limits

    # Start subprocess
    proc = subprocess.Popen(
        [python_executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=working_dir,
        env=proc_env,
        text=True,
        bufsize=1,
        preexec_fn=preexec_fn,
    )

    stdout_lines = []
    stderr_lines = []
    start_time = time.time()

    def _read_stream(stream, collect_list, is_stderr=False):
        try:
            for line in iter(stream.readline, ""):
                if line is None:
                    break
                trimmed = line.rstrip("\n")
                collect_list.append(trimmed)
                if stream_consumer:
                    try:
                        stream_consumer(trimmed, is_stderr)
                    except Exception:
                        pass
            stream.close()
        except Exception:
            pass

    # Spawn reader threads
    t_out = threading.Thread(target=_read_stream, args=(proc.stdout, stdout_lines, False), daemon=True)
    t_err = threading.Thread(target=_read_stream, args=(proc.stderr, stderr_lines, True), daemon=True)
    t_out.start()
    t_err.start()

    # Wait with timeout
    try:
        while True:
            if proc.poll() is not None:
                break
            if time.time() - start_time > timeout:
                # timeout -> kill process
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "status": "timeout",
                    "returncode": None,
                    "stdout": "\n".join(stdout_lines),
                    "stderr": "\n".join(stderr_lines) + "\n[Process killed due to timeout]",
                }
            time.sleep(0.05)

        # Ensure readers finish
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)

        return {
            "status": "finished",
            "returncode": proc.returncode,
            "stdout": "\n".join(stdout_lines),
            "stderr": "\n".join(stderr_lines),
        }
    finally:
        # Clean up temp dir (best-effort)
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
