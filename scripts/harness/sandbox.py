"""
harness/sandbox.py
==================
Production-grade isolated subprocess sandbox for executing untrusted Python.

Design goals
------------
* **No terminal_service dependency** — the benchmark must be self-contained
  and runnable without the WebSocket-backed terminal session that the live
  agent UI uses.
* **Hard timeout** — the subprocess is sent SIGTERM then SIGKILL (or
  TerminateProcess on Windows) after the configured wall-clock limit.
* **Memory limiting** — on POSIX, ``resource.setrlimit`` caps virtual address
  space.  On Windows this is silently skipped.
* **Clean environment** — a stripped-down copy of ``os.environ`` is passed,
  omitting filesystem-discovery and credentials variables.
* **Structured output** — the child process writes a JSON blob wrapped in
  sentinel markers; the parent finds it with a regex so prefix/suffix noise
  from the shell is harmless.
* **No filesystem leakage** — temp files are created in a private tmpdir
  that is deleted in a ``finally`` block even if the process is killed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Optional

from .types import SandboxResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex to locate the JSON blob this sandbox emits.
_JSON_FENCE_RE = re.compile(
    r"__BENCH_START__\s*(\{.*?\})\s*__BENCH_END__",
    re.DOTALL,
)

# Environment keys that could leak host secrets or confuse child processes.
_SCRUBBED_ENV_KEYS = {
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "HUGGINGFACE_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
}

# The runner script injected into the child process.
# It captures stdout/stderr, distinguishes error types, and emits structured JSON.
_RUNNER_TEMPLATE = """\
import sys, json, builtins, io, traceback as _tb, os as _os

# --- Sandbox hardening ---
def _disabled_input(*a, **k):
    sys.stderr.write("SANDBOX: input() disabled\\n")
    _os._exit(2)

builtins.input = _disabled_input

# --- Capture streams ---
_out = io.StringIO()
_err = io.StringIO()
sys.stdout = _out
sys.stderr = _err

_result = dict(
    status="runtime_error",
    returncode=1,
    stdout="",
    stderr="",
    traceback=None,
)

_USER_CODE = {user_code!r}

try:
    _compiled = compile(_USER_CODE, "<agent_code>", "exec")
except SyntaxError:
    _tb_str = _tb.format_exc()
    _result["status"] = "compilation_error"
    _result["traceback"] = _tb_str
else:
    try:
        exec(_compiled, {{"__builtins__": builtins}}, {{}})
        _result["status"] = "success"
        _result["returncode"] = 0
    except AssertionError:
        _result["status"] = "assertion_failure"
        _result["traceback"] = _tb.format_exc()
    except SystemExit as _se:
        _rc = _se.code if isinstance(_se.code, int) else 0
        _result["returncode"] = _rc
        _result["status"] = "success" if _rc == 0 else "runtime_error"
    except BaseException:
        _result["status"] = "runtime_error"
        _result["traceback"] = _tb.format_exc()

_result["stdout"] = _out.getvalue()
_result["stderr"] = _err.getvalue()

sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__
print(f"__BENCH_START__\\n{{json.dumps(_result)}}\\n__BENCH_END__", flush=True)
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_in_sandbox(
    code: str,
    *,
    timeout: int = 10,
    memory_limit_mb: int = 256,
) -> SandboxResult:
    """
    Execute *code* in an isolated subprocess and return a structured result.

    The function:
    1. Writes a self-contained runner script to a private temp directory.
    2. Spawns a subprocess with a stripped environment.
    3. Applies POSIX resource limits if available.
    4. Kills the process on timeout.
    5. Parses the JSON output emitted by the runner.
    6. Cleans up the temp directory unconditionally.

    Args:
        code:             Full Python source to execute (including test assertions).
        timeout:          Hard wall-clock limit in seconds.
        memory_limit_mb:  Virtual memory cap in megabytes (POSIX only).

    Returns:
        A :class:`SandboxResult` with status, outputs, and timing.
    """
    tmpdir: Optional[str] = None
    proc: Optional[subprocess.Popen] = None
    start = time.monotonic()

    try:
        # ── 1. Write runner script ──────────────────────────────────────────
        tmpdir = tempfile.mkdtemp(prefix="bench_sandbox_")
        script_path = os.path.join(tmpdir, f"run_{uuid.uuid4().hex[:8]}.py")
        runner_source = _RUNNER_TEMPLATE.format(user_code=code)
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(runner_source)

        # ── 2. Build clean environment ──────────────────────────────────────
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in _SCRUBBED_ENV_KEYS
        }
        # Prevent the child from discovering/writing to the project workspace
        env.pop("PYTHONPATH", None)

        # ── 3. Spawn subprocess ─────────────────────────────────────────────
        preexec = _make_preexec(memory_limit_mb) if os.name != "nt" else None

        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmpdir,        # chdir into the sandbox tmpdir, not the project
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            preexec_fn=preexec,
        )

        # ── 4. Wait with hard timeout ───────────────────────────────────────
        try:
            stdout_raw, stderr_raw = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process(proc)
            stdout_raw, stderr_raw = proc.communicate()
            elapsed = time.monotonic() - start
            return SandboxResult(
                status="timeout",
                returncode=None,
                stdout=stdout_raw or "",
                stderr=f"[Process killed after {timeout}s timeout]",
                traceback=None,
                execution_time_seconds=elapsed,
            )

        elapsed = time.monotonic() - start

        # ── 5. Parse JSON blob ──────────────────────────────────────────────
        parsed = _parse_output(stdout_raw)
        if parsed is None:
            # Runner itself failed (syntax error in template, OOM, etc.)
            return SandboxResult(
                status="runtime_error",
                returncode=proc.returncode,
                stdout=stdout_raw,
                stderr=stderr_raw or "Runner produced no parseable output.",
                traceback=None,
                execution_time_seconds=elapsed,
            )

        return SandboxResult(
            status=parsed.get("status", "runtime_error"),
            returncode=parsed.get("returncode"),
            stdout=parsed.get("stdout", ""),
            stderr=parsed.get("stderr", ""),
            traceback=parsed.get("traceback"),
            execution_time_seconds=elapsed,
        )

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - start
        return SandboxResult(
            status="runtime_error",
            returncode=None,
            stdout="",
            stderr=f"Sandbox internal error: {exc}",
            traceback=None,
            execution_time_seconds=elapsed,
        )
    finally:
        # ── 6. Cleanup ──────────────────────────────────────────────────────
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        if tmpdir and os.path.isdir(tmpdir):
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_output(raw: str) -> Optional[dict]:
    """Extract and parse the JSON blob from the runner's stdout."""
    if not raw:
        return None

    # Strip ANSI escape codes that some terminal drivers inject
    ansi_re = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    clean = ansi_re.sub("", raw)

    matches = _JSON_FENCE_RE.findall(clean)
    if not matches:
        return None

    # Take the last match to skip any echoed command lines
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return None


def _make_preexec(memory_limit_mb: int):
    """
    Return a callable suitable for ``subprocess.Popen(preexec_fn=...)``.

    Sets virtual-address-space and CPU-time limits via ``resource``.
    Only called on POSIX; the ``preexec_fn`` kwarg is not supported on Windows.
    """
    def _preexec() -> None:
        try:
            import resource  # type: ignore[import]
            limit_bytes = memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, resource.RLIM_INFINITY))
            # CPU time guard (hard limit slightly above timeout so OS kills it)
            resource.setrlimit(resource.RLIMIT_CPU, (30, 60))
        except Exception:
            pass  # Silently skip on environments where resource is unavailable

    return _preexec


def _kill_process(proc: subprocess.Popen) -> None:
    """Send SIGTERM then SIGKILL (or TerminateProcess on Windows)."""
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass

    time.sleep(0.1)

    try:
        proc.kill()
    except Exception:
        pass
