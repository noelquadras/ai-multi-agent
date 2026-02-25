"""
NODE 0: SPEC WRITER (MetaGPT artifact-first)

Produces a technical spec BEFORE code generation, giving the code generator
explicit architectural direction instead of letting the LLM invent everything
from a raw requirements string.
"""

from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.spec_schema import SpecOutput
from agents.artifacts import save_artifact
from agents.llm_config import check_interrupts, get_llm
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
        "5. Complexity estimate — \"simple\", \"medium\", or \"complex\""
    )),
])


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
    
    try:
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("spec_writer", ""))
        structured_llm = llm.with_structured_output(SpecOutput)
        
        spec_structured = None
        spec_doc_path = None
        try:
            spec: SpecOutput = structured_llm.invoke(messages)
            spec_structured = spec.model_dump()
            
            # Persist to disk (MetaGPT artifact-first pattern)
            from pathlib import Path
            spec_path = Path(f"tasks/{state['task_id']}/spec/design.json")
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(spec.model_dump_json(indent=2))
            spec_doc_path = str(spec_path)
            
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
        return {
            "spec_doc_path": spec_doc_path,
            "spec_structured": spec_structured,
            "current_agent": "spec_writer",
            "messages": messages,  # new messages only; reducer appends
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Spec writer failed: {str(e)}"
        })
        # Non-fatal — downstream generate will still work without a spec
        return {
            "spec_doc_path": None,
            "spec_structured": None,
            "error": str(e),
            "current_agent": "spec_writer"
        }
