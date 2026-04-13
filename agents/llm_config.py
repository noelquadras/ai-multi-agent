"""
Shared LLM configuration and utility functions used by all agent nodes.

Contains:
- LLM initialization (Ollama, Groq)
- Model configuration
- Interrupt/cancellation checks
- Code output cleaning
- Message trimming
"""

import os
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

# Global LLM instances (lazy-init singletons keyed by model name)
_ollama_llm: Optional[ChatOllama] = None
_groq_llm = None
_current_model = "ollama"

# Tools available to the LLMs
from tools.langchain_tools import search_duckduckgo, search_serper, scrape_web_page
_available_tools = [search_duckduckgo, search_serper, scrape_web_page]

# Models known to NOT support tool calling
_MODELS_WITHOUT_TOOL_SUPPORT = {
    "gemma3:4b", "gemma3:1b", "gemma3",
    "llama2:7b",
}

# Cache for model capability check
_model_tool_support_cache: dict[str, bool] = {}


def check_model_tool_support(model_name: str) -> bool:
    """Check if a model supports tool calling (cached)."""
    if model_name in _model_tool_support_cache:
        return _model_tool_support_cache[model_name]

    # Check against known unsupported models
    model_lower = model_name.lower()
    for unsupported in _MODELS_WITHOUT_TOOL_SUPPORT:
        if unsupported.lower() in model_lower:
            _model_tool_support_cache[model_name] = False
            return False

    # Try binding a tool – if it fails, model doesn't support tools
    try:
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        test_llm = ChatOllama(model=model_name, base_url=ollama_host, temperature=0.1)
        test_llm.bind_tools([search_duckduckgo])
        _model_tool_support_cache[model_name] = True
        return True
    except Exception as e:
        if "does not support tools" in str(e).lower():
            _model_tool_support_cache[model_name] = False
            return False
        return True  # Unknown error – assume tools work


def _is_groq_model(model_id: str) -> bool:
    """
    Determine whether a model ID refers to a Groq cloud model.

    Heuristics:
      1. "/" in id → Groq org/model format (e.g. "qwen/qwen3-32b").
      2. Known Groq-native prefixes without "/".
      3. Literal "groq" in the id.
    """
    lower = model_id.lower()
    if lower in ("", "ollama"):
        return False
    if "/" in model_id:
        return True
    if lower.startswith(("llama", "gemma2-", "mixtral-", "deepseek-", "whisper-")):
        return True
    return "groq" in lower


def _resolve_model(model_name: str | None) -> str:
    """Resolve a model name to a concrete model identifier."""
    if model_name and model_name not in ("ollama", "groq"):
        return model_name
    if model_name == "groq" or _is_groq_model(model_name or ""):
        return "llama-3.3-70b-versatile"
    return os.getenv("OLLAMA_MODEL", "glm-5:cloud")


def _get_ollama(model_name: str) -> ChatOllama:
    """Get or create a cached Ollama LLM for the given model."""
    global _ollama_llm
    if _ollama_llm is None or getattr(_ollama_llm, "model", "") != model_name:
        print(f"Initializing Ollama with model: {model_name}")
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        _ollama_llm = ChatOllama(
            model=model_name,
            base_url=ollama_host,
            temperature=0.7,
        )
    return _ollama_llm


def _get_groq(model_name: str):
    """Get or create a cached Groq LLM for the given model.  Falls back to Ollama."""
    global _groq_llm
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("Warning: GROQ_API_KEY not set. Falling back to Ollama.")
        return _get_ollama(_resolve_model(None))

    current = getattr(_groq_llm, "model_name", "") or getattr(_groq_llm, "model", "")
    if _groq_llm is None or current != model_name:
        try:
            from langchain_groq import ChatGroq
            print(f"Initializing Groq with model: {model_name}")
            _groq_llm = ChatGroq(model=model_name, api_key=api_key, temperature=0.7)
        except ImportError:
            print("Warning: langchain-groq not installed. Falling back to Ollama.")
            return _get_ollama(_resolve_model(None))
        except Exception as e:
            print(f"Warning: Could not initialize Groq: {e}. Falling back to Ollama.")
            return _get_ollama(_resolve_model(None))

    return _groq_llm


