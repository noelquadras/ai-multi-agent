"""
State schema for LangGraph agent workflow.
This defines the shared state that flows through all agent nodes.
"""

from typing import TypedDict, Annotated, Sequence, Optional
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """
    Shared state across all agent nodes in the graph.
    
    This state is passed between nodes and updated by each agent.
    """
    # Input
    requirements: str
    task_id: str
    model: str  # "ollama" or "groq" (default/fallback)
    agent_models: Optional[dict[str, str]]  # Specific models for each agent
    benchmark_test_code: Optional[str]  # Optional test code for benchmarking (e.g. HumanEval)
    
    # Agent Outputs
    generated_code: str
    review_report: str
    decision: str  # "YES" or "NO"
    refined_code: str
    documentation: str
    test_results: str  # CLI test output summary
    test_output: Optional[dict] # Raw execution results (returncode, stdout, stderr)
    analysis: str # Analyzer's reasoning and instructions

    # Metadata
    messages: Annotated[Sequence[BaseMessage], operator.add]
    current_agent: str
    error: Optional[str]
    iteration_count: int
    debug_loop_count: int  # Number of refine→test→analyze cycles (for telemetry)
    total_tokens_used: Optional[int]  # Cumulative token count (if backend exposes it)
