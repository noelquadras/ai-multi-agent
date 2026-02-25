"""
NODE 7: TERMINAL ANALYZER

Analyzes raw terminal output to determine if code needs refinement
and what specific fixes are required. Uses structured Pydantic output.
"""

from langchain_core.prompts import ChatPromptTemplate
from agents.state import AgentState
from agents.schemas import AnalysisOutput
from agents.llm_config import check_interrupts, get_llm, _trimmed_invoke
from database import emit_event

_terminal_analyzer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a smart debugger. Analyze runtime errors."),
    ("human", (
        "You are a Python Debugging Expert.\n\n"
        "The code executed but failed with the following output:\n\n"
        "RETURN CODE: {returncode}\n\n"
        "STDOUT:\n{stdout}\n\n"
        "STDERR:\n{stderr}\n\n"
        "TRACEBACK:\n{traceback}\n\n"
        "Analyze the error carefully."
    )),
])


def terminal_analyzer_node(state: AgentState) -> AgentState:
    """
    Analyze the raw terminal output to determine if code needs refinement
    and what specific fixes are required.  Uses structured Pydantic output.
    """
    check_interrupts(state["task_id"])
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "analyzer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": "[AGENT_START analyzer]"
    })
    
    test_output = state.get("test_output", {})
    returncode = test_output.get("returncode")
    stdout = test_output.get("stdout", "")
    stderr = test_output.get("stderr", "")
    traceback_str = test_output.get("traceback", "")
    
    # If successful, skip analysis
    if returncode == 0 and not traceback_str:
        pass_output = AnalysisOutput(
            verdict="PASS", error_type="none", root_cause="", fix_hints=[]
        )
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Analyzer: Code executed successfully. No fix needed."
        })
        return {
            "analysis": "PASS",
            "analysis_structured": pass_output.model_dump(),
            "decision": "NO",
            "current_agent": "analyzer"
        }
    
    messages = _terminal_analyzer_prompt.format_messages(
        returncode=returncode, stdout=stdout,
        stderr=stderr, traceback=traceback_str,
    )
    
    try:
        llm = get_llm(for_heavy_task=True, override_model=state.get("agent_models", {}).get("analyzer", ""))
        structured_llm = llm.with_structured_output(AnalysisOutput)
        
        analysis_output_dict = None
        try:
            result: AnalysisOutput = structured_llm.invoke(messages)
            analysis = f"{result.verdict}: {result.root_cause}" if result.verdict == "FIX_REQUIRED" else "PASS"
            analysis_output_dict = result.model_dump()
        except Exception:
            response = _trimmed_invoke(llm, messages)
            analysis = response.content.strip()
        
        emit_event(state["task_id"], {"type": "log", "message": f"🔍 Analyzer: {analysis}"})
        emit_event(state["task_id"], {"type": "agent_end", "agent": "analyzer"})
        emit_event(state["task_id"], {"type": "log", "message": "[AGENT_END analyzer]"})
        
        return {
            "analysis": analysis,
            "analysis_structured": analysis_output_dict,
            "current_agent": "analyzer",
            "messages": messages
        }
        
    except Exception as e:
        emit_event(state["task_id"], {"type": "system_error", "error": f"Analysis failed: {str(e)}"})
        fallback_output = AnalysisOutput(
            verdict="FIX_REQUIRED", error_type="runtime",
            root_cause="Analyzer failed, please check logs manually.", fix_hints=[]
        )
        return {
            "analysis": "FIX_REQUIRED: Analyzer failed, please check logs manually.",
            "analysis_structured": fallback_output.model_dump(),
            "error": str(e),
            "current_agent": "analyzer"
        }
