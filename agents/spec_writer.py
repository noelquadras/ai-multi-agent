"""
NODE 0: SPEC WRITER (MetaGPT artifact-first)

Produces a technical spec BEFORE code generation, giving the code generator
explicit architectural direction instead of letting the LLM invent everything
from a raw requirements string.
"""

from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime
from pydantic import BaseModel, Field
from agents.state import AgentState
from agents.spec_schema import SpecOutput
from agents.artifacts import save_artifact
from agents.llm_config import check_interrupts, get_llm
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event

_spec_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a software architect who writes concise, actionable technical specs."),
    ("human", (
        "You are a Senior Software Architect.\n"
        "Given the requirements below, produce a concise technical specification.\n\n"
        "Requirements:\n{requirements}\n\n"
        "The spec must cover:\n"
        "1. Implementation approach — what strategy, libraries, and patterns to use\n"
        "2. File list — always [\"solution.py\"] for a single-file solution\n"
        "3. Class/function design — plain-English outline of the key abstractions\n"
        "4. Key edge cases — things the implementation MUST handle\n"
        "5. Complexity estimate — \"simple\", \"medium\", or \"complex\"\n\n"
        "If you need deep research before you can write the spec, call the RequestResearch tool."
    )),
])

@subscribe(ActionType.TASK_CLASSIFIED)
def spec_writer_node(state: AgentState) -> AgentState:
    """
    Produce a technical spec BEFORE code generation.
    
    Gives the code generator explicit architectural direction instead of
    letting the LLM invent everything from a raw requirements string.
    Persists the spec to disk (MetaGPT artifact-first pattern).
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "spec_writer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_START spec_writer]"
    })
    
    # Persist requirement text as the first artifact
    save_artifact(state["task_id"], "requirement.txt", state["requirements"])
    
    messages = _spec_writer_prompt.format_messages(requirements=state["requirements"])
    
    spec_structured = None
    spec_doc_path = None
    
    try:
        base_llm = get_llm(
            for_heavy_task=False, 
            override_model=state.get("agent_models", {}).get("spec_writer", ""),
            base_model=state.get("model", "ollama")
        )
        
        structured_llm = get_llm(
            for_heavy_task=False, 
            override_model=state.get("agent_models", {}).get("spec_writer", ""),
            base_model=state.get("model", "ollama"),
            extra_tools=[SpecOutput],
            bind_request_research=True
        )
        try:
            response = structured_llm.invoke(messages)
            
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                if tool_call["name"] == "RequestResearch":
                    query = tool_call["args"].get("query", state["requirements"])
                    emit_event(state["task_id"], {
                        "type": "log",
                        "message": f"SpecWriter: Handing off to Researcher for: {query}"
                    })
                    return {
                        "messages": [make_action_message(f"Requested research: {query}", ActionType.NEEDS_RESEARCH, "spec_writer")],
                    }
                else:
                    # It's a SpecOutput
                    spec = SpecOutput(**tool_call["args"])
            else:
                # Fallback if it didn't use a tool, force structured output
                spec = base_llm.with_structured_output(SpecOutput).invoke(messages)
                
            spec_structured = spec.model_dump()
            
            # Persist to disk (MetaGPT artifact-first pattern)
            from pathlib import Path
            spec_path = Path(f"tasks/{state['task_id']}/spec/design.json")
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(spec.model_dump_json(indent=2))
            spec_doc_path = str(spec_path)
            
            # Build human-readable spec content for the frontend
            spec_display = (
                f"# Technical Specification\n\n"
                f"## Implementation Approach\n{spec.implementation_approach}\n\n"
                f"## File List\n" + "\n".join(f"- {f}" for f in spec.file_list) + "\n\n"
                f"## Class / Function Design\n{spec.class_design}\n\n"
                f"## Key Edge Cases\n" + "\n".join(f"- {ec}" for ec in spec.key_edge_cases) + "\n\n"
                f"## Complexity Estimate\n{spec.complexity_estimate}\n"
            )
            # Save a readable spec artifact (overwrite to keep latest only)
            save_artifact(state["task_id"], "spec/spec_latest.md", spec_display)

            emit_event(state["task_id"], {
                "type": "spec_output",
                "agent": "spec_writer",
                "spec": spec_display,
                "filename": "spec.md"
            })

            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Spec written: {spec.complexity_estimate} complexity, "
                           f"{len(spec.key_edge_cases)} edge cases identified"
            })
        except Exception as parse_err:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Structured spec extraction failed, continuing without: {parse_err}"
            })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "spec_writer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END spec_writer]"
        })
        
        # Return only new messages — add_messages reducer handles appending
        # Prepare the isolated state update
        spec_data = {
            "spec_doc_path": spec_doc_path,
            "spec_structured": spec_structured,
        }
        
        # Record the event
        complexity = spec_structured.get("complexity_estimate") if spec_structured else "unknown"
        edge_cases_count = len(spec_structured.get("key_edge_cases", [])) if spec_structured else 0
        summary = f"Technical spec completed. Complexity: {complexity}, Edge cases: {edge_cases_count}."
        
        # Initialize execution plan and acceptance criteria if not exists
        exec_plan = state.get("execution_plan") or []
        if not exec_plan:
            exec_plan = [
                {"step_id": 1, "phase": "PLAN", "description": "Write technical specification", "status": "completed"},
                {"step_id": 2, "phase": "MAKE", "description": "Generate and refine code", "status": "pending"},
                {"step_id": 3, "phase": "TEST", "description": "Test code behavior", "status": "pending"}
            ]
        
        acc_criteria = state.get("acceptance_criteria") or {}
        if not acc_criteria and spec_structured:
            acc_criteria = {"must_handle": spec_structured.get("key_edge_cases", [])}

        completion_event = {
            "type": "spec_completed",
            "agent": "spec_writer",
            "timestamp": datetime.now().isoformat(),
            "data": {"complexity": complexity}
        }

        return {
            "agent_states": {"spec_writer": spec_data},
            "messages": [make_action_message(summary, ActionType.PRD_READY, "spec_writer")],
            "events": [completion_event],
            "plan_iterations": state.get("plan_iterations", 0) + 1,
            "execution_plan": exec_plan,
            "acceptance_criteria": acc_criteria
        }
    except Exception as e:
        error_event = {
            "type": "error",
            "agent": "spec_writer",
            "timestamp": datetime.now().isoformat(),
            "data": {"error": str(e)}
        }
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Spec writer failed: {str(e)}"
        })
        return {
            "agent_states": {"spec_writer": {"error": str(e)}},
            "errors": [error_event]
        }
