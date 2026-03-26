"""
NODE 1: CODE GENERATOR

Generates initial code based on requirements and an optional technical spec.
Uses the heavy-duty LLM model for code generation.
"""

from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime
from pydantic import BaseModel, Field
from agents.state import AgentState
from agents.spec_schema import SpecOutput
from agents.artifacts import save_code_version
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
        "- If you need DEEP or EXTENSIVE web research beyond quick searches before coding, call the RequestResearch tool.\n"
        "- When generating the code, format it inside a ```python block.\n"
        "- Write ONLY Python code inside the block\n"
        "- End with ``` (no text after it)\n"
        "- Code must be syntactically correct and runnable\n"
        "- MUST be Python 3.11+ compatible\n"
        # "- DO NOT use input(), open(), or file I/O (sandbox restrictions)\n"
        "- Use print() to show output\n"
        "- Do NOT leave TODOs or placeholder comments\n"
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
    llm_states = state.get("agent_states", {})
    spec_data = llm_states.get("spec_writer", {})
    if spec_data.get("spec_structured"):
        spec = SpecOutput(**spec_data["spec_structured"])
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
        llm = get_llm(
            for_heavy_task=True, 
            override_model=state.get("agent_models", {}).get("coder", ""),
            base_model=state.get("model", "ollama"),
            bind_request_research=True
        )

        # ── Streaming pass: show tokens in real-time ─────────────────────
        from database import broadcast_event
        accumulated_text = ""
        tool_calls = []
        try:
            for chunk in llm.stream(messages):
                # Collect tool calls if present
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    tool_calls.extend(chunk.tool_call_chunks)
                token = chunk.content if hasattr(chunk, "content") else ""
                if token:
                    accumulated_text += token
                    broadcast_event(state["task_id"], {
                        "type": "code_stream",
                        "agent": "coder",
                        "chunk": token,
                        "done": False,
                    })
            # Signal stream end
            broadcast_event(state["task_id"], {
                "type": "code_stream",
                "agent": "coder",
                "chunk": "",
                "done": True,
            })
        except Exception as stream_err:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Code streaming failed, falling back to invoke: {stream_err}"
            })
            if not accumulated_text:
                response = _trimmed_invoke(llm, messages)
                accumulated_text = response.content
                if hasattr(response, "tool_calls"):
                    tool_calls = response.tool_calls

        # ── Process tool calls if any ────────────────────────────────────
        # Reconstruct tool calls from streamed chunks
        if tool_calls and not accumulated_text.strip():
            # Aggregate tool call chunks into complete tool calls
            from langchain_core.messages import AIMessageChunk
            aggregated = AIMessageChunk(content="")
            for tc in tool_calls:
                aggregated = aggregated + AIMessageChunk(content="", tool_call_chunks=[tc])
            
            if aggregated.tool_calls:
                first_call = aggregated.tool_calls[0]
                if first_call["name"] == "RequestResearch":
                    query = first_call["args"].get("query", state["requirements"])
                    return {
                        "messages": [make_action_message(f"Requested research: {query}", ActionType.NEEDS_RESEARCH, "generate")],
                        "events": [{
                            "type": "research_requested",
                            "agent": "coder",
                            "timestamp": datetime.now().isoformat(),
                            "data": {"query": query}
                        }]
                    }
            
        # 2. Normal code generation complete
        code = accumulated_text
        clean_code = clean_code_output(code)
        _, version_filename = save_code_version(state["task_id"], clean_code)
        
        emit_event(state["task_id"], {
            "type": "code_output",
            "agent": "coder",
            "code": clean_code,
            "filename": version_filename
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "coder"
        })
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END coder]"
        })
        
        # ── Mutate execution_plan IN MAKE (generate) ─────────────────────────
        import copy
        exec_plan = copy.deepcopy(state.get("execution_plan", []))
        for step in exec_plan:
            if step["phase"] == "MAKE":
                step["status"] = "in_progress"
                break
                
        return {
            "agent_states": {"generate": {"generated_code": clean_code}},
            "messages": [make_action_message(
                f"Generated {len(clean_code)} chars of code",
                ActionType.CODE_READY, "generate"
            )],
            "iteration_count": state.get("iteration_count", 0) + 1,
            "make_iterations": state.get("make_iterations", 0) + 1,
            "execution_plan": exec_plan,
            "events": [{
                "type": "code_generated",
                "agent": "coder",
                "timestamp": datetime.now().isoformat(),
                "data": {"length": len(code)}
            }]
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code generation failed: {str(e)}"
        })
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "coder"
        })
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END coder]"
        })
        return {
            "errors": [{
                "type": "error",
                "agent": "coder",
                "timestamp": datetime.now().isoformat(),
                "data": {"error": str(e)}
            }],
            "messages": [make_action_message(
                f"Code generation failed: {str(e)}",
                ActionType.CODE_READY, "generate"
            )]
        }
