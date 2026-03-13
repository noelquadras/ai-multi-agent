from __future__ import annotations

import json
from datetime import datetime
from typing import List, Literal, Optional, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError


T = TypeVar("T", bound="BaseContext")


class BaseContext(BaseModel):
    """Base class for all context types with JSON serialization support."""

    @classmethod
    def loads(cls: Type[T], val: str) -> Optional[T]:
        try:
            data = json.loads(val)
            return cls(**data)
        except (json.JSONDecodeError, ValidationError):
            return None

    def dumps(self) -> str:
        return json.dumps(self.model_dump())


class Document(BaseModel):
    """Simple document structure for context tracking."""

    content: str
    filename: str
    created_at: datetime = Field(default_factory=datetime.now)


class CodingContext(BaseContext):
    """Context for coding activities."""

    filename: str
    design_doc: Optional[Document] = None
    task_doc: Optional[Document] = None
    code_doc: Optional[Document] = None
    code_plan_and_change_doc: Optional[Document] = None
    language: str = "python"
    framework: Optional[str] = None
    complexity: Literal["trivial", "standard", "complex"] = "standard"


class TestingContext(BaseContext):
    """Context for testing activities."""

    filename: str
    code_doc: Document
    test_doc: Optional[Document] = None
    test_framework: Literal["pytest", "unittest", "vitest"] = "pytest"
    coverage_target: Optional[float] = None


class RunCodeContext(BaseContext):
    """Context for code execution activities."""

    mode: Literal["script", "module", "test"] = "script"
    code: Optional[str] = None
    code_filename: str = ""
    test_code: Optional[str] = None
    test_filename: str = ""
    command: List[str] = Field(default_factory=list)
    working_directory: str = ""
    additional_python_paths: List[str] = Field(default_factory=list)
    output_filename: Optional[str] = None
    output: Optional[str] = None
    timeout_seconds: int = 30
    environment: dict[str, str] = Field(default_factory=dict)


class RunCodeResult(BaseContext):
    """Result structure for code execution."""

    summary: str
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    memory_usage: Optional[int] = None


class CodeSummarizeContext(BaseContext):
    """Context for code summarization activities."""

    design_filename: str = ""
    task_filename: str = ""
    codes_filenames: List[str] = Field(default_factory=list)
    reason: str = ""

    @classmethod
    def from_filenames(cls, filenames: List[str]) -> "CodeSummarizeContext":
        ctx = cls()
        for filename in filenames:
            if filename.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                ctx.codes_filenames.append(filename)
            elif filename.endswith((".md", ".txt", ".rst")):
                ctx.design_filename = filename
            elif filename.endswith((".task", ".json", ".yaml", ".yml")):
                ctx.task_filename = filename
        return ctx

    def __hash__(self) -> int:
        return hash((self.design_filename, self.task_filename, frozenset(self.codes_filenames)))


class CodePlanAndChangeContext(BaseContext):
    """Context for code planning and changes."""

    requirement: str = ""
    issue: str = ""
    prd_filename: str = ""
    design_filename: str = ""
    task_filename: str = ""
    target_files: List[str] = Field(default_factory=list)
    proposed_changes: dict[str, str] = Field(default_factory=dict)
    rationale: str = ""


class PlannerContext(BaseContext):
    """Global planner context for tracking ongoing activities."""

    current_tasks: List[dict] = Field(default_factory=list)
    active_agents: List[str] = Field(default_factory=list)
    resource_usage: dict[str, float] = Field(default_factory=dict)
    ongoing_activities: dict[str, dict] = Field(default_factory=dict)
    system_load: float = 0.0
    available_memory_mb: int = 0
    time_of_day: Literal["morning", "afternoon", "evening", "night"] = "morning"


