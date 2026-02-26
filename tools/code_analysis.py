"""
Static code analysis tools for agents.

Provides AST-based code analysis, basic linting, and dependency
extraction. Used by the reviewer and refiner agents to understand
code structure without executing it.

Inspired by MetaGPT's code analysis utilities.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FunctionInfo:
    """Information about a function in the code."""
    name: str
    lineno: int
    args: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    complexity: int = 1  # Rough cyclomatic complexity


@dataclass
class ClassInfo:
    """Information about a class in the code."""
    name: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    docstring: str = ""


@dataclass
class AnalysisResult:
    """Result of AST-based code analysis."""
    success: bool = True
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    total_lines: int = 0
    complexity_score: int = 0  # Sum of all function complexities
    error: str = ""


@dataclass
class LintIssue:
    """Single lint issue found in the code."""
    line: int
    message: str
    severity: str = "warning"  # "error", "warning", "info"


def analyze_ast(code: str) -> AnalysisResult:
    """
    Analyze Python code using the AST to extract structure information.
    
    Args:
        code: Python source code string
    
    Returns:
        AnalysisResult with functions, classes, imports, and complexity.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AnalysisResult(
            success=False,
            error=f"Syntax error at line {e.lineno}: {e.msg}",
            total_lines=len(code.splitlines()),
        )

    result = AnalysisResult(total_lines=len(code.splitlines()))

    for node in ast.walk(tree):
        # Extract imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result.imports.append(f"{module}.{alias.name}")

        # Extract functions
        elif isinstance(node, ast.FunctionDef):
            complexity = _count_complexity(node)
            func_info = FunctionInfo(
                name=node.name,
                lineno=node.lineno,
                args=[arg.arg for arg in node.args.args],
                decorators=[_decorator_name(d) for d in node.decorator_list],
                docstring=ast.get_docstring(node) or "",
                complexity=complexity,
            )
            result.functions.append(func_info)
            result.complexity_score += complexity

        # Extract classes
        elif isinstance(node, ast.ClassDef):
            methods = [
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            class_info = ClassInfo(
                name=node.name,
                lineno=node.lineno,
                bases=[_node_name(b) for b in node.bases],
                methods=methods,
                docstring=ast.get_docstring(node) or "",
            )
            result.classes.append(class_info)

    return result


def lint_code(code: str) -> list[LintIssue]:
    """
    Perform basic static analysis / linting on Python code.
    
    Checks for common issues without executing the code.
    This is NOT a replacement for pylint/flake8 but provides
    quick feedback in the agent loop.
    
    Args:
        code: Python source code string
    
    Returns:
        List of LintIssue objects.
    """
    issues: list[LintIssue] = []
    lines = code.splitlines()

    # Check 1: Syntax validity
    try:
        ast.parse(code)
    except SyntaxError as e:
        issues.append(LintIssue(
            line=e.lineno or 0,
            message=f"Syntax error: {e.msg}",
            severity="error",
        ))
        return issues  # Can't do further analysis

    # Check 2: Line length
    for i, line in enumerate(lines, 1):
        if len(line) > 120:
            issues.append(LintIssue(
                line=i,
                message=f"Line too long ({len(line)} > 120 chars)",
                severity="warning",
            ))

    # Check 3: Bare except
    bare_except_re = re.compile(r"^\s*except\s*:")
    for i, line in enumerate(lines, 1):
        if bare_except_re.match(line):
            issues.append(LintIssue(
                line=i,
                message="Bare except: catches all exceptions including SystemExit",
                severity="warning",
            ))

    # Check 4: TODO/FIXME/HACK comments
    for i, line in enumerate(lines, 1):
        for tag in ("TODO", "FIXME", "HACK", "XXX"):
            if tag in line:
                issues.append(LintIssue(
                    line=i,
                    message=f"Found {tag} comment",
                    severity="info",
                ))
                break

    # Check 5: Unused imports (basic check)
    tree = ast.parse(code)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imports.add(name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                imports.add(name)

    # Check if imported names appear in the rest of the code
    code_without_imports = "\n".join(
        line for line in lines
        if not line.strip().startswith(("import ", "from "))
    )
    for imp in imports:
        if imp not in code_without_imports and imp != "*":
            issues.append(LintIssue(
                line=0,
                message=f"Potentially unused import: '{imp}'",
                severity="warning",
            ))

    return issues


def extract_dependencies(code: str) -> list[str]:
    """
    Extract all imported module names from Python code.
    
    Returns top-level module names only (e.g., "os" from "os.path").
    
    Args:
        code: Python source code string
    
    Returns:
        List of unique top-level module names.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Fallback: regex-based extraction
        pattern = re.compile(r"^(?:import|from)\s+(\w+)", re.MULTILINE)
        return list(set(pattern.findall(code)))

    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])

    return sorted(modules)


# ─── Internal Helpers ───────────────────────────────────────────────────────

def _count_complexity(node: ast.FunctionDef) -> int:
    """Count rough cyclomatic complexity of a function."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
    return complexity


def _decorator_name(node: ast.expr) -> str:
    """Extract decorator name from AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "?"


def _node_name(node: ast.expr) -> str:
    """Extract name from an AST expression node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    return "?"
