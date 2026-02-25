"""
NODE 5: DOCUMENTATION WRITER

Generates professional markdown documentation for the final code,
suitable for use as a README.
"""

from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.artifacts import save_artifact
from agents.llm_config import check_interrupts, get_llm, _trimmed_invoke
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event

_doc_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a documentation expert who creates clear, comprehensive technical documentation."),
    ("human", (
        "You are a Senior Technical Writer.\n\n"
        "Write PROFESSIONAL documentation for the following code:\n\n"
        "{final_code}\n\n"
        "Documentation MUST include:\n"
        "• **Overview**: What the code does\n"
        "• **Features**: Key functionality\n"
        "• **Requirements & Dependencies**: What's needed to run it\n"
        "• **Installation**: How to set it up\n"
        "• **Usage Examples**: How to use it\n"
        "• **Implementation Details**: How it works internally\n"
        "• **Known Limitations**: Any constraints\n"
        "• **Future Improvements**: Potential enhancements\n\n"
        "Output MUST be clean, well-formatted markdown suitable for a README."
    )),
])


@subscribe(ActionType.ANALYSIS_PASS, node_name="document")
def doc_writer_node(state: AgentState) -> AgentState:
    """Generate professional documentation."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "doc_writer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START doc_writer]"
    })
    
    # Use refined code if available, otherwise use generated code
    final_code = state.get("refined_code") or state["generated_code"]
    
    messages = _doc_writer_prompt.format_messages(final_code=final_code)
    
    try:
        # Use local model for documentation (cheaper)
        llm = get_llm(for_heavy_task=False, override_model=state.get("agent_models", {}).get("doc_writer", ""))
        response = _trimmed_invoke(llm, messages)
        docs = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Documentation generated: {len(docs)} characters"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "doc_writer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END doc_writer]"
        })
        
        # Persist documentation artifact
        save_artifact(state["task_id"], "docs/README.md", docs)
        
        return {
            "documentation": docs,
            "current_agent": "doc_writer",
            "messages": [make_action_message(
                f"Documentation generated ({len(docs)} chars)",
                ActionType.DOCS_READY, "document"
            )],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Documentation generation failed: {str(e)}"
        })
        return {
            "documentation": "# Documentation\n\nFailed to generate documentation.",
            "error": str(e),
            "current_agent": "doc_writer"
        }
