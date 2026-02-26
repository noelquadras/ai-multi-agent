"""
Tools package — re-export hub for all agent tools.

This package provides tools that agents can use for:
- File operations (read, write, search, list)
- Shell command execution (safe, sandboxed)
- Web search (DuckDuckGo)
- Code analysis (AST, linting, dependencies)
- Code execution (sandbox subprocess, Docker runner)
- Tool discovery (registry, schemas)
"""

# Core tools (existing)
from tools.executor import execute                              # noqa: F401
from tools.sandbox_subprocess import run_code_in_subprocess     # noqa: F401

# File operations
from tools.file_ops import (                                    # noqa: F401
    read_file,
    write_file,
    list_directory,
    search_files,
    set_workspace_root,
)

# Shell execution
from tools.shell import run_shell, run_python                   # noqa: F401

# Web search
from tools.web_search import search_web, search_and_summarize   # noqa: F401

# Code analysis
from tools.code_analysis import (                               # noqa: F401
    analyze_ast,
    lint_code,
    extract_dependencies,
)

# Tool registry
from tools.tool_registry import (                               # noqa: F401
    ToolRegistry,
    ToolSpec,
    register_tool,
)
