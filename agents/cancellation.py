"""
Cooperative cancellation tokens for running tasks.

Inspired by AutoGen's CancellationToken + ExternalTermination.set().
Each task gets a threading.Event (not asyncio.Event, since the graph
runs in a background thread via threading.Thread).

Usage:
    from agents.cancellation import cancellation_registry

    # In run_crew (background thread):
    cancellation_registry.register(task_id)
    ...
    # In each node:
    if cancellation_registry.is_cancelled(task_id):
        raise RuntimeError("Task cancelled by user")
    ...
    # In API endpoint:
    cancellation_registry.cancel(task_id)
"""

import threading


class TaskCancellationRegistry:
    """Maps task_id → threading.Event for cooperative cancellation."""

    def __init__(self):
        self._tokens: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def register(self, task_id: str) -> threading.Event:
        """Create a fresh cancellation token for a task."""
        token = threading.Event()
        with self._lock:
            self._tokens[task_id] = token
        return token

    def cancel(self, task_id: str):
        """Signal cancellation for a running task."""
        with self._lock:
            token = self._tokens.get(task_id)
        if token:
            token.set()

    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled."""
        with self._lock:
            token = self._tokens.get(task_id)
        return token.is_set() if token else False

    def unregister(self, task_id: str):
        """Clean up after a task completes."""
        with self._lock:
            self._tokens.pop(task_id, None)


cancellation_registry = TaskCancellationRegistry()
