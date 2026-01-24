"""
LangGraph agent nodes - each agent is implemented as a node function.
"""

import re
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from agents.state import AgentState
from app import emit_event
from tools.executor import execute

# Initialize LLM
llm = ChatOllama(
    model="mistral:7b-instruct",
    base_url="http://localhost:11434",
    temperature=0.7
    # Let Ollama decide GPU/CPU automatically
    # GPU is faster, CPU is more stable
)


def clean_code_output(text: str) -> str:
    """Extract code from markdown code blocks."""
    if not text:
        return ""
    # Remove markdown code block markers
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", text)
    cleaned = re.sub(r"```", "", cleaned)
    return cleaned.strip()


# ==========================================
# NODE 1: CODE GENERATOR
# ==========================================
def code_generator_node(state: AgentState) -> AgentState:
    """Generate initial code based on requirements."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "coder"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START coder]"
    })
    
    prompt = f"""You are a Senior Software Developer.
Generate complete, runnable code for the following requirements:

{state['requirements']}

STRICT RULES:
- Output ONLY a single code block
- NO explanations before or after
- Code must be syntactically correct and runnable
- Use minimal dependencies unless explicitly required
- Enclose your code in markdown code block (```language ... ```)
"""
    
    messages = [
        SystemMessage(content="You are an expert code generator focused on clean, maintainable code."),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        code = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Generated {len(code)} characters of code"
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
            **state,
            "generated_code": code,
            "current_agent": "coder",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code generation failed: {str(e)}"
        })
        return {
            **state,
            "error": str(e),
            "current_agent": "coder"
        }


# ==========================================
# NODE 2: CODE REVIEWER
# ==========================================
def code_reviewer_node(state: AgentState) -> AgentState:
    """Review generated code for issues."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "reviewer"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START reviewer]"
    })
    
    prompt = f"""You are an Expert QA and Security Auditor.
Review the following code critically:

{state['generated_code']}

You MUST output in exactly this structured format:

### Summary
- Brief overview of code quality (2-3 sentences)

### Detailed Review
- List specific issues, bugs, or security concerns
- Mention style or maintainability problems
- Note any missing error handling

### Final Recommendations
- Bullet list of concrete improvements the refiner must apply

DO NOT write code.
DO NOT rewrite the solution.
DO NOT add extra sections.
"""
    
    messages = [
        SystemMessage(content="You are a meticulous code reviewer focused on security, bugs, and best practices."),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        review = response.content
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Review completed: {len(review)} characters"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "reviewer"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END reviewer]"
        })
        
        return {
            **state,
            "review_report": review,
            "current_agent": "reviewer",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code review failed: {str(e)}"
        })
        return {
            **state,
            "error": str(e),
            "current_agent": "reviewer"
        }


# ==========================================
# NODE 3: DECISION MAKER
# ==========================================
def decision_maker_node(state: AgentState) -> AgentState:
    """Decide if code needs refinement."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "decision"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START decision]"
    })
    
    prompt = f"""Analyze ONLY the code below:

{state['generated_code']}

Question: Does the code have bugs, security vulnerabilities, or incorrect behavior?

