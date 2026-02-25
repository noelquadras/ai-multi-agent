"""
NODE 1: CODE GENERATOR

Generates initial code based on requirements and an optional technical spec.
Uses the heavy-duty LLM model for code generation.
"""

from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.spec_schema import SpecOutput
from agents.artifacts import save_artifact
from agents.llm_config import check_interrupts, get_llm, clean_code_output, _trimmed_invoke
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event

_code_generator_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert code generator focused on clean, maintainable code."),
    ("human", (
        "You are a Senior Software Developer.\n"
        "Generate complete, runnable PYTHON code for the following requirements:\n\n"
        "{requirements}\n"
        "{spec_section}\n\n"
        "CRITICAL OUTPUT FORMAT:\n"
        "```python\n"
        "# your code here\n"
        "```\n\n"
        "STRICT RULES:\n"
        "- Start IMMEDIATELY with ```python (no text before it)\n"
        "- Write ONLY Python code inside the block\n"
        "- End with ``` (no text after it)\n"
        "- NO explanations, NO comments outside the code block\n"
        "- Code must be syntactically correct and runnable\n"
        "- MUST be Python 3.11+ compatible\n"
        "- DO NOT use input(), open(), or file I/O (sandbox restrictions)\n"
        "- Use print() to show output\n"
        "- Do NOT leave TODOs or placeholder comments\n\n"
        "FORBIDDEN:\n"
        "❌ \"Here's a solution...\"\n"
        "❌ \"This code does...\"\n"
        "❌ Text before or after the code block\n"
        "✅ Start directly with: ```python"
    )),
])


@subscribe(ActionType.PRD_READY, ActionType.ANALYSIS_REGENERATE, node_name="generate")
def code_generator_node(state: AgentState) -> AgentState:
    """Generate initial code based on requirements and optional spec."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "coder"
    })
    
    model_name = state.get("model", "ollama")
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START coder] (using {model_name})"
    })
    
    # Build spec section if available
    spec_section = ""
    if state.get("spec_structured"):
        spec = SpecOutput(**state["spec_structured"])
        spec_section = (
            "\n--- TECHNICAL SPEC (follow this!) ---\n"
            f"- Approach: {spec.implementation_approach}\n"
            f"- Classes/Functions: {spec.class_design}\n"
            f"- Must handle: {', '.join(spec.key_edge_cases)}\n"
            f"- Complexity: {spec.complexity_estimate}\n"
            "---"
        )
    
    messages = _code_generator_prompt.format_messages(
        requirements=state["requirements"],
        spec_section=spec_section,
    )
    
    try:
        # Use heavy-duty model for code generation
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("coder", ""))
        response = _trimmed_invoke(llm, messages)
        code = response.content
        
        # Persist artifact to disk
        save_artifact(state["task_id"], "code/solution.py", clean_code_output(code))
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Generated {len(code)} characters of code"
        })
        
        # EMIT GENERATED CODE FOR FRONTEND PREVIEW
        emit_event(state["task_id"], {
            "type": "code_output",
            "agent": "coder",
            "code": clean_code_output(code)
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "coder"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END coder]"
        })
        
        return {
            "generated_code": code,
            "current_agent": "coder",
            "messages": [make_action_message(
                f"Generated {len(code)} chars of code",
                ActionType.CODE_READY, "generate"
            )],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code generation failed: {str(e)}"
        })
        return {
            "error": str(e),
            "current_agent": "coder"
        }
