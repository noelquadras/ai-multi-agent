"""
Shared LLM configuration and utility functions used by all agent nodes.

Contains:
- LLM initialization (Ollama, Groq)
- Model configuration
- Interrupt/cancellation checks
- Code output cleaning
- Message trimming
"""

import re
from typing import Optional
from langchain_core.messages import trim_messages
from langgraph.types import interrupt
from langchain_ollama import ChatOllama
from agents.cancellation import cancellation_registry
from database import get_task_status

# ===========================================
# LLM CONFIGURATION
# ===========================================

# Global LLM instances
_ollama_llm: Optional[ChatOllama] = None
_groq_llm = None
_current_model = "ollama"
_groq_api_key = ""


def get_ollama_llm(model_name: str = None):
    """Get or create Ollama LLM instance."""
    global _ollama_llm, _current_model
    
    # Determine which model to use:
    # 1. Explicit argument (highest priority)
    # 2. Global current_model (from set_model_config)
    # 3. Default fallback
    target_model = model_name or _current_model
    
    # If the choice is generic "ollama", we need a concrete model tag
    if not target_model or target_model == "ollama":
        import os
        target_model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
        
    # Re-initialize if model changed or not initialized
    if _ollama_llm is None or getattr(_ollama_llm, "model", "") != target_model:
        print(f"Initializing Ollama with model: {target_model}")
        _ollama_llm = ChatOllama(
            model=target_model,
            base_url="http://localhost:11434",
            temperature=0.7
        )

    return _ollama_llm


def check_interrupts(task_id: str):
    """
    Check for cancellation and pause status using LangGraph-native primitives.

    Called at the start of every node for cooperative control:
      - **Cancellation** is still handled via the in-process
        ``cancellation_registry`` (threading.Event) because it needs
        sub-second latency.
      - **Pause** now uses ``interrupt()`` from ``langgraph.types``.
        Instead of blocking a thread in a ``while True: time.sleep(1)``
        loop, ``interrupt()`` suspends graph execution and persists the
        current state to the checkpointer.  The thread is released
        immediately.  When the UI/API resumes the task it calls
        ``graph.invoke(Command(resume=True), config)`` which re-enters
        the graph at exactly the node that was interrupted.
    """
    # 1. Cooperative cancellation (ExternalTermination pattern)
    if cancellation_registry.is_cancelled(task_id):
        raise RuntimeError(f"Task {task_id} cancelled by user")

    # 2. Check DB for terminal / paused status
    db_state = get_task_status(task_id)
    if not db_state:
        return  # Task row missing — nothing to check

    status = db_state.get("status")

    if status in ("failed", "completed", "cancelled"):
        raise RuntimeError(f"Task stopped with status: {status}")

    if status == "paused":
        # Suspend the graph without holding a thread.
        # The checkpointer persists state; the API resumes with
        # Command(resume=True) which re-enters this node.
        interrupt({"reason": "paused", "task_id": task_id})


def get_groq_llm(model_name: str = "llama-3.3-70b-versatile"):
    """Get or create Groq LLM instance."""
    global _groq_llm, _groq_api_key
    
    # Use specified model or default to the most capable one
    if _groq_llm is None and _groq_api_key:
        try:
            from langchain_groq import ChatGroq
            _groq_llm = ChatGroq(
                model=model_name,
                api_key=_groq_api_key,
                temperature=0.7
            )
        except ImportError:
            print("Warning: langchain-groq not installed. Using Ollama.")
            return get_ollama_llm()
        except Exception as e:
            print(f"Warning: Could not initialize Groq: {e}. Using Ollama.")
            return get_ollama_llm()
    return _groq_llm or get_ollama_llm()


def set_model_config(model: str, groq_api_key: str = ""):
    """Set the model configuration for this run."""
    global _current_model, _groq_api_key, _groq_llm
    _current_model = model
    _groq_api_key = groq_api_key
    if model == "groq" and groq_api_key:
        _groq_llm = None  # Reset to force re-initialization
        get_groq_llm()  # Initialize immediately


def get_llm(for_heavy_task: bool = False, override_model: str = "", base_model: str = ""):
    """
    Get the appropriate LLM based on configuration and task type.
    
    Args:
        for_heavy_task: If True, use the heavy-duty model (Groq for code gen).
        override_model: Specific model ID for this node (per-agent config).
        base_model: Global model choice for this run (from frontend).
    """
    # 1. Priority: Explicit override for this specific step/agent
    if override_model:
        if "groq" in override_model.lower() or "llama" in override_model.lower() and _groq_api_key:
            return get_groq_llm(model_name=override_model)
        
        # Assume it's a local Ollama model
        return ChatOllama(
            model=override_model,
            base_url="http://localhost:11434",
            temperature=0.7
        )

    # 2. Use the base model choice from the run if provided
    current_choice = base_model or _current_model
    
    # 3. Decision logic: Groq for heavy tasks if selected
    if current_choice == "groq" or "llama" in current_choice.lower():
        if _groq_api_key:
             return get_groq_llm()
        
    return get_ollama_llm(model_name=current_choice)


def clean_code_output(text: str) -> str:
    """Extract code from markdown code blocks, ignoring text outside blocks."""
    if not text:
        return ""
    
    # Try to find code between triple backticks
    # Pattern: ```language\ncode\n```
    code_block_pattern = r"```(?:[a-zA-Z]+)?\s*\n(.*?)```"
    matches = re.findall(code_block_pattern, text, re.DOTALL)
    
    if matches:
        # Return the first code block found
        return matches[0].strip()
    
    # Fallback: if no code blocks found, try removing any explanatory text
    # and return everything after the first line that looks like code
    lines = text.split('\n')
    code_started = False
    code_lines = []
    
    for line in lines:
        # Skip explanatory text at the beginning
        if not code_started:
            # Detect start of code (import, def, class, etc.)
            if line.strip().startswith(('import ', 'from ', 'def ', 'class ', '#', '@')):
                code_started = True
                code_lines.append(line)
        else:
            code_lines.append(line)
    
    if code_lines:
        return '\n'.join(code_lines).strip()
    
    # Last resort: return as-is
    return text.strip()


# ===========================================
# NATIVE MESSAGE TRIMMING (replaces _buffered_messages)
# ===========================================

_trim = trim_messages(
    strategy="last",
    max_tokens=20,
    token_counter=len,
    start_on="human",
    include_system=True,
)


def _trimmed_invoke(llm, messages: list):
    """Trim messages to fit context window, then invoke the LLM."""
    trimmed = _trim.invoke(messages)
    return llm.invoke(trimmed)
