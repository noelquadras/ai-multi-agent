"""
State schema for LangGraph agent workflow.
This defines the shared state that flows through all agent nodes.
"""

from typing import TypedDict, Annotated, Sequence, Optional, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class TaskProfile(TypedDict, total=False):
    """
    Classification of the task complexity and required execution path.
    """
    complexity: Literal["trivial", "standard", "complex"]
    needs_spec: bool
    needs_review: bool
    needs_docs: bool
    needs_testing: bool
    rationale: str


class AgentMetrics(TypedDict):
    """Token usage and invocation metrics per agent."""
    calls: int
    tokens: int


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
    
    # Classification & Profiling
    task_profile: Optional[TaskProfile]
    agent_metrics: dict[str, AgentMetrics] # Per-agent usage tracking

    # Agent Outputs
    generated_code: str
    review_report: str
    decision: str  # "YES" or "NO"
    refined_code: str
    documentation: str
    test_results: str  # CLI test output summary
    test_output: Optional[dict] # Raw execution results (returncode, stdout, stderr)
    analysis: str # Analyzer's reasoning and instructions

    # Spec writer output (MetaGPT artifact-first pattern)
    spec_doc_path: Optional[str]       # Path to persisted spec JSON
    spec_structured: Optional[dict]    # SpecOutput dict

    # Structured outputs (Pydantic model_dump dicts)
    review_report_structured: Optional[dict]    # ReviewOutput dict
    decision_output: Optional[dict]   # Serialised DecisionOutput
    analysis_structured: Optional[dict]         # AnalysisOutput dict

    # Per-agent memory (ListMemory pattern)
    refiner_memory: Optional[list[str]]  # "Iteration N: fixed [...]" entries

    # Orchestrator fields (autonomous LLM-driven orchestration)
    plan: Optional[list[dict]]                # PlanStep dicts — dynamic execution plan
    pending_dispatches: Optional[list[str]]   # Agent names to dispatch next (set by orchestrator)
    orchestrator_history: Optional[list[dict]] # Command audit trail [{command, args, rationale}]
    orchestrator_thinking: Optional[str]       # Last reasoning chain (for UI/debug)

    # Metadata
    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_agent: str
    error: Optional[str]
    iteration_count: int
    debug_loop_count: int  # Number of refine→test→analyze cycles (for telemetry)
    total_tokens_used: Optional[int]  # Cumulative token count (if backend exposes it)
