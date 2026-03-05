"""
NODE 8: RESEARCHER

Inspired by MetaGPT's Researcher role:
Collects links, browses content, summarizes, and produces a final markdown report.
Since it has LangChain tools (`search_duckduckgo`, `search_serper`, `scrape_web_page`)
bound to it automatically by `get_llm()`, it just uses ReAct loop to do its job.
"""

from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.artifacts import save_artifact
from agents.llm_config import check_interrupts, get_llm, _trimmed_invoke
from agents.action_types import ActionType, subscribe, make_action_message
from database import emit_event

_researcher_prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are an expert Researcher agent.\n"
     "Your goal is to gather information from the web to produce a highly accurate, comprehensive research report.\n\n"
     "INSTRUCTIONS:\n"
     "1. Use tools (like web search) to find relevant URLs and information.\n"
     "2. Use tools (like web scraper) to read the content of those URLs if needed.\n"
     "3. Do not stop until you have a solid understanding of the topic.\n"
     "4. When you are finished, output your final Research Report formatted in Markdown.\n\n"
     "DO NOT just output a short answer. Output a fully detailed research report based on your findings."),
    ("human", 
     "The user or another agent requested the following research task:\n"
     "{requirements}\n\n"
     "Please perform thorough research using your tools and output the final markdown report.")
])


@subscribe(ActionType.NEEDS_RESEARCH, node_name="researcher")
def researcher_node(state: AgentState) -> dict:
    """Conduct deep research using tools and create a report."""
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "researcher"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_START researcher] Starting deep research process..."
    })
    
    messages = _researcher_prompt.format_messages(requirements=state["requirements"])
    
    # Check if there's any recent context like a specific "Requested research: {query}" message
    if state.get("messages"):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "content") and "Requested research" in last_msg.content:
            messages.append(("human", f"Specific details from the requester: {last_msg.content}"))
            
    # Include recent tool history if any (in case we are returning from the ToolNode)
    workflow_messages = state.get("messages", [])
    if workflow_messages:
        recent_tool_context = []
        for msg in workflow_messages[-6:]:
            if getattr(msg, "type", "") == "tool" or (hasattr(msg, "tool_calls") and msg.tool_calls):
                recent_tool_context.append(msg)
        messages.extend(recent_tool_context)
    
    try:
        # Use a model for research — needs search tools for web access
        llm = get_llm(
            for_heavy_task=False, 
            override_model=state.get("agent_models", {}).get("researcher", ""),
            base_model=state.get("model", "ollama"),
            bind_search_tools=True
        )
        
        response = _trimmed_invoke(llm, messages)
        
        if hasattr(response, "tool_calls") and response.tool_calls:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"Researcher requested tools: {[t['name'] for t in response.tool_calls]}"
            })
            return {
                "messages": [response]  # Return to router, which will send to 'tools'
            }
            
        research_report = response.content
        
        # Persist report as artifact
        save_artifact(state["task_id"], "research/report.md", research_report)
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Generated research report: {len(research_report)} chars"
        })
        
        # Also emit doc_output so frontend can see it immediately
        emit_event(state["task_id"], {
            "type": "doc_output",  # re-using doc_output channel for frontend visibility
            "agent": "researcher",
            "documentation": research_report
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "researcher"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": "[AGENT_END researcher]"
        })
        
        return {
            "agent_states": {"researcher": {"research_report": research_report}},
            "messages": [make_action_message(
                f"Research complete. Report generated ({len(research_report)} chars).",
                ActionType.RESEARCH_READY, 
                "researcher"
            )],
            "events": [{
                "type": "research_completed",
                "agent": "researcher",
                "timestamp": datetime.now().isoformat(),
                "data": {"report_length": len(research_report)}
            }]
        }
        
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Researcher failed: {str(e)}"
        })
        return {
            "agent_states": {"researcher": {"error": str(e)}},
            "errors": [{
                "type": "error",
                "agent": "researcher",
                "timestamp": datetime.now().isoformat(),
                "data": {"error": str(e)}
            }],
            "messages": [make_action_message(
                f"Research failed: {str(e)}",
                ActionType.RESEARCH_READY,
                "researcher"
            )]
        }
