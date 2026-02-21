"""
scripts/benchmark_runner.py
============================
CLI entrypoint for the research-grade agent evaluation harness.

Usage examples
--------------
# Download datasets only
python scripts/benchmark_runner.py --dataset humaneval --download

# Quick 5-task eval on the default model
python scripts/benchmark_runner.py --dataset humaneval --tasks 5

# Rigorous 3-sample pass@3 evaluation with 4 parallel workers
python scripts/benchmark_runner.py \\
    --dataset humaneval --tasks 50 --samples 3 --workers 4 \\
    --model ollama --temperature 0 --seed 42

# MBPP starting at task 20
python scripts/benchmark_runner.py \\
    --dataset mbpp --tasks 10 --start 20
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure project root is on the path so ``main`` and ``harness`` can be imported
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Harness imports — these are the only public API we expose to the CLI
from harness.dataset import ensure_downloaded  # noqa: E402
from harness.runner import BenchmarkRunner      # noqa: E402
from harness.types import EvalConfig            # noqa: E402

# Default output directory (relative to project root)
_DEFAULT_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "data", "benchmarks")


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="benchmark_runner",
        description=(
            "Research-grade agent evaluation harness for HumanEval / MBPP.\n\n"
            "Pass --download to fetch the dataset only.\n"
            "Omit --download to run the full evaluation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Dataset / scope ─────────────────────────────────────────────────────
    parser.add_argument(
        "--dataset",
        type=str,
        choices=["humaneval", "mbpp"],
        default="humaneval",
        help="Benchmark dataset to evaluate against.  (default: humaneval)",
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=5,
        metavar="N",
        help="Number of tasks to evaluate.  (default: 5)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        metavar="IDX",
        help="Zero-based index of the first task.  (default: 0)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download the dataset then exit (no evaluation).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=_DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory to write result JSON files.  (default: {_DEFAULT_OUTPUT_DIR})",
    )

    # ── Model / LLM config ───────────────────────────────────────────────────
    parser.add_argument(
        "--model",
        type=str,
        default="ollama",
        help=(
            "Model key: 'ollama' (default local), 'groq', or any specific "
            "Ollama model tag e.g. 'mistral:7b-instruct'.  (default: ollama)"
        ),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        metavar="T",
        help=(
            "Sampling temperature.  0.0 = fully deterministic greedy decoding.  "
            "(default: 0.0)"
        ),
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=1.0,
        dest="top_p",
        metavar="P",
        help="Nucleus-sampling probability mass.  (default: 1.0)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        dest="max_tokens",
        metavar="N",
        help="Maximum tokens the LLM may generate per completion.  (default: 2048)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="S",
        help=(
            "PRNG seed forwarded to the LLM backend (when supported).  "
            "If omitted, no seed is set."
        ),
    )

    # ── pass@k / parallelism ─────────────────────────────────────────────────
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        metavar="K",
        help=(
            "Number of independent completions per task (for pass@k).  "
            "Set to 1 for standard pass@1 evaluation.  (default: 1)"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="W",
        help=(
            "Number of parallel worker processes.  Values >1 use the "
            "multiprocessing pool for true process-level isolation.  "
            "(default: 1 = sequential)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        metavar="SEC",
        help="Per-task sandbox execution timeout in seconds.  (default: 10)",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments, build EvalConfig, and dispatch to the harness."""
    parser = _build_parser()
    args = parser.parse_args()

    # ── Download-only mode ───────────────────────────────────────────────────
    if args.download:
        success = ensure_downloaded(args.dataset, data_dir=args.output_dir)
        sys.exit(0 if success else 1)

    # ── Validate arguments ───────────────────────────────────────────────────
    if args.tasks < 1:
        parser.error("--tasks must be ≥ 1")
    if args.samples < 1:
        parser.error("--samples must be ≥ 1")
    if args.workers < 1:
        parser.error("--workers must be ≥ 1")
    if not (0.0 <= args.temperature <= 2.0):
        parser.error("--temperature must be in [0.0, 2.0]")
    if not (0.0 < args.top_p <= 1.0):
        parser.error("--top-p must be in (0.0, 1.0]")

    # ── Build config ─────────────────────────────────────────────────────────
    config = EvalConfig(
        model=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        seed=args.seed,
        timeout_seconds=args.timeout,
        samples_per_task=args.samples,
        workers=args.workers,
    )

    print("\n[config] Evaluation parameters:")
    for key, val in config.as_dict().items():
        print(f"  {key:<22} = {val}")
    print()

    # ── Run benchmark ─────────────────────────────────────────────────────────
    runner = BenchmarkRunner(benchmark=args.dataset, config=config)
    report = runner.run(
        num_tasks=args.tasks,
        start_idx=args.start,
        data_dir=args.output_dir,
    )

    # ── Save report ───────────────────────────────────────────────────────────
    output_path = BenchmarkRunner.save(report, output_dir=args.output_dir)
    print(f"\n✅ Benchmark complete.  Results → {output_path}\n")


if __name__ == "__main__":
    # Multiprocessing guard — required on Windows and macOS (spawn start method)
    # Without this, spawned worker processes would re-run the __main__ block.
    import multiprocessing
    multiprocessing.freeze_support()
    main()
