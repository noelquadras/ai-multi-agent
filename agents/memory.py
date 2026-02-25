"""
Per-agent conversation memory (ListMemory pattern).

Inspired by AutoGen's AssistantAgent(memory=[ListMemory(...)]).
Each agent can accumulate short summaries of what it tried in previous
iterations.  The memory is injected as additional context before every
LLM call so the agent avoids repeating failed approaches.

Usage:
    mem = AgentMemory(role="refiner", entries=state.get("refiner_memory") or [])
    memory_ctx = mem.as_system_context()
    # … inject memory_ctx into the prompt …
    mem.add(f"Iteration {n}: fixed [issue1, issue2]")
    return {…, "refiner_memory": mem.entries}
"""

from dataclasses import dataclass, field


@dataclass
class AgentMemory:
    """Per-task memory store for a specific agent role."""

    role: str
    entries: list[str] = field(default_factory=list)
    max_entries: int = 10

    def add(self, entry: str):
        """Append an entry, trimming oldest if over limit."""
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def as_system_context(self) -> str:
        """Format entries as a numbered block suitable for prompt injection."""
        if not self.entries:
            return ""
        numbered = "\n".join(f"{i+1}. {e}" for i, e in enumerate(self.entries))
        return (
            f"\n## Previous {self.role} attempts (most recent last):\n"
            f"{numbered}\n"
            f"IMPORTANT: Do NOT repeat a fix that already failed. Try a different approach.\n"
        )
