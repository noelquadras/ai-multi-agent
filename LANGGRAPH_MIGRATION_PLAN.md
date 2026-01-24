# 🔄 Migration Plan: CrewAI → LangGraph

## 📊 Overview

This document outlines the complete migration from **CrewAI** to **LangGraph** for the AI Multi-Agent system.

---

## 🎯 Why LangGraph?

### **Advantages:**
1. **Better Control**: Fine-grained control over agent workflow
2. **Conditional Logic**: Easy branching based on agent outputs
3. **State Management**: Built-in state tracking across nodes
4. **Transparency**: Clear visualization of agent graph
5. **Flexibility**: Easier to add/remove agents dynamically
6. **Debugging**: Better error handling and logging
7. **Performance**: More efficient for complex workflows

### **Trade-offs:**
- More code to write (but more maintainable)
- Lower-level API (but more powerful)
- Need to handle more orchestration logic manually

---

## 🏗️ New Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INPUT                                │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              LANGGRAPH STATE GRAPH                           │
│                                                              │
│  ┌──────────────┐                                           │
│  │   START      │                                           │
│  └──────┬───────┘                                           │
│         ↓                                                    │
│  ┌──────────────┐                                           │
│  │  Code Gen    │ (Node 1)                                  │
│  │   Agent      │                                           │
│  └──────┬───────┘                                           │
│         ↓                                                    │
│  ┌──────────────┐     ┌──────────────┐                     │
│  │  Reviewer    │────→│  Decision    │ (Parallel)          │
│  │   Agent      │     │   Agent      │                     │
│  └──────┬───────┘     └──────┬───────┘                     │
│         ↓                     ↓                              │
│         └──────────┬──────────┘                             │
│                    ↓                                         │
│         ┌──────────────────┐                                │
│         │  Conditional     │                                │
│         │  Edge: Refine?   │                                │
│         └──────┬───────────┘                                │
│                ↓                                             │
│         YES ┌──────────────┐ NO                             │
│         ───→│  Refiner     │───→ (Skip)                     │
│             │   Agent      │                                │
│             └──────┬───────┘                                │
│                    ↓                                         │
│             ┌──────────────┐                                │
│             │  Doc Writer  │                                │
│             │   Agent      │                                │
│             └──────┬───────┘                                │
│                    ↓                                         │
│             ┌──────────────┐                                │
│             │     END      │                                │
│             └──────────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Step 1: Update Dependencies

### **requirements.txt**

**REMOVE:**
```txt
crewai
```

**ADD:**
```txt
langgraph
langchain
langchain-community
langchain-core
```

**Updated requirements.txt:**
```txt
# LLM & Orchestration
langgraph
langchain
langchain-community
langchain-core
langchain-ollama
litellm

# API & Server
fastapi
uvicorn
python-multipart
pydantic
python-dotenv

# Utilities
cors
```

---

## 📝 Step 2: Define State Schema

### **New File: `agents/state.py`**

```python
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    """
    Shared state across all agent nodes in the graph.
    """
    # Input
    requirements: str
    task_id: str
    
    # Agent Outputs
    generated_code: str
    review_report: str
    decision: str  # "YES" or "NO"
    refined_code: str
    documentation: str
    
    # Metadata
    messages: Annotated[Sequence[BaseMessage], operator.add]
    current_agent: str
    error: str | None
    iteration_count: int
```

---

## 🤖 Step 3: Rewrite Agents as Nodes

### **New File: `agents/nodes.py`**

