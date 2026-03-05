"""
Smart Manager Tools - Inspired by MetaGPT's RoleZero.

Features:
- Intent Classification (QUICK/SEARCH/TASK/AMBIGUOUS)
- Dynamic Task Planning (CreateTask, AppendTask, ReplaceTask, FinishTask)
- In-memory Experience Cache for routing decisions
- Duplicate Response Detection
"""

import hashlib
import json
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    """Classify user intent to determine routing strategy."""
    intent: str = Field(
        description="Classification result: QUICK (simple answer), SEARCH (needs web info), "
                    "TASK (requires agent work), AMBIGUOUS (unclear request)"
    )
    reasoning: str = Field(description="Brief reasoning for the classification")


class TaskInfo(BaseModel):
    """Information about a single task in the plan."""
    task_id: str = Field(description="Unique task identifier")
    instruction: str = Field(description="What this task entails")
    task_type: str = Field(description="Type: spec, code, review, test, docs, research")
    assignee: str = Field(default="", description="Agent assigned to this task")
    dependent_task_ids: list[str] = Field(default_factory=list, description="Tasks that must complete first")
    is_finished: bool = Field(default=False, description="Whether this task is completed")
    result: str = Field(default="", description="Task execution result")


class CreatePlan(BaseModel):
    """Create a new task plan from requirements."""
    tasks: list[TaskInfo] = Field(description="List of tasks to create")
    goal: str = Field(description="Overall goal these tasks aim to achieve")


class AppendTask(BaseModel):
    """Append new tasks to the existing plan."""
    tasks: list[TaskInfo] = Field(description="New tasks to append to the plan")


class ReplaceTask(BaseModel):
    """Replace a specific task with new instructions."""
    task_id: str = Field(description="ID of the task to replace")
    new_instruction: str = Field(description="New instruction for the task")
    new_task_type: str = Field(description="New task type")


class FinishTask(BaseModel):
    """Mark a task as finished and optionally record results."""
    task_id: str = Field(description="ID of the task to finish")
    result: str = Field(default="", description="Execution result or summary")


class QuickResponse(BaseModel):
    """Provide a direct answer without agent delegation."""
    response: str = Field(description="The direct response to the user")


class SearchInfo(BaseModel):
    """Perform a search and provide results."""
    query: str = Field(description="Search query")
    response: str = Field(description="Search results or direct answer")


class RetryWithStrategy(BaseModel):
    """Retry the last action with a different approach."""
    strategy: str = Field(description="Different strategy to try: 'use_different_agent', 'simplify_task', 'break_into_steps', 'ask_human'")
    reasoning: str = Field(description="Why this strategy might work")


# In-memory experience cache for routing decisions
class ExperienceCache:
    """
    Simple in-memory cache for successful routing decisions.
    Stores (requirement_pattern, routing_decision) pairs.
    """
    
    def __init__(self, max_size: int = 100):
        self._cache: dict[str, dict] = {}
        self._max_size = max_size
        self._response_hashes: dict[str, list[str]] = {}  # task_id -> list of response hashes
    
    def _hash_requirement(self, req: str) -> str:
        """Create a simple hash of the requirement for caching."""
        return hashlib.sha256(req.lower().strip().encode()).hexdigest()[:16]
    
    def get_routing(self, requirement: str) -> Optional[dict]:
        """Get cached routing decision for similar requirement."""
        key = self._hash_requirement(requirement)
        return self._cache.get(key)
    
    def store_routing(self, requirement: str, routing: dict):
        """Store successful routing decision."""
        key = self._hash_requirement(requirement)
        if len(self._cache) >= self._max_size:
            # Simple FIFO eviction
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = {
            "routing": routing,
            "timestamp": datetime.now().isoformat()
        }
    
    def track_response(self, task_id: str, response_content: str):
        """Track a response hash for duplicate detection."""
        if task_id not in self._response_hashes:
            self._response_hashes[task_id] = []
        
        # Hash the response content
        content_hash = hashlib.sha256(response_content.encode()).hexdigest()
        self._response_hashes[task_id].append(content_hash)
        
        # Keep only last 10 hashes per task
        if len(self._response_hashes[task_id]) > 10:
            self._response_hashes[task_id] = self._response_hashes[task_id][-10:]
    
    def is_duplicate_response(self, task_id: str, response_content: str, threshold: int = 3) -> bool:
        """Check if response is duplicate (repeated threshold times)."""
        if task_id not in self._response_hashes:
            return False
        
        content_hash = hashlib.sha256(response_content.encode()).hexdigest()
        hashes = self._response_hashes[task_id]
        
        # Count occurrences of this hash
        count = hashes.count(content_hash)
        return count >= threshold
    
    def get_duplicate_count(self, task_id: str, response_content: str) -> int:
        """Get count of how many times this response has appeared."""
        if task_id not in self._response_hashes:
            return 0
        content_hash = hashlib.sha256(response_content.encode()).hexdigest()
        return self._response_hashes[task_id].count(content_hash)
    
    def clear_task(self, task_id: str):
        """Clear tracking for a completed task."""
        if task_id in self._response_hashes:
            del self._response_hashes[task_id]


# Global experience cache instance
experience_cache = ExperienceCache()


# Quick thinking prompt for intent classification
QUICK_THINK_PROMPT = """You are a classifier determining the appropriate response strategy.

Classify the user's request into one of these categories:

## QUICK
For straightforward questions answerable directly:
- General knowledge questions
- Simple math or coding questions
- Greetings and casual chat
- "How-to" questions seeking general guidance
- Requests that don't require tool usage

## SEARCH  
For queries requiring up-to-date or external information:
- Current events, weather, stock prices
- Information that may have changed recently
- Specific technical docs or tutorials

## TASK
For requests requiring agent work and tool usage:
- Software development tasks
- File creation or editing
- Multi-step workflows
- Anything requiring code execution
- Project planning or analysis

## AMBIGUOUS
For unclear or incomplete requests:
- Missing critical details
- Vague or overly broad requests
- Requests referencing files not provided

Respond with ONLY a JSON object:
{{"intent": "QUICK|SEARCH|TASK|AMBIGUOUS", "reasoning": "brief explanation"}}

User request: {requirement}

Remember: Only classify as QUICK if it truly doesn't need agent work. Most software tasks are TASK."""