STRICT OUTPUT RULE:
Output ONLY ONE WORD: YES or NO
NO punctuation. NO explanation. NO additional text.
"""
    
    messages = [
        SystemMessage(content="You are a deterministic decision auditor. Output only YES or NO."),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        decision = response.content.strip().upper()
        
        # Ensure it's YES or NO
        if "YES" in decision:
            decision = "YES"
        elif "NO" in decision:
            decision = "NO"
        else:
            decision = "YES"  # Default to refinement if unclear
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Decision: {decision}"
        })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "decision"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END decision]"
        })
        
        return {
            **state,
            "decision": decision,
            "current_agent": "decision",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Decision making failed: {str(e)}"
        })
        return {
            **state,
            "decision": "YES",  # Default to refinement on error
            "error": str(e),
            "current_agent": "decision"
        }


# ==========================================
# NODE 4: CODE REFINER
# ==========================================
def code_refiner_node(state: AgentState) -> AgentState:
    """Refine code based on review feedback."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "refiner"
    })
    
    emit_event(state["task_id"], {
        "type": "log",
        "message": f"[AGENT_START refiner]"
    })
    
    prompt = f"""You are a Code Refiner specializing in fixing bugs and applying improvements.

Original Code:
{state['generated_code']}

Review Feedback:
{state['review_report']}

Your task:
1. Read the original code
2. Read the review feedback carefully
3. Apply ALL suggested fixes and improvements
4. Output ONLY the corrected code in a single code block

STRICT OUTPUT RULE:
- Output ONLY a single fenced code block
- NO explanations
- NO comments about what you changed
- Just the final, corrected code
"""
    
    messages = [
        SystemMessage(content="You are a refactoring specialist who fixes code based on feedback."),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = llm.invoke(messages)
        refined_code = response.content
        
        # Try to execute the code if it's Python
        cleaned_code = clean_code_output(refined_code)
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"Attempting to execute refined code..."
        })
        
        result = execute(cleaned_code, timeout_seconds=4)
        
        if result["status"] == "success":
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"✅ Code executed successfully!"
            })
            if result.get("stdout"):
                emit_event(state["task_id"], {
                    "type": "log",
                    "message": f"Output: {result['stdout']}"
                })
        else:
            emit_event(state["task_id"], {
                "type": "log",
                "message": f"⚠️ Execution failed: {result.get('stderr', 'Unknown error')}"
            })
        
        emit_event(state["task_id"], {
            "type": "agent_end",
            "agent": "refiner"
        })
        
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"[AGENT_END refiner]"
        })
        
        return {
            **state,
            "refined_code": refined_code,
            "current_agent": "refiner",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Code refinement failed: {str(e)}"
        })
        return {
            **state,
            "refined_code": state["generated_code"],  # Fallback to original
            "error": str(e),
            "current_agent": "refiner"
        }


# ==========================================
# NODE 5: DOCUMENTATION WRITER
# ==========================================
def doc_writer_node(state: AgentState) -> AgentState:
    """Generate professional documentation."""
    
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
    
    prompt = f"""You are a Senior Technical Writer.

Write PROFESSIONAL documentation for the following code:

{final_code}

Documentation MUST include:
• **Overview**: What the code does
• **Features**: Key functionality
• **Requirements & Dependencies**: What's needed to run it
• **Installation**: How to set it up
• **Usage Examples**: How to use it
• **Implementation Details**: How it works internally
• **Known Limitations**: Any constraints
• **Future Improvements**: Potential enhancements

Output MUST be clean, well-formatted markdown suitable for a README.
"""
    
    messages = [
        SystemMessage(content="You are a documentation expert who creates clear, comprehensive technical documentation."),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = llm.invoke(messages)
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
        
        return {
            **state,
            "documentation": docs,
            "current_agent": "doc_writer",
            "messages": state.get("messages", []) + messages + [response],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    except Exception as e:
        emit_event(state["task_id"], {
            "type": "system_error",
            "error": f"Documentation generation failed: {str(e)}"
        })
        return {
            **state,
            "documentation": "# Documentation\n\nFailed to generate documentation.",
            "error": str(e),
            "current_agent": "doc_writer"
        }


# ==========================================
# CONDITIONAL EDGE: Should Refine?
# ==========================================
def should_refine(state: AgentState) -> str:
    """
    Determine next node based on decision.
    
    Returns:
        "refine" if code needs refinement
        "document" if code is good enough to skip refinement
    """
    decision = state.get("decision", "NO").upper()
    
    if "YES" in decision:
        emit_event(state["task_id"], {
            "type": "log",
            "message": "🔄 Decision: Code needs refinement"
        })
        return "refine"
    else:
        emit_event(state["task_id"], {
            "type": "log",
            "message": "✅ Decision: Code is good, skipping refinement"
        })
        return "document"
