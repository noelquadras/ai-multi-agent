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
    model: str  # "ollama" or "groq"
    
    # Agent Outputs
    generated_code: str
    review_report: str
    decision: str  # "YES" or "NO"
    refined_code: str
    documentation: str
    test_results: str  # CLI test output
    
    # Metadata
    messages: Annotated[Sequence[BaseMessage], operator.add]
    current_agent: str
    error: Optional[str]
    iteration_count: int
