"""
Tool registry for agent tool discovery and recommendation.

Provides a decorator-based registration system and a registry singleton
that agents and the orchestrator can query to discover available tools
and their schemas.

Inspired by MetaGPT's ToolRegistry and BM25ToolRecommender.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ToolSpec:
    """Specification for a registered tool."""
    name: str
    description: str
    module: str
    function: Callable
    parameters: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_schema(self) -> dict:
        """Convert to a JSON-serializable schema for LLM context."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "tags": self.tags,
        }


class ToolRegistry:
    """
    Singleton registry for all available tools.
    
    Tools register themselves via the @register_tool decorator.
    The orchestrator queries this to build tool descriptions
    for the LLM context.
    """
    _instance: Optional[ToolRegistry] = None
    _tools: dict[str, ToolSpec]

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, spec: ToolSpec) -> None:
        """Register a tool specification."""
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolSpec]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_tools_by_tag(self, tag: str) -> list[ToolSpec]:
        """Get tools matching a specific tag."""
        return [t for t in self._tools.values() if tag in t.tags]

    def get_tools_for_agent(self, agent_name: str) -> list[ToolSpec]:
        """
        Get tools relevant to a specific agent.
        
        Uses tag matching to filter tools:
        - "all" tag means the tool is available to all agents
        - Agent-specific tags match the agent name
        """
        return [
            t for t in self._tools.values()
            if "all" in t.tags or agent_name in t.tags
        ]

    def get_tool_schemas(self) -> str:
        """
        Get JSON string of all tool schemas.
        Suitable for including in an LLM system prompt.
        """
        schemas = [t.to_schema() for t in self._tools.values()]
        return json.dumps(schemas, indent=2)

    def reset(self) -> None:
        """Clear all registrations (useful for testing)."""
        self._tools.clear()


def _extract_parameters(func: Callable) -> dict:
    """Extract parameter info from a function's signature and docstring."""
    sig = inspect.signature(func)
    params = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        param_info = {"type": "any"}
        
        if param.annotation != inspect.Parameter.empty:
            param_info["type"] = getattr(param.annotation, "__name__", str(param.annotation))
        
        if param.default != inspect.Parameter.empty:
            param_info["default"] = repr(param.default)
            param_info["required"] = False
        else:
            param_info["required"] = True
        
        params[name] = param_info
    
    return params


def register_tool(
    name: Optional[str] = None,
    tags: Optional[list[str]] = None,
):
    """
    Decorator to register a function as an available tool.
    
    Args:
        name: Tool name (defaults to function name)
        tags: Tags for filtering (e.g., ["all"], ["generate", "refine"])
    
    Usage:
        @register_tool(tags=["all"])
        def my_tool(arg1: str, arg2: int = 5) -> str:
            '''Description of the tool.'''
            ...
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = inspect.getdoc(func) or f"Tool: {tool_name}"
        
        # Take first paragraph of docstring as description
        tool_desc = tool_desc.split("\n\n")[0].strip()

        spec = ToolSpec(
            name=tool_name,
            description=tool_desc,
            module=func.__module__,
            function=func,
            parameters=_extract_parameters(func),
            tags=tags or ["all"],
        )

        registry = ToolRegistry()
        registry.register(spec)
        func._tool_spec = spec
        return func

    return decorator


# ─── Auto-register built-in tools ───────────────────────────────────────────

def _register_builtin_tools() -> None:
    """
    Import and register all built-in tools from the tools package.
    Called once at module load time.
    """
    registry = ToolRegistry()
    
    # File operations
    try:
        from tools.file_ops import read_file, write_file, list_directory, search_files
        for fn, tags in [
            (read_file, ["all"]),
            (write_file, ["generate", "refine"]),
            (list_directory, ["all"]),
            (search_files, ["all"]),
        ]:
            spec = ToolSpec(
                name=fn.__name__,
                description=inspect.getdoc(fn) or fn.__name__,
                module=fn.__module__,
                function=fn,
                parameters=_extract_parameters(fn),
                tags=tags,
            )
            registry.register(spec)
    except ImportError:
        pass

    # Shell execution
    try:
        from tools.shell import run_shell, run_python
        for fn, tags in [
            (run_shell, ["test", "refine"]),
            (run_python, ["test", "refine"]),
        ]:
            spec = ToolSpec(
                name=fn.__name__,
                description=inspect.getdoc(fn) or fn.__name__,
                module=fn.__module__,
                function=fn,
                parameters=_extract_parameters(fn),
                tags=tags,
            )
            registry.register(spec)
    except ImportError:
        pass

    # Web search
    try:
        from tools.web_search import search_web, search_and_summarize
        for fn in (search_web, search_and_summarize):
            spec = ToolSpec(
                name=fn.__name__,
                description=inspect.getdoc(fn) or fn.__name__,
                module=fn.__module__,
                function=fn,
                parameters=_extract_parameters(fn),
                tags=["all"],
            )
            registry.register(spec)
    except ImportError:
        pass

    # Code analysis
    try:
        from tools.code_analysis import analyze_ast, lint_code, extract_dependencies
        for fn in (analyze_ast, lint_code, extract_dependencies):
            spec = ToolSpec(
                name=fn.__name__,
                description=inspect.getdoc(fn) or fn.__name__,
                module=fn.__module__,
                function=fn,
                parameters=_extract_parameters(fn),
                tags=["review", "refine", "analyze_test"],
            )
            registry.register(spec)
    except ImportError:
        pass


# Auto-register on import
_register_builtin_tools()