```python
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
)

# ==========================================
# NODE 1: CODE GENERATOR
# ==========================================
def code_generator_node(state: AgentState) -> AgentState:
    """Generate initial code based on requirements."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "coder"
    })
    
    prompt = f"""You are a Senior Software Developer.
Generate complete, runnable code for:

{state['requirements']}

RULES:
- Output ONLY a single code block
- No explanations
- Syntactically correct
- Use minimal dependencies
"""
    
    messages = [
        SystemMessage(content="You are an expert code generator."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    code = response.content
    
    emit_event(state["task_id"], {
        "type": "agent_end",
        "agent": "coder"
    })
    
    return {
        **state,
        "generated_code": code,
        "current_agent": "coder",
        "messages": state.get("messages", []) + messages + [response]
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
    
    prompt = f"""You are an Expert QA and Security Auditor.
Review this code:

{state['generated_code']}

Output a structured review:

### Summary
[Brief overview]

### Issues
- [List specific problems]

### Recommendations
- [Concrete improvements]
"""
    
    messages = [
        SystemMessage(content="You are a critical code reviewer."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    review = response.content
    
    emit_event(state["task_id"], {
        "type": "agent_end",
        "agent": "reviewer"
    })
    
    return {
        **state,
        "review_report": review,
        "current_agent": "reviewer",
        "messages": state.get("messages", []) + messages + [response]
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
    
    prompt = f"""Analyze this code:

{state['generated_code']}

Does it have bugs, security issues, or incorrect behavior?

Output ONLY: YES or NO
"""
    
    messages = [
        SystemMessage(content="You are a decision auditor."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    decision = response.content.strip().upper()
    
    emit_event(state["task_id"], {
        "type": "agent_end",
        "agent": "decision"
    })
    
    return {
        **state,
        "decision": decision,
        "current_agent": "decision",
        "messages": state.get("messages", []) + messages + [response]
    }

# ==========================================
# NODE 4: CODE REFINER
# ==========================================
def code_refiner_node(state: AgentState) -> AgentState:
    """Refine code based on review."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "refiner"
    })
    
    prompt = f"""You are a Code Refiner.

Original Code:
{state['generated_code']}

Review Feedback:
{state['review_report']}

Apply ALL suggestions and output ONLY the corrected code block.
"""
    
    messages = [
        SystemMessage(content="You are a refactoring specialist."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    refined_code = response.content
    
    # Try to execute the code
    result = execute(refined_code)
    
    if result["status"] == "success":
        emit_event(state["task_id"], {
            "type": "log",
            "message": f"✅ Code executed successfully: {result['stdout']}"
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
    
    return {
        **state,
        "refined_code": refined_code,
        "current_agent": "refiner",
        "messages": state.get("messages", []) + messages + [response]
    }

# ==========================================
# NODE 5: DOCUMENTATION WRITER
# ==========================================
def doc_writer_node(state: AgentState) -> AgentState:
    """Generate documentation."""
    
    emit_event(state["task_id"], {
        "type": "agent_start",
        "agent": "doc_writer"
    })
    
    final_code = state.get("refined_code") or state["generated_code"]
    
    prompt = f"""You are a Technical Writer.

Write professional documentation for this code:

{final_code}

Include:
- Overview
- Features
- Requirements
- Installation
- Usage
- Implementation details
"""
    
    messages = [
        SystemMessage(content="You are a documentation expert."),
        HumanMessage(content=prompt)
    ]
    
    response = llm.invoke(messages)
    docs = response.content
    
    emit_event(state["task_id"], {
        "type": "agent_end",
        "agent": "doc_writer"
    })
    
    return {
        **state,
        "documentation": docs,
        "current_agent": "doc_writer",
        "messages": state.get("messages", []) + messages + [response]
    }

# ==========================================
# CONDITIONAL EDGE: Should Refine?
# ==========================================
def should_refine(state: AgentState) -> str:
    """Determine next node based on decision."""
    decision = state.get("decision", "NO").upper()
    
    if "YES" in decision:
        return "refine"
    else:
        return "document"
```

---

## 🔗 Step 4: Build the Graph

### **Updated: `main.py`**

```python
import os
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

# Disable telemetry
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"

# ==========================================
# BUILD LANGGRAPH WORKFLOW
# ==========================================
def create_agent_graph():
    """Create the LangGraph state graph."""
    
    # Initialize graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("generate", code_generator_node)
    workflow.add_node("review", code_reviewer_node)
    workflow.add_node("decide", decision_maker_node)
    workflow.add_node("refine", code_refiner_node)
    workflow.add_node("document", doc_writer_node)
    
    # Define edges
    workflow.set_entry_point("generate")
    
    # Sequential flow
    workflow.add_edge("generate", "review")
    workflow.add_edge("review", "decide")
    
    # Conditional edge: refine or skip
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

# ==========================================
# RUN WORKFLOW
# ==========================================
def run_software_crew(requirements: str, task_id: str):
    """Execute the agent workflow."""
    
    # Create graph
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
    
    # Execute graph
    final_state = graph.invoke(initial_state)
    
    print("\n--- WORKFLOW COMPLETE ---\n", flush=True)
    
    # Emit final results
    emit_event(task_id, {
        "type": "code_output",
        "agent": "refiner",
        "code": final_state.get("refined_code") or final_state["generated_code"]
    })
    
    emit_event(task_id, {
        "type": "review_output",
        "agent": "reviewer",
        "review": final_state["review_report"]
    })
    
    emit_event(task_id, {
        "type": "doc_output",
        "agent": "doc_writer",
        "documentation": final_state["documentation"]
    })
    
    emit_event(task_id, {"type": "task_completed"})
    
    return final_state

if __name__ == "__main__":
    req = input("Enter requirements: ")
    result = run_software_crew(req, task_id="debug")
    print("\n=== FINAL CODE ===")
    print(result.get("refined_code") or result["generated_code"])
```