def _create_llm(model_name: str):
    """Route to the correct backend (Groq or Ollama) based on the model name."""
    if _is_groq_model(model_name) and os.getenv("GROQ_API_KEY", ""):
        return _get_groq(model_name)
    return _get_ollama(model_name)


# ── Public helpers (backward-compatible names) ──────────────────────────────

def get_ollama_llm(model_name: str = None):
    """Get or create an Ollama LLM instance."""
    return _get_ollama(_resolve_model(model_name))


def get_groq_llm(model_name: str = None):
    """Get or create a Groq LLM instance."""
    return _get_groq(_resolve_model(model_name))


def set_model_config(model: str):
    """Set the default model for this run."""
    global _current_model, _groq_llm
    _current_model = model
    # Pre-warm Groq if applicable
    if _is_groq_model(model) and os.getenv("GROQ_API_KEY", ""):
        _groq_llm = None
        _get_groq(_resolve_model(model))


# ===========================================
# MAIN ENTRY POINT
# ===========================================

def get_llm(
    for_heavy_task: bool = False,   # reserved for future per-tier routing
    override_model: str = "",
    base_model: str = "",
    bind_search_tools: bool = False,
    bind_request_research: bool = False,
    extra_tools: list = None,
):
    """
    Get the appropriate LLM based on configuration and task type.

    Priority: override_model > base_model > _current_model (global default).
    Optionally binds search / research / extra tools if the model supports them.
    """
    target = _resolve_model(override_model or base_model or _current_model)
    llm = _create_llm(target)

    # ── Collect tools to bind ────────────────────────────────────────────
    supports_tools = check_model_tool_support(target)
    if not supports_tools:
        print(f"Warning: Model '{target}' may not support tools. Using plain LLM.")
        return llm

    tools_to_bind: list = []
    if bind_search_tools:
        tools_to_bind.extend(_available_tools)
    if bind_request_research:
        from agents.action_types import RequestResearch
        tools_to_bind.append(RequestResearch)
    if extra_tools:
        tools_to_bind.extend(extra_tools)

    if tools_to_bind:
        try:
            return llm.bind_tools(tools_to_bind)
        except Exception as e:
            print(f"Warning: Failed to bind tools for {target}: {e}. Using plain LLM.")

    return llm


# ===========================================
# INTERRUPT / CANCELLATION
# ===========================================

def check_interrupts(task_id: str):
    """
    Cooperative cancellation & pause check — call at the start of every node.

    - Cancellation uses the in-process cancellation_registry (fast).
    - Pause uses LangGraph's interrupt() to suspend without holding a thread.
    """
    if cancellation_registry.is_cancelled(task_id):
        raise RuntimeError(f"Task {task_id} cancelled by user")

    db_state = get_task_status(task_id)
    if not db_state:
        return

    status = db_state.get("status")
    if status in ("failed", "completed", "cancelled"):
        raise RuntimeError(f"Task stopped with status: {status}")
    if status == "paused":
        interrupt({"reason": "paused", "task_id": task_id})


# ===========================================
# CODE OUTPUT CLEANING
# ===========================================

def clean_code_output(text: str) -> str:
    """Extract code from markdown code blocks, ignoring text outside blocks."""
    if not text:
        return ""

    # Try to find code between triple backticks
    matches = re.findall(r"```(?:[a-zA-Z]+)?\s*\n(.*?)```", text, re.DOTALL)
    if matches:
        return matches[0].strip()

    # Fallback: skip explanatory text, keep lines that look like code
    code_lines, started = [], False
    for line in text.split('\n'):
        if not started:
            if line.strip().startswith(('import ', 'from ', 'def ', 'class ', '#', '@')):
                started = True
                code_lines.append(line)
        else:
            code_lines.append(line)

    return '\n'.join(code_lines).strip() if code_lines else text.strip()


# ===========================================
# MESSAGE TRIMMING
# ===========================================

# token_counter=len → counts NUMBER OF MESSAGES, not tokens.
# max_tokens=15 → keep the last 15 messages.
_trim = trim_messages(
    strategy="last",
    max_tokens=15,
    token_counter=len,
    start_on="human",
    include_system=True,
)


def _trimmed_invoke(llm, messages: list):
    """Trim messages to the last 15, then invoke the LLM."""
    return llm.invoke(_trim.invoke(messages))
