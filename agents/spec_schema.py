"""
Pydantic schema for the spec_writer_node output.

The spec document gives the code generator explicit architectural direction
(MetaGPT artifact-first pattern) instead of letting the LLM invent
everything from a raw requirements string.
"""

from pydantic import BaseModel, Field
from typing import Literal


class SpecOutput(BaseModel):
    """Technical specification produced before code generation."""

    implementation_approach: str = Field(
        description="Frameworks, libraries, hard parts, and overall strategy"
    )
    file_list: list[str] = Field(
        default=["solution.py"],
        description="Files to generate (always ['solution.py'] for now)"
    )
    class_design: str = Field(
        description="Plain-English outline of classes, functions, and their responsibilities"
    )
    key_edge_cases: list[str] = Field(
        description="Edge cases and corner conditions the code MUST handle"
    )
    complexity_estimate: Literal["simple", "medium", "complex"] = Field(
        description="Estimated complexity of the implementation"
    )
