"""
harness/runner.py
=================
Benchmark runner — orchestrates dataset loading, agent invocation,
evaluation, and report serialisation.

Architecture
------------
* ``BenchmarkRunner`` is the central coordinator.
* Tasks may be run **sequentially** (workers=1) or in **parallel** via
  ``multiprocessing.Pool`` (workers>1).  We use *multiprocessing* (not
  threading) so each worker has its own Python interpreter, its own copies
  of global LLM state, and is fully isolated.
* The runner calls ``run_software_crew`` from ``main.py`` (your agent graph)
  for each sample, extracts the refined code, then hands it off to the
  evaluator.  It never itself calls the sandbox — that is the evaluator's job.
* No asyncio event-loop logic lives in the runner.  Each worker process calls
  ``run_software_crew`` which internally manages whatever concurrency it needs.

Failure contract
----------------
* A failure in **one task** (including an unhandled exception from the agent)
  is caught and recorded as ``final_status = "internal_agent_error"``.
* The runner never crashes the whole benchmark because of a single bad task.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ensure the project root is importable from worker processes
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from harness.dataset import (
    build_prompt,
    ensure_downloaded,
    get_entry_point,
    get_test_code,
    load_tasks,
)
from harness.evaluator import (
    aggregate_pass_at_k,
    compute_pass_at_k,
    evaluate_sample,
)
from harness.types import (
    BenchmarkReport,
    EvalConfig,
    SampleResult,
    TaskResult,
)


# ---------------------------------------------------------------------------
# Worker-level task function (must be top-level for multiprocessing pickling)
# ---------------------------------------------------------------------------

def _run_single_task(args: Tuple[Dict[str, Any], str, EvalConfig, str]) -> TaskResult:
    """
    Execute all k samples for *one* benchmark task.

    This function is designed to be called inside a worker process spawned by
    ``ProcessPoolExecutor``.  It must be a top-level function (not a lambda or
    nested function) so that ``pickle`` can serialise it.

    Args:
        args: A tuple of (task_dict, benchmark_name, eval_config, timestamp).

    Returns:
        A :class:`TaskResult` with all sample outcomes populated.
    """
    task, benchmark_name, config, timestamp = args

    task_key = task.get("task_id", "unknown")
    entry_point = get_entry_point(task, task_key)
    test_code = get_test_code(task)
    prompt = build_prompt(task, benchmark_name)
    agent_task_id = f"bench_{benchmark_name}_{task_key}_{timestamp}"

    samples: List[SampleResult] = []

    for sample_idx in range(config.samples_per_task):
        wall_start = time.monotonic()

        # --- Invoke the agent ---
        generated_code = ""
        iteration_count = 0
        debug_loop_count = 0
        total_tokens: Optional[int] = None
        agent_error: Optional[str] = None

        try:
            # Import here so each subprocess initialises its own state
            from main import run_software_crew  # type: ignore[import]

            agent_result: Dict[str, Any] = run_software_crew(
                requirements=prompt,
                task_id=f"{agent_task_id}_s{sample_idx}",
                model=config.model,
                benchmark_test_code=None,  # We run the test ourselves in the sandbox
            )

            # Extract the best available code
            generated_code = (
                agent_result.get("refined_code")
                or agent_result.get("generated_code")
                or ""
            )

            # Extract telemetry the agent surface exposes
            iteration_count = agent_result.get("iteration_count", 0)
            debug_loop_count = agent_result.get("debug_loop_count", 0)
            total_tokens = agent_result.get("total_tokens_used")

        except Exception:
            agent_error = traceback.format_exc()
            generated_code = ""

        # --- Evaluate in sandbox ---
        if agent_error:
            # Agent itself crashed — record without running sandbox
            elapsed = time.monotonic() - wall_start
            sample = SampleResult(
                sample_index=sample_idx,
                passed=False,
                total_tests=0,
                failed_tests=1,
                error_type="internal_agent_error",
                generated_code=generated_code,
                sandbox=None,
                number_of_iterations=iteration_count,
                number_of_debug_loops=debug_loop_count,
                execution_time_seconds=elapsed,
                total_tokens_used=total_tokens,
                final_status="internal_agent_error",
            )
        else:
            sample = evaluate_sample(
                generated_code=generated_code,
                test_code=test_code,
                sample_index=sample_idx,
                config=config,
                iteration_count=iteration_count,
                debug_loop_count=debug_loop_count,
                total_tokens=total_tokens,
            )

        samples.append(sample)

        # Short summary to stdout so the user sees progress
        status_icon = "✓" if sample.passed else "✗"
        print(
            f"  [{task_key}] sample={sample_idx} "
            f"{status_icon} {sample.final_status} "
            f"({sample.execution_time_seconds:.2f}s)",
            flush=True,
        )

    # Determine aggregate final_status for this task
    if any(s.passed for s in samples):
        agg_status = "pass"
    elif all(s.final_status == "timeout" for s in samples):
        agg_status = "timeout"
    elif all(s.final_status == "internal_agent_error" for s in samples):
        agg_status = "internal_agent_error"
    else:
        agg_status = "fail"

    return TaskResult(
        task_id=task_key,
        entry_point=entry_point,
        samples=samples,
        final_status=agg_status,
    )


# ---------------------------------------------------------------------------
# Main runner class
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """
    Orchestrates the full benchmark evaluation lifecycle.

    Usage::

        config = EvalConfig(model="ollama", samples_per_task=3, workers=2)
        runner = BenchmarkRunner("humaneval", config)
        report = runner.run(num_tasks=50)
        runner.save(report, output_dir="data/benchmarks")
    """

    def __init__(self, benchmark: str, config: EvalConfig) -> None:
        """
        Initialise the runner.

        Args:
            benchmark: Benchmark name key (``"humaneval"`` or ``"mbpp"``).
            config:    Evaluation configuration dataclass.
        """
        self.benchmark = benchmark
        self.config = config

    def run(
        self,
        num_tasks: int = 5,
        start_idx: int = 0,
        data_dir: Optional[str] = None,
    ) -> BenchmarkReport:
        """
        Download (if needed), load, and evaluate a slice of benchmark tasks.

        Args:
            num_tasks:  Maximum number of tasks to evaluate.
            start_idx:  Zero-based offset into the dataset.
            data_dir:   Optional override for the dataset directory.

        Returns:
            A populated :class:`BenchmarkReport`.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        # ── Ensure dataset is available ─────────────────────────────────────
        if not ensure_downloaded(self.benchmark, **({"data_dir": data_dir} if data_dir else {})):
            raise RuntimeError(f"Could not download dataset '{self.benchmark}'.")

        # ── Load task slice ─────────────────────────────────────────────────
        load_kwargs: Dict[str, Any] = {"start": start_idx, "count": num_tasks}
        if data_dir:
            load_kwargs["data_dir"] = data_dir
        tasks = load_tasks(self.benchmark, **load_kwargs)

        total = len(tasks)
        k = self.config.samples_per_task

        print(
            f"\n{'='*60}\n"
            f"  Benchmark : {self.benchmark.upper()}\n"
            f"  Model     : {self.config.model}\n"
            f"  Tasks     : {total}  |  Samples/task : {k}\n"
            f"  Workers   : {self.config.workers}\n"
            f"  Timeout   : {self.config.timeout_seconds}s/task\n"
            f"{'='*60}\n",
            flush=True,
        )

        # ── Run tasks ───────────────────────────────────────────────────────
        task_args = [
            (task, self.benchmark, self.config, timestamp)
            for task in tasks
        ]

        task_results: List[TaskResult] = []
        bench_start = time.monotonic()

        if self.config.workers <= 1:
            # Sequential execution
            for i, args in enumerate(task_args):
                task_id = args[0].get("task_id", f"task_{i}")
                print(f"[{i+1}/{total}] {task_id}", flush=True)
                result = _run_single_task(args)
                task_results.append(result)
        else:
            # Parallel execution via multiprocessing
            with ProcessPoolExecutor(max_workers=self.config.workers) as pool:
                futures = {
                    pool.submit(_run_single_task, args): args[0].get("task_id", f"task_{i}")
                    for i, args in enumerate(task_args)
                }
                completed = 0
                for future in as_completed(futures):
                    task_id = futures[future]
                    completed += 1
                    try:
                        result = future.result()
                        task_results.append(result)
                        print(
                            f"[{completed}/{total}] {task_id} → {result.final_status}",
                            flush=True,
                        )
                    except Exception:  # noqa: BLE001
                        tb = traceback.format_exc()
                        print(
                            f"[{completed}/{total}] {task_id} → WORKER CRASHED\n{tb}",
                            flush=True,
                        )
                        # Still record a failed TaskResult so output is complete
                        task_results.append(
                            TaskResult(
                                task_id=task_id,
                                entry_point=task_id,
                                samples=[],
                                final_status="internal_agent_error",
                            )
                        )

        bench_elapsed = time.monotonic() - bench_start

        # ── Compute summary statistics ──────────────────────────────────────
        all_sample_lists = [t.samples for t in task_results]

        # pass@1: fraction of tasks where at least 1 sample passed (k=1)
        pass_at_1 = sum(1 for t in task_results if t.any_passed()) / max(total, 1)

        # pass@k (full estimator)
        pass_at_k = aggregate_pass_at_k(all_sample_lists, k=k)

        # Average per-sample latency across ALL samples
        all_samples_flat = [s for t in task_results for s in t.samples]
        avg_latency = (
            sum(s.execution_time_seconds for s in all_samples_flat)
            / max(len(all_samples_flat), 1)
        )

        report = BenchmarkReport(
            benchmark=self.benchmark,
            model=self.config.model,
            timestamp=timestamp,
            eval_config=self.config,
            tasks=task_results,
            total_tasks=total,
            pass_at_1=pass_at_1,
            pass_at_k=pass_at_k,
            avg_latency=avg_latency,
        )

        # ── Print summary ───────────────────────────────────────────────────
        print(
            f"\n{'='*60}\n"
            f"  RESULTS\n"
            f"  Tasks evaluated  : {total}\n"
            f"  pass@1           : {pass_at_1*100:.2f}%\n"
            f"  pass@{k:<3}          : {pass_at_k*100:.2f}%\n"
            f"  Avg latency      : {avg_latency:.2f}s\n"
            f"  Total wall time  : {bench_elapsed:.1f}s\n"
            f"{'='*60}\n",
            flush=True,
        )

        return report

    @staticmethod
    def save(report: BenchmarkReport, output_dir: str) -> str:
        """
        Serialise *report* to a JSON file named after the benchmark + timestamp.

        Args:
            report:     The report to save.
            output_dir: Directory where the file will be written.

        Returns:
            Absolute path to the written file.
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = f"results_{report.benchmark}_{report.model}_{report.timestamp}.json"
        output_path = os.path.join(output_dir, filename)

        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(report.as_dict(), fh, indent=2, ensure_ascii=False)

        print(f"\n[runner] Report saved → {output_path}", flush=True)
        return output_path