---

## 🗑️ Step 5: Remove Old Files

**Delete or Archive:**
- `agents/config.py` (replaced by `agents/nodes.py`)
- `tasks/tasks.py` (logic moved to nodes and edges)

---

## 🧪 Step 6: Testing

### **Test Script: `test_langgraph.py`**

```python
from main import run_software_crew

# Test simple task
result = run_software_crew(
    requirements="Create a function that adds two numbers",
    task_id="test_001"
)

print("Generated Code:", result["generated_code"])
print("Review:", result["review_report"])
print("Decision:", result["decision"])
print("Final Code:", result.get("refined_code", "Not refined"))
print("Documentation:", result["documentation"])
```

---

## 📊 Comparison: Before vs After

| Feature | CrewAI | LangGraph |
|---------|--------|-----------|
| **Control** | High-level | Low-level (more control) |
| **Conditional Logic** | Limited | Full support |
| **State Management** | Implicit | Explicit (TypedDict) |
| **Visualization** | Basic | Graph visualization |
| **Debugging** | Harder | Easier (clear state) |
| **Parallel Execution** | Built-in | Manual (but flexible) |
| **Code Complexity** | Less code | More code (but clearer) |

---

## 🚀 Migration Steps

### **Phase 1: Preparation** (30 mins)
1. ✅ Backup current code
2. ✅ Create new branch: `git checkout -b langgraph-migration`
3. ✅ Read LangGraph documentation

### **Phase 2: Dependencies** (10 mins)
1. ✅ Update `requirements.txt`
2. ✅ Uninstall CrewAI: `pip uninstall crewai`
3. ✅ Install LangGraph: `pip install langgraph langchain langchain-community`

### **Phase 3: Core Migration** (2 hours)
1. ✅ Create `agents/state.py`
2. ✅ Create `agents/nodes.py`
3. ✅ Update `main.py`
4. ✅ Update `tools/executor.py` (if needed)

### **Phase 4: Testing** (1 hour)
1. ✅ Test each node individually
2. ✅ Test full workflow
3. ✅ Test with frontend
4. ✅ Fix any issues

### **Phase 5: Cleanup** (30 mins)
1. ✅ Remove old CrewAI files
2. ✅ Update documentation
3. ✅ Update `present_overview.md`

---

## 🎯 Benefits After Migration

1. **Better Debugging**: Clear state at each step
2. **Easier Testing**: Test individual nodes
3. **More Flexible**: Easy to add/remove agents
4. **Conditional Logic**: Skip refiner if code is perfect
5. **Visualization**: See the agent graph visually
6. **Performance**: Optimize specific nodes
7. **Error Handling**: Better error recovery

---

## 📈 Expected Results

- **Same Functionality**: All 5 agents still work
- **Better Performance**: Conditional skipping saves time
- **Clearer Code**: Explicit state management
- **Easier Maintenance**: Modular node structure
- **More Testable**: Unit test each node

---

## 🔧 Advanced Features (Future)

Once migrated, you can easily add:

1. **Parallel Execution**: Run reviewer + decision in parallel
2. **Human-in-the-Loop**: Add approval nodes
3. **Retry Logic**: Retry failed nodes
4. **Dynamic Routing**: Route based on code complexity
5. **Checkpointing**: Save/resume workflows
6. **Multi-Language**: Add nodes for different languages

---

## 📚 Resources

- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **LangGraph Tutorial**: https://python.langchain.com/docs/langgraph
- **State Management**: https://langchain-ai.github.io/langgraph/concepts/low_level/
- **Conditional Edges**: https://langchain-ai.github.io/langgraph/how-tos/branching/

---

## ✅ Checklist

- [ ] Backup current code
- [ ] Update dependencies
- [ ] Create state schema
- [ ] Implement nodes
- [ ] Build graph
- [ ] Test workflow
- [ ] Update frontend (if needed)
- [ ] Update documentation
- [ ] Deploy

---

**Estimated Migration Time**: 3-4 hours
**Difficulty**: Medium
**Risk**: Low (can revert to CrewAI if needed)

---

**Ready to start?** Let me know and I can help you implement this step by step! 🚀
