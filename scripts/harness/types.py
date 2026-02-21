"""
harness/types.py
================
Central home for every typed data structure used by the evaluation harness.

Using dataclasses + TypedDict keeps all contracts explicit and IDE-navigable
without pulling in a heavy validation library like pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Execution config (deterministic LLM settings)
# ---------------------------------------------------------------------------

@dataclass
class EvalConfig:
    """
    Parameters that control LLM sampling and evaluation behaviour.

    Defaults lean heavily toward determinism so benchmark runs are
    reproducible by simply re-using the same config.
    """

    model: str = "ollama"
    """Logical model key: 'ollama' | 'groq' | any specific Ollama tag."""

    temperature: float = 0.0
    """Sampling temperature.  0 = greedy / fully deterministic."""

    top_p: float = 1.0
    """Nucleus-sampling probability mass."""

    max_tokens: int = 2048
    """Hard cap on tokens the model may generate per completion."""

    seed: Optional[int] = None
    """Optional PRNG seed forwarded to the LLM (supported by some backends)."""

    timeout_seconds: int = 10
    """Per-task wall-clock timeout for the sandbox subprocess."""

    samples_per_task: int = 1
    """Number of independent completions to generate for pass@k estimation."""

    workers: int = 1
    """Number of parallel worker processes (≥2 triggers multiprocessing)."""

    def as_dict(self) -> Dict[str, Any]:
        """Return a plain dict suitable for JSON serialisation."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
            "timeout_seconds": self.timeout_seconds,
            "samples_per_task": self.samples_per_task,
            "workers": self.workers,
        }


# ---------------------------------------------------------------------------
# Sandbox execution result
# ---------------------------------------------------------------------------

@dataclass
class SandboxResult:
    """
    Raw, structured output from a single sandbox execution.

    This is produced by ``harness.sandbox`` and consumed by
    ``harness.evaluator``.  It is intentionally decoupled from any
    LLM concern.
    """

    # Categorical outcome — one of the five sentinel strings below
    status: str
    """
    One of:
      - ``success``           : process exited 0 and assertions passed
      - ``compilation_error`` : SyntaxError / IndentationError before exec
      - ``runtime_error``     : exception raised during exec (non-assertion)
      - ``assertion_failure`` : AssertionError / test-assertion failed
      - ``timeout``           : process was killed because it exceeded the limit
    """

    returncode: Optional[int] = None
    """OS-level exit code.  None if the process was forcefully killed."""

    stdout: str = ""
    """Captured standard output."""

    stderr: str = ""
    """Captured standard error (may overlap with traceback on Python)."""

    traceback: Optional[str] = None
    """Full Python traceback string, if available."""

    execution_time_seconds: float = 0.0
    """Wall-clock seconds the subprocess was alive."""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "traceback": self.traceback,
            "execution_time_seconds": round(self.execution_time_seconds, 4),
        }


# ---------------------------------------------------------------------------
# Per-sample evaluation result
# ---------------------------------------------------------------------------

@dataclass
class SampleResult:
    """
    Structured outcome for one LLM completion attempt on one task.

    All fields needed for pass@k computation and post-hoc analysis live here.
    """

    sample_index: int
    """0-based index within the k samples generated for this task."""

    passed: bool
    """True iff the sandbox returned status == 'success'."""

    total_tests: int = 0
    """Number of test assertions in the harness (1 for HumanEval-style tasks)."""

    failed_tests: int = 0
    """Number of assertions that failed (0 means all passed)."""

    error_type: Optional[str] = None
    """
    Categorised failure reason:
      compilation_error | runtime_error | assertion_failure | timeout | None
    """

    generated_code: str = ""
    """The raw code string produced by the agent."""

    sandbox: Optional[SandboxResult] = None
    """Full sandbox result attached for deep inspection."""

    # --- Telemetry ---
    number_of_iterations: int = 0
    """How many times the agent looped internally (generate → refine cycles)."""

    number_of_debug_loops: int = 0
    """Number of refine→test→analyze cycles the agent went through."""

    execution_time_seconds: float = 0.0
    """Total wall-clock seconds from agent invocation to result."""

    total_tokens_used: Optional[int] = None
    """Tokens consumed (if the LLM backend exposes this)."""

    final_status: str = "unknown"
    """
    Human-readable terminal outcome:
      pass | fail | timeout | runtime_error | compilation_error |
      assertion_failure | internal_agent_error
    """

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "passed": self.passed,
            "total_tests": self.total_tests,
            "failed_tests": self.failed_tests,
            "error_type": self.error_type,
            "generated_code": self.generated_code,
            "sandbox": self.sandbox.as_dict() if self.sandbox else None,
            "number_of_iterations": self.number_of_iterations,
            "number_of_debug_loops": self.number_of_debug_loops,
            "execution_time_seconds": round(self.execution_time_seconds, 4),
            "total_tokens_used": self.total_tokens_used,
            "final_status": self.final_status,
        }


# ---------------------------------------------------------------------------
# Per-task aggregated result
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    """
    Aggregated evaluation outcome for one benchmark task across all k samples.
    """

    task_id: str
    entry_point: str
    samples: List[SampleResult] = field(default_factory=list)
    final_status: str = "unknown"
    """
    Aggregate verdict:
      pass (≥1 sample passed) | fail | timeout | error
    """

    def any_passed(self) -> bool:
        """Return True if at least one sample passed (used for pass@1 when k=1)."""
        return any(s.passed for s in self.samples)

    def pass_count(self) -> int:
        """Return number of samples that passed."""
        return sum(1 for s in self.samples if s.passed)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "entry_point": self.entry_point,
            "samples": [s.as_dict() for s in self.samples],
            "final_status": self.final_status,
        }


# ---------------------------------------------------------------------------
# Top-level benchmark report
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkReport:
    """
    Complete top-level benchmark report written to the output JSON file.
    """

    benchmark: str
    model: str
    timestamp: str
    eval_config: EvalConfig
    tasks: List[TaskResult] = field(default_factory=list)

    # --- Computed summary fields (populated after all tasks complete) ---
    total_tasks: int = 0
    pass_at_1: float = 0.0
    pass_at_k: float = 0.0
    avg_latency: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "model": self.model,
            "timestamp": self.timestamp,
            "eval_config": self.eval_config.as_dict(),
            "summary": {
                "total_tasks": self.total_tasks,
                "pass_at_1": round(self.pass_at_1, 4),
                "pass_at_k": round(self.pass_at_k, 4),
                "avg_latency": round(self.avg_latency, 4),
            },
            "tasks": [t.as_dict() for t in self.tasks],
        }
