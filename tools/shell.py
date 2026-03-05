"""
Shell command execution tool for agents.

Provides safe shell command execution with timeout, output capture,
and a blocklist for dangerous commands. Wraps the existing
sandbox_subprocess.py for consistency.

Inspired by MetaGPT's Terminal.run_command.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

from tools.sandbox_subprocess import run_code_in_subprocess


# Blocklist of dangerous shell patterns
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",          # recursive delete root
    r"del\s+/s\s+/q",         # Windows recursive delete
    r"format\s+[a-zA-Z]:",    # format drives
    r"mkfs\.",                 # Linux format
    r"dd\s+if=",              # raw disk write
    r":(){.*};:",              # fork bomb
    r">\s*/dev/sd",            # overwrite disk
    r"shutdown",               # system shutdown
    r"reboot",                 # system reboot
    r"curl.*\|\s*bash",        # pipe to bash
    r"wget.*\|\s*sh",          # pipe to shell
]

_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]


@dataclass
class ShellResult:
    """Result of a shell command execution."""
    status: str  # "success", "error", "timeout", "blocked"
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""


def _is_blocked(command: str) -> bool:
    """Check if a command matches any blocked pattern."""
    for pattern in _BLOCKED_RE:
        if pattern.search(command):
            return True
    return False


def run_shell(
    command: str,
    timeout: int = 10,
    cwd: Optional[str] = None,
) -> ShellResult:
    """
    Execute a shell command safely with timeout and output capture.
    
    Args:
        command: Shell command to execute
        timeout: Maximum execution time in seconds
        cwd: Working directory (defaults to current)
    
    Returns:
        ShellResult with status, output, and return code.
    """
    if _is_blocked(command):
        return ShellResult(
            status="blocked",
            stderr=f"Command blocked by safety filter: {command}"
        )

    # Wrap command as Python subprocess call for sandboxing
    code = f"""\
import subprocess, sys, os

os.chdir({repr(cwd or os.getcwd())})
result = subprocess.run(
    {repr(command)},
    shell=True,
    capture_output=True,
    text=True,
    timeout={timeout},
)
print(result.stdout, end='')
if result.stderr:
    print(result.stderr, end='', file=sys.stderr)
sys.exit(result.returncode)
"""

    try:
        result = run_code_in_subprocess(
            code=code,
            timeout=timeout + 5,  # Buffer for subprocess overhead
            working_dir=cwd,
        )

        return ShellResult(
            status=result.get("status", "error"),
            returncode=result.get("returncode"),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
        )
    except Exception as e:
        return ShellResult(
            status="error",
            stderr=f"Shell execution error: {e}",
        )


def run_python(
    code: str,
    timeout: int = 10,
    cwd: Optional[str] = None,
) -> ShellResult:
    """
    Execute Python code in a sandboxed subprocess.
    
    This is a convenience wrapper around sandbox_subprocess.
    
    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds
        cwd: Working directory
    
    Returns:
        ShellResult with execution output.
    """
    try:
        result = run_code_in_subprocess(
            code=code,
            timeout=timeout,
            working_dir=cwd,
        )

        return ShellResult(
            status=result.get("status", "error"),
            returncode=result.get("returncode"),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
        )
    except Exception as e:
        return ShellResult(
            status="error",
            stderr=f"Python execution error: {e}",
        )
