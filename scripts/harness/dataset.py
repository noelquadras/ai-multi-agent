"""
harness/dataset.py
==================
Pure-function dataset loader with no global state.

Supports:
  - HumanEval (.jsonl.gz)
  - MBPP-Plus  (.jsonl.gz)

Downloads are handled lazily with httpx (sync) so caller code stays
simple — no async event-loop plumbing in benchmark logic.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BENCHMARKS: Dict[str, Dict[str, str]] = {
    "humaneval": {
        "url": "https://github.com/openai/human-eval/raw/master/data/HumanEval.jsonl.gz",
        "filename": "HumanEval.jsonl.gz",
        "task_key": "task_id",
    },
    "mbpp": {
        "url": (
            "https://github.com/evalplus/mbppplus_release/releases/"
            "download/v0.1.0/MbppPlus.jsonl.gz"
        ),
        "filename": "MbppPlus.jsonl.gz",
        "task_key": "task_id",
    },
}

_DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "benchmarks",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dataset_path(name: str, data_dir: str = _DEFAULT_DATA_DIR) -> str:
    """Return the expected local path for benchmark *name*."""
    cfg = _get_config(name)
    return os.path.join(data_dir, cfg["filename"])


def ensure_downloaded(
    name: str,
    data_dir: str = _DEFAULT_DATA_DIR,
    force: bool = False,
) -> bool:
    """
    Download *name* dataset if it is not already present locally.

    Args:
        name:     Benchmark key, e.g. ``"humaneval"``.
        data_dir: Directory where the compressed file will be stored.
        force:    If True, re-download even if the file exists.

    Returns:
        True on success, False on failure.
    """
    cfg = _get_config(name)
    path = os.path.join(data_dir, cfg["filename"])
    url = cfg["url"]

    if os.path.exists(path) and not force:
        print(f"[dataset] '{name}' already present at {path}", flush=True)
        return True

    os.makedirs(data_dir, exist_ok=True)
    print(f"[dataset] Downloading '{name}' from {url} …", flush=True)

    try:
        import httpx  # keep httpx as the only download dep
        with httpx.Client(follow_redirects=True, timeout=120.0) as client:
            response = client.get(url)
            response.raise_for_status()
        with open(path, "wb") as fh:
            fh.write(response.content)
        print(f"[dataset] Downloaded '{name}' → {path}", flush=True)
        return True
    except Exception as exc:
        print(f"[dataset] ERROR downloading '{name}': {exc}", file=sys.stderr, flush=True)
        return False


def load_tasks(
    name: str,
    data_dir: str = _DEFAULT_DATA_DIR,
    start: int = 0,
    count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Load and return a slice of tasks from the compressed JSONL file.

    Args:
        name:     Benchmark key.
        data_dir: Directory containing the compressed file.
        start:    Zero-based index of the first task to return.
        count:    Maximum number of tasks to return (None = all).

    Returns:
        A list of task dicts as parsed from the JSONL file.

    Raises:
        FileNotFoundError: If the dataset file does not exist.
        ValueError:        If *name* is not in the registry.
    """
    cfg = _get_config(name)
    path = os.path.join(data_dir, cfg["filename"])

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset file not found: {path}\n"
            f"Run with --download flag first."
        )

    tasks: List[Dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))

    end = start + count if count is not None else len(tasks)
    return tasks[start:end]


def build_prompt(task: Dict[str, Any], benchmark: str) -> str:
    """
    Build the agent prompt for a single benchmark task.

    The prompt instructs the agent to complete the function body only,
    without meta-commentary, so the generated code concatenates cleanly
    with the test harness.

    Args:
        task:      Raw task dict from the JSONL file.
        benchmark: Benchmark name used for field-name disambiguation.

    Returns:
        A fully formatted prompt string.
    """
    prompt_body = task.get("prompt", "")
    return (
        "Complete the following Python function. "
        "Return ONLY the code — no explanations, no markdown fences, "
        "no text before or after the code block.\n\n"
        f"{prompt_body}"
    )


def get_test_code(task: Dict[str, Any]) -> str:
    """Return the test/assertion code from a task dict, handling field aliases."""
    # HumanEval uses 'test'; MBPP-Plus uses 'assertion' or 'test_list'
    return task.get("test") or task.get("assertion") or ""


def get_entry_point(task: Dict[str, Any], task_id: str) -> str:
    """Return the entry-point function name, falling back to task_id."""
    return task.get("entry_point") or f"task_{task_id}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_config(name: str) -> Dict[str, str]:
    cfg = BENCHMARKS.get(name)
    if cfg is None:
        raise ValueError(
            f"Unknown benchmark '{name}'. "
            f"Valid options: {list(BENCHMARKS.keys())}"
        )
    return cfg
