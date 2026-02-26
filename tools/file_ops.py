"""
File system operations for agents.

Provides safe file read/write/search operations that agents can use
to interact with the project workspace. All paths are validated
and sandboxed to prevent escape.

Inspired by MetaGPT's Editor tool (libs/editor.py).
"""

from __future__ import annotations

import os
import re
import fnmatch
from dataclasses import dataclass
from typing import Optional


# Allowed workspace root — agents can only access files under this
_WORKSPACE_ROOT: str | None = None


def set_workspace_root(path: str) -> None:
    """Set the workspace root for file operations."""
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = os.path.abspath(path)


def _resolve_path(path: str) -> str:
    """Resolve and validate a path against the workspace root."""
    if _WORKSPACE_ROOT is None:
        raise RuntimeError("Workspace root not set. Call set_workspace_root() first.")
    
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(_WORKSPACE_ROOT):
        raise PermissionError(
            f"Path '{path}' is outside the workspace root '{_WORKSPACE_ROOT}'"
        )
    return abs_path


@dataclass
class FileResult:
    """Result of a file operation."""
    success: bool
    content: str = ""
    error: str = ""
    path: str = ""


def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> FileResult:
    """
    Read a file's contents, optionally limited to a line range.
    
    Args:
        path: File path (absolute or relative to workspace root)
        start_line: 1-indexed start line (inclusive). None = beginning.
        end_line: 1-indexed end line (inclusive). None = end of file.
    
    Returns:
        FileResult with the file contents or error message.
    """
    try:
        abs_path = _resolve_path(path)
        if not os.path.isfile(abs_path):
            return FileResult(success=False, error=f"File not found: {path}")

        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            lines = lines[s:e]

        return FileResult(
            success=True,
            content="".join(lines),
            path=abs_path,
        )
    except PermissionError as e:
        return FileResult(success=False, error=str(e))
    except Exception as e:
        return FileResult(success=False, error=f"Read error: {e}")


def write_file(
    path: str,
    content: str,
    mode: str = "w",
) -> FileResult:
    """
    Write content to a file.
    
    Args:
        path: File path
        content: Content to write
        mode: "w" for overwrite, "a" for append
    
    Returns:
        FileResult indicating success or failure.
    """
    try:
        abs_path = _resolve_path(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, mode, encoding="utf-8") as f:
            f.write(content)

        return FileResult(success=True, path=abs_path, content=f"Written {len(content)} chars")
    except PermissionError as e:
        return FileResult(success=False, error=str(e))
    except Exception as e:
        return FileResult(success=False, error=f"Write error: {e}")


def list_directory(
    path: str,
    pattern: str = "*",
    recursive: bool = False,
) -> FileResult:
    """
    List files in a directory with optional glob pattern filtering.
    
    Args:
        path: Directory path
        pattern: Glob pattern to filter results (e.g., "*.py")
        recursive: If True, search recursively
    
    Returns:
        FileResult with newline-separated file paths.
    """
    try:
        abs_path = _resolve_path(path)
        if not os.path.isdir(abs_path):
            return FileResult(success=False, error=f"Not a directory: {path}")

        results = []
        if recursive:
            for root, dirs, files in os.walk(abs_path):
                # Skip hidden and __pycache__ dirs
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        rel = os.path.relpath(os.path.join(root, f), abs_path)
                        results.append(rel)
        else:
            for entry in os.listdir(abs_path):
                if fnmatch.fnmatch(entry, pattern):
                    full = os.path.join(abs_path, entry)
                    prefix = "[DIR] " if os.path.isdir(full) else ""
                    results.append(f"{prefix}{entry}")

        # Cap results to avoid overwhelming output
        if len(results) > 100:
            results = results[:100] + [f"... and {len(results) - 100} more"]

        return FileResult(success=True, content="\n".join(results), path=abs_path)
    except Exception as e:
        return FileResult(success=False, error=f"List error: {e}")


def search_files(
    directory: str,
    query: str,
    extensions: Optional[list[str]] = None,
    max_results: int = 50,
) -> FileResult:
    """
    Search for a text pattern across files in a directory (grep-like).
    
    Args:
        directory: Directory to search in
        query: Text pattern to search for (case-insensitive)
        extensions: File extensions to include (e.g., [".py", ".js"])
        max_results: Maximum number of matches to return
    
    Returns:
        FileResult with matching lines in "file:line_num: content" format.
    """
    try:
        abs_path = _resolve_path(directory)
        if not os.path.isdir(abs_path):
            return FileResult(success=False, error=f"Not a directory: {directory}")

        pattern = re.compile(re.escape(query), re.IGNORECASE)
        matches = []

        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for fname in files:
                if extensions:
                    if not any(fname.endswith(ext) for ext in extensions):
                        continue
                
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if pattern.search(line):
                                rel = os.path.relpath(fpath, abs_path)
                                matches.append(f"{rel}:{i}: {line.rstrip()}")
                                if len(matches) >= max_results:
                                    break
                except Exception:
                    continue

                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

        return FileResult(
            success=True,
            content="\n".join(matches) if matches else "No matches found",
            path=abs_path,
        )
    except Exception as e:
        return FileResult(success=False, error=f"Search error: {e}")