class TaskContext(BaseContext):
    """Context for individual task execution."""

    task_id: str = Field(default_factory=lambda: uuid4().hex)
    agent_name: str
    start_time: datetime
    estimated_duration: int = 30  # minutes
    actual_duration: Optional[int] = None
    progress: float = 0.0
    status: Literal["pending", "in_progress", "completed", "failed", "blocked"] = "pending"
    retry_count: int = 0
    max_retries: int = 3


class ResourceContext(BaseContext):
    """Context for resource management."""

    cpu_available: float = 1.0
    memory_available_mb: int = 0
    disk_space_mb: int = 0
    network_bandwidth_mbps: float = 100.0
    gpu_available: bool = False
    gpu_memory_mb: int = 0


class PriorityContext(BaseContext):
    """Context for priority management."""

    urgency_level: Literal["low", "medium", "high", "critical"] = "medium"
    business_impact: Literal["low", "medium", "high"] = "medium"
    deadline: Optional[datetime] = None
    SLA: Optional[str] = None


class DependencyContext(BaseContext):
    """Context for task dependencies."""

    dependencies: List[str] = Field(default_factory=list)
    blocking_tasks: List[str] = Field(default_factory=list)
    dependency_graph: dict[str, List[str]] = Field(default_factory=dict)


class TimeContext(BaseContext):
    """Context for time-related information."""

    current_time: datetime = Field(default_factory=datetime.now)
    timezone: str = "UTC"
    working_hours_start: int = 9
    working_hours_end: int = 17
    is_business_hours: bool = True
    day_of_week: int = Field(default_factory=lambda: datetime.now().weekday())


class TaskItem(BaseModel):
    """A single task in the ReAct planning system."""

    task_id: str = Field(default_factory=lambda: uuid4().hex)
    description: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    estimated_duration: Optional[int] = None  # minutes
    status: Literal["pending", "in_progress", "completed"] = "pending"
    dependencies: List[str] = Field(default_factory=list)
    context: Optional[BaseContext] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    def __hash__(self) -> int:
        return hash(self.task_id)


class CodingPlanningTool(BaseModel):
    """Create a standard task plan for a coding objective."""

    context: CodingContext
    goal: str
    complexity: Literal["trivial", "standard", "complex"] = "standard"

    def generate_task_plan(self) -> List[TaskItem]:
        tasks: List[TaskItem] = []

        tasks.append(
            TaskItem(
                description=f"Analyze requirements: {self.goal}",
                priority="high",
                estimated_duration=15,
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Design solution architecture for {self.goal}",
                priority="high",
                estimated_duration=30,
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Implement core functionality for {self.goal}",
                priority="high",
                estimated_duration=60,
                dependencies=[tasks[0].task_id, tasks[1].task_id],
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Write tests for {self.goal}",
                priority="medium",
                estimated_duration=30,
                dependencies=[tasks[2].task_id],
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Review and refine code for {self.goal}",
                priority="medium",
                estimated_duration=15,
                dependencies=[tasks[3].task_id],
                context=self.context,
            )
        )

        return tasks


class TestingPlanningTool(BaseModel):
    """Create a standard task plan for testing a target."""

    context: TestingContext
    target_code: str

    def generate_test_plan(self) -> List[TaskItem]:
        tasks: List[TaskItem] = []

        tasks.append(
            TaskItem(
                description=f"Analyze target code: {self.target_code}",
                priority="high",
                estimated_duration=10,
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Identify test cases for {self.target_code}",
                priority="high",
                estimated_duration=20,
                dependencies=[tasks[0].task_id],
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Write unit tests for {self.target_code}",
                priority="high",
                estimated_duration=30,
                dependencies=[tasks[1].task_id],
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Write integration tests for {self.target_code}",
                priority="medium",
                estimated_duration=20,
                dependencies=[tasks[2].task_id],
                context=self.context,
            )
        )
        tasks.append(
            TaskItem(
                description=f"Run test suite for {self.target_code}",
                priority="high",
                estimated_duration=15,
                dependencies=[tasks[3].task_id],
                context=self.context,
            )
        )

        return tasks
