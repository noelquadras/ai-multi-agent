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

# Tools available to the LLMs
from tools.langchain_tools import search_duckduckgo, search_serper, scrape_web_page
_available_tools = [search_duckduckgo, search_serper, scrape_web_page]

# Models known to NOT support tool calling
_MODELS_WITHOUT_TOOL_SUPPORT = {
    "gemma3:4b", "gemma3:1b", "gemma3",  # Gemma 3 small variants
    "llama2:7b",  # Some llama2 variants struggle
}

# Cache for model capability check
_model_tool_support_cache: dict[str, bool] = {}


def check_model_tool_support(model_name: str) -> bool:
    """
    Check if a model supports tool calling.
    Returns True if tools are supported, False otherwise.
    """
    global _model_tool_support_cache
    
    # Check cache first
    if model_name in _model_tool_support_cache:
        return _model_tool_support_cache[model_name]
    
    # Check against known unsupported models
    model_lower = model_name.lower()
    for unsupported in _MODELS_WITHOUT_TOOL_SUPPORT:
        if unsupported.lower() in model_lower:
            _model_tool_support_cache[model_name] = False
            return False
    
    # Try a quick test with the model
    try:
        from langchain_core.messages import HumanMessage
        test_llm = ChatOllama(model=model_name, base_url="http://localhost:11434", temperature=0.1)
        # Try to bind a simple tool - if it fails, model doesn't support tools
        test_llm.bind_tools([search_duckduckgo])
        # If binding succeeded, do a quick test call
        try:
            test_llm.invoke([HumanMessage(content="hi")])
        except Exception:
            pass  # Binding succeeded even if invoke might have issues
        _model_tool_support_cache[model_name] = True
        return True
    except Exception as e:
        # If binding fails, model doesn't support tools
        if "does not support tools" in str(e).lower():
            _model_tool_support_cache[model_name] = False
            return False
        # For other errors, assume tools work (fail gracefully)
        return True


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


def get_groq_llm(model_name: str = None):
    """Get or create Groq LLM instance."""
    global _groq_llm, _groq_api_key
    
    # Default model if none specified or generic "groq" provided
    default_model = "llama-3.3-70b-versatile"
    target_model = model_name or default_model
    
    if target_model.lower() == "groq":
        target_model = default_model
    
    # Re-initialize if:
    # 1. Not initialized yet
    # 2. Model name changed
    # 3. We have an API key
    current_model_name = getattr(_groq_llm, "model_name", "") or getattr(_groq_llm, "model", "")
    
    if _groq_api_key and (_groq_llm is None or current_model_name != target_model):
        try:
            from langchain_groq import ChatGroq
            print(f"Initializing Groq with model: {target_model}")
            _groq_llm = ChatGroq(
                model=target_model,
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


def get_llm(for_heavy_task: bool = False, override_model: str = "", base_model: str = "", bind_search_tools: bool = False, bind_request_research: bool = False, extra_tools: list = None):
    """
    Get the appropriate LLM based on configuration and task type.
    
    Args:
        for_heavy_task: If True, use the heavy-duty model (Groq for code gen).
        override_model: Specific model ID for this node (per-agent config).
        base_model: Global model choice for this run (from frontend).
        bind_search_tools: If True, bind search/scrape tools to the LLM.
                           Only agents that need web access should set this.
        bind_request_research: If True, binds the RequestResearch tool so the agent
                               can delegate deep research gathering to the researcher agent.
        extra_tools: List of extra tools to bind.
    """
    # 1. Priority: Explicit override for this specific step/agent
    if override_model:
        # Check if it's a Groq model (explicitly requested or a known Groq llama model)
        # Avoid matching 'ollama' as 'llama'
        is_groq = "groq" in override_model.lower() or \
                  ("llama" in override_model.lower() and "ollama" not in override_model.lower())
                  
        if is_groq and _groq_api_key:
            llm = get_groq_llm(model_name=override_model)
        else:
            # Default to local Ollama model
            llm = get_ollama_llm(model_name=override_model)
    else:
        # 2. Use the base model choice from the run if provided
        current_choice = base_model or _current_model
        
        # 3. Decision logic: Route to Groq if requested or if it's a cloud llama model
        # Again, ensure 'ollama' doesn't trigger the 'llama' check
        is_groq_choice = current_choice == "groq" or \
                         ("llama" in current_choice.lower() and "ollama" not in current_choice.lower())

        if is_groq_choice and _groq_api_key:
            llm = get_groq_llm(model_name=current_choice)
        else:
            llm = get_ollama_llm(model_name=current_choice)
    
    # Get the actual model name for tool support check
    actual_model = override_model or base_model or _current_model
    if actual_model == "groq":
        actual_model = "llama-3.3-70b-versatile"  # Default Groq model
    
    # Check if model supports tools
    supports_tools = check_model_tool_support(actual_model)
    if not supports_tools:
        print(f"Warning: Model '{actual_model}' may not support tools. Using plain LLM.")
        # Return LLM without tools bound
    
    tools_to_bind = []
    if supports_tools and bind_search_tools:
        tools_to_bind.extend(_available_tools)
    if supports_tools and bind_request_research:
        from agents.action_types import RequestResearch
        tools_to_bind.append(RequestResearch)
    if supports_tools and extra_tools:
        tools_to_bind.extend(extra_tools)
        
    if tools_to_bind:
        try:
            return llm.bind_tools(tools_to_bind)
        except Exception as e:
            print(f"Warning: Failed to bind tools for {actual_model}: {e}. Using plain LLM.")
            return llm
        
    return llm


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

# NOTE: token_counter=len counts NUMBER OF MESSAGES (not tokens).
# So max_tokens=15 means "keep the last 15 messages".
# This is intentional — we want message-count pruning, not token-count pruning,
# because accurate token counting requires a tokenizer we don't have for all models.
_trim = trim_messages(
    strategy="last",
    max_tokens=15,         # Keep last 15 messages
    token_counter=len,     # len(messages) = message count
    start_on="human",
    include_system=True,
)


def _trimmed_invoke(llm, messages: list):
    """Trim messages to fit context window (keeps last 15 messages), then invoke LLM."""
    trimmed = _trim.invoke(messages)
    return llm.invoke(trimmed)

