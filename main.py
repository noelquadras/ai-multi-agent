# main.py
import os
import re
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes import (
    code_generator_node,
    code_reviewer_node,
    decision_maker_node,
    code_refiner_node,
    doc_writer_node,
    should_refine
)
from app import emit_event

load_dotenv()

# Configure environment
os.environ["OPENAI_API_KEY"] = "na"
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_MODEL_NAME"] = "mistral:7b-instruct"
# Let Ollama use GPU for better performance


def clean_output(text: str) -> str:
    """Clean markdown code blocks from text."""
    if not text:
        return ""
    return re.sub(r"```[a-zA-Z]*|```", "", text).strip()


def create_agent_graph():
    """
    Create the LangGraph state graph for the agent workflow.
    
    Graph structure:
        START → generate → review → decide → [conditional] → document → END
                                              ↓
                                           refine → document
    """
    # Initialize graph with state schema
    workflow = StateGraph(AgentState)
    
    # Add nodes (each agent is a node)
    workflow.add_node("generate", code_generator_node)
    workflow.add_node("review", code_reviewer_node)
    workflow.add_node("decide", decision_maker_node)
    workflow.add_node("refine", code_refiner_node)
    workflow.add_node("document", doc_writer_node)
    
    # Define edges (workflow connections)
    workflow.set_entry_point("generate")
    
    # Sequential flow
    workflow.add_edge("generate", "review")
    workflow.add_edge("review", "decide")
    
    # Conditional edge: refine or skip to documentation
    workflow.add_conditional_edges(
        "decide",
        should_refine,
        {
            "refine": "refine",
            "document": "document"
        }
    )
    
    # Both paths lead to documentation
    workflow.add_edge("refine", "document")
    workflow.add_edge("document", END)
    
    return workflow.compile()


def run_software_crew(requirements: str, task_id: str):
    """
    Execute the LangGraph agent workflow.
    
    Args:
        requirements: User's code requirements
        task_id: Unique task identifier
        
    Returns:
        Final state with all agent outputs
    """
    # Create the graph
    graph = create_agent_graph()
    
    # Initial state
    initial_state: AgentState = {
        "requirements": requirements,
        "task_id": task_id,
        "generated_code": "",
        "review_report": "",
        "decision": "",
        "refined_code": "",
        "documentation": "",
        "messages": [],
        "current_agent": "",
        "error": None,
        "iteration_count": 0
    }
    
    print("\n--- RUNNING LANGGRAPH WORKFLOW ---\n", flush=True)
    
    # Execute the graph
    final_state = graph.invoke(initial_state)
    
    print("\n--- WORKFLOW COMPLETE ---\n", flush=True)
    
    # =========================
    # EMIT FINAL RESULTS
    # =========================
    
    # Final code (use refined if available, otherwise generated)
    final_code = clean_output(final_state.get("refined_code") or final_state["generated_code"])
    
    emit_event(task_id, {
        "type": "code_output",
        "agent": "refiner",
        "code": final_code
    })
    
    emit_event(task_id, {
        "type": "review_output",
        "agent": "reviewer",
        "review": final_state["review_report"]
    })
    
    emit_event(task_id, {
        "type": "decision_output",
        "agent": "decision",
        "decision": final_state["decision"]
    })
    
    emit_event(task_id, {
        "type": "doc_output",
        "agent": "doc_writer",
        "documentation": final_state["documentation"]
    })
    
    emit_event(task_id, {"type": "task_completed"})
    
    # Return results in expected format
    results = {
        "generated_code": clean_output(final_state["generated_code"]),
        "review_report": final_state["review_report"],
        "decision": final_state["decision"],
        "refined_code": final_code,
        "documentation": final_state["documentation"]
    }
    
    return results


if __name__ == "__main__":
    req = input("Enter requirements: ")
    result = run_software_crew(req, task_id="debug")
    print(result)