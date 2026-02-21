"""
harness/evaluator.py
====================
Structured evaluation engine.

Responsibilities
----------------
* Concatenate the agent's generated code with the benchmark test harness.
* Run the combined code through the sandbox.
* Map sandbox outcomes to typed ``SampleResult`` objects — **no string matching**.
* Compute pass@k using the standard unbiased estimator from Chen et al. (2021):

        pass@k = 1 − C(n−c, k) / C(n, k)

  where n = total samples, c = passing samples, k = target k.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List

from .sandbox import run_in_sandbox
from .types import EvalConfig, SampleResult, SandboxResult


# ---------------------------------------------------------------------------
# Error-type classification
# ---------------------------------------------------------------------------

# Order matters: more specific statuses must come before broader ones.
_STATUS_TO_ERROR_TYPE: Dict[str, str] = {
    "compilation_error": "compilation_error",
    "assertion_failure": "assertion_failure",
    "timeout":           "timeout",
    "runtime_error":     "runtime_error",
    "success":           "",          # no error
}


def classify_error(sandbox_result: SandboxResult) -> str:
    """
    Map a :class:`SandboxResult` status to one of the five canonical error-type
    strings, or an empty string when the run succeeded.
    """
    return _STATUS_TO_ERROR_TYPE.get(sandbox_result.status, "runtime_error")


# ---------------------------------------------------------------------------
# Single-sample evaluation
# ---------------------------------------------------------------------------

def evaluate_sample(
    generated_code: str,
    test_code: str,
    sample_index: int,
    config: EvalConfig,
    *,
    iteration_count: int = 0,
    debug_loop_count: int = 0,
    total_tokens: int | None = None,
) -> SampleResult:
    """
    Execute one (code, test) pair in the sandbox and return a structured result.

    The function **never raises** — all unexpected failures are captured and
    returned as a ``SampleResult`` with ``final_status = "internal_agent_error"``.

    Args:
        generated_code:  The code produced by the agent (may include its own
                         imports and the function definition).
        test_code:       The benchmark's test harness code (assertions, etc.).
        sample_index:    0-based position within the k samples for this task.
        config:          Evaluation configuration.
        iteration_count: Telemetry — how many times the agent looped.
        debug_loop_count: Telemetry — how many refine→test→analyze cycles ran.
        total_tokens:    Telemetry — tokens consumed, if available.

    Returns:
        A fully-populated :class:`SampleResult`.
    """
    wall_start = time.monotonic()

    try:
        # Combine agent code with test harness, separated cleanly
        combined = _merge_code(generated_code, test_code)

        sandbox_result: SandboxResult = run_in_sandbox(
            combined,
            timeout=config.timeout_seconds,
        )

        passed = sandbox_result.status == "success"
        error_type: str | None = classify_error(sandbox_result) or None

        # Determine total/failed tests for HumanEval-style single check_fn blocks
        # Each assertion is one test; failed_tests = 1 if we know it failed
        total_tests, failed_tests = _count_tests(test_code, sandbox_result)

        final_status = _derive_final_status(passed, sandbox_result.status)

        return SampleResult(
            sample_index=sample_index,
            passed=passed,
            total_tests=total_tests,
            failed_tests=failed_tests,
            error_type=error_type,
            generated_code=generated_code,
            sandbox=sandbox_result,
            number_of_iterations=iteration_count,
            number_of_debug_loops=debug_loop_count,
            execution_time_seconds=time.monotonic() - wall_start,
            total_tokens_used=total_tokens,
            final_status=final_status,
        )

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - wall_start
        return SampleResult(
            sample_index=sample_index,
            passed=False,
            total_tests=0,
            failed_tests=1,
            error_type="internal_agent_error",
            generated_code=generated_code,
            sandbox=SandboxResult(
                status="runtime_error",
                stderr=f"Evaluator internal error: {exc}",
                execution_time_seconds=elapsed,
            ),
            number_of_iterations=iteration_count,
            number_of_debug_loops=debug_loop_count,
            execution_time_seconds=elapsed,
            total_tokens_used=total_tokens,
            final_status="internal_agent_error",
        )


# ---------------------------------------------------------------------------
# pass@k estimator
# ---------------------------------------------------------------------------

def compute_pass_at_k(n: int, c: int, k: int) -> float:
    """
    Unbiased pass@k estimator from Chen et al. (2021), Equation 1.

    ``pass@k = 1 − C(n−c, k) / C(n, k)``

    Args:
        n: Total number of samples generated per task.
        c: Number of those samples that passed.
        k: The k in pass@k (must satisfy k ≤ n).

    Returns:
        Probability in [0, 1].  Returns 0.0 for degenerate inputs.
    """
    if n < 1 or k < 1 or k > n:
        return 0.0
    if c == n:
        return 1.0
    if c == 0:
        return 0.0

    # Use log-space arithmetic to avoid integer overflow for large n
    # log C(n-c, k) − log C(n, k)
    log_num = sum(math.log(n - c - i) for i in range(k))
    log_den = sum(math.log(n - i) for i in range(k))

    return 1.0 - math.exp(log_num - log_den)


def aggregate_pass_at_k(
    sample_results_per_task: List[List[SampleResult]],
    k: int,
) -> float:
    """
    Compute the mean pass@k over all tasks.

    Args:
        sample_results_per_task: One inner list per task, each containing
                                 the k SampleResults for that task.
        k:                       Target k value.

    Returns:
        Mean pass@k in [0, 1].
    """
    if not sample_results_per_task:
        return 0.0

    scores = []
    for samples in sample_results_per_task:
        n = len(samples)
        c = sum(1 for s in samples if s.passed)
        scores.append(compute_pass_at_k(n, c, min(k, n)))

    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _merge_code(generated: str, test_code: str) -> str:
    """
    Concatenate agent code and test harness with a clear boundary.

    The newline padding ensures that if the agent forgets a trailing newline,
    the test code still parses correctly.
    """
    parts = [generated.rstrip()]
    if test_code:
        parts.append("")           # empty line separator
        parts.append(test_code.lstrip("\n"))
    return "\n".join(parts)


def _count_tests(test_code: str, result: SandboxResult) -> tuple[int, int]:
    """
    Heuristically count total and failed assertions.

    For HumanEval-style tasks there is effectively one "test block".
    We count ``assert`` statements in the test code as a proxy for total_tests.
    If the sandbox reported a failure we mark all assertions as failed
    (conservative but safe — we cannot know which assertion fired without
    a full test runner like pytest).
    """
    assert_count = test_code.count("\n    assert ") + test_code.count("\nassert ")
    total = max(assert_count, 1) if test_code else 0

    if result.status == "success":
        failed = 0
    elif result.status == "assertion_failure":
        failed = 1   # at least one failed; we cannot determine the precise count
    else:
        failed = total

    return total, failed


def _derive_final_status(passed: bool, sandbox_status: str) -> str:
    """Map a boolean pass/fail and sandbox status to a human-readable string."""
    if passed:
        return "pass"
    return {
        "compilation_error": "compilation_error",
        "assertion_failure": "assertion_failure",
        "timeout":           "timeout",
        "runtime_error":     "runtime_error",
    }.get(sandbox_status, "fail")
