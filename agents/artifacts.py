"""
Disk-persisted artifact store for the agent pipeline.

Every node writes its output to disk under tasks/{task_id}/.
This gives full auditability, resume-on-restart capability, and
easy debugging (open any file to see exactly what a node produced).

Inspired by: MetaGPT FileRepository + AutoGen save_state/load_state.
"""

from pathlib import Path
import json
import re
from typing import Optional

TASKS_ROOT = Path("tasks")


def artifact_dir(task_id: str) -> Path:
    """Return (and create) the root artifact directory for a task."""
    p = TASKS_ROOT / task_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_artifact(task_id: str, relative_path: str, content: str) -> Path:
    """Write a text artifact to disk. Creates parent directories as needed."""
    path = artifact_dir(task_id) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def save_code_version(task_id: str, content: str) -> tuple[Path, str]:
    """Save code as the next version: code/solution_v1.py, v2, v3, etc.
    Returns (path, filename) e.g. (Path(...), 'solution_v3.py').
    """
    code_dir = artifact_dir(task_id) / "code"
    code_dir.mkdir(parents=True, exist_ok=True)

    # Find existing version numbers
    existing = list(code_dir.glob("solution_v*.py"))
    max_ver = 0
    for f in existing:
        m = re.search(r"solution_v(\d+)\.py$", f.name)
        if m:
            max_ver = max(max_ver, int(m.group(1)))

    next_ver = max_ver + 1
    filename = f"solution_v{next_ver}.py"
    path = code_dir / filename
    path.write_text(content, encoding="utf-8")
    return path, filename


def save_json_artifact(task_id: str, relative_path: str, data: dict) -> Path:
    """Write a JSON artifact to disk."""
    return save_artifact(task_id, relative_path, json.dumps(data, indent=2, default=str))


def load_artifact(task_id: str, relative_path: str) -> Optional[str]:
    """Read a text artifact from disk, or None if it doesn't exist."""
    path = artifact_dir(task_id) / relative_path
    return path.read_text(encoding="utf-8") if path.exists() else None


def load_json_artifact(task_id: str, relative_path: str) -> Optional[dict]:
    """Read a JSON artifact from disk, or None if it doesn't exist."""
    text = load_artifact(task_id, relative_path)
    if text is None:
        return None
    return json.loads(text)


def list_artifacts(task_id: str) -> list[dict]:
    """
    Return a manifest of all files under tasks/{task_id}/.

    Each entry: {"path": relative_posix_path, "size": bytes, "modified": iso_timestamp}
    """
    root = TASKS_ROOT / task_id
    if not root.exists():
        return []

    manifest = []
    for f in sorted(root.rglob("*")):
        if f.is_file():
            stat = f.stat()
            manifest.append({
                "path": f.relative_to(root).as_posix(),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return manifest
