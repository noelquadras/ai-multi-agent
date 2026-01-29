# 🎓 AI Multi-Agent Software Development System - VIVA Preparation Guide

## 📋 Quick Summary (Elevator Pitch)

> **What is this project?**
> 
> This is an **autonomous AI-powered software development system** that uses **6 specialized AI agents** working collaboratively like a real software development team. You give it a natural language requirement (like "create a login form"), and it automatically **generates code, reviews it, fixes bugs, tests it, and writes documentation** - all powered by local AI models!

---

## 🏗️ Project Architecture - Simple Explanation

```
┌─────────────────────────────────────────────────────────────┐
│                    👤 USER (You)                            │
│              "Create a calculator app"                       │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              🌐 FRONTEND (What user sees)                   │
│                                                              │
│   • Built with Next.js 16 + React 19                        │
│   • Shows agent status, code editor, activity log           │
│   • Runs on http://localhost:3000                           │
│   • Uses Monaco Editor (same as VS Code!)                   │
└──────────────────────┬──────────────────────────────────────┘
                       ↓ HTTP/SSE (Real-time events)
┌─────────────────────────────────────────────────────────────┐
│              🔧 BACKEND (FastAPI Server)                    │
│                                                              │
│   • Python 3.11 + FastAPI                                   │
│   • Handles API requests                                    │
│   • Streams events to frontend via SSE                      │
│   • Runs on http://localhost:8000                           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              🧠 AI ORCHESTRATION (LangGraph)                │
│                                                              │
│   • Manages 6 AI agents as a workflow                       │
│   • State management between agents                         │
│   • Conditional routing (skip steps if not needed)          │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              🤖 LLM (Ollama/Groq)                           │
│                                                              │
│   • Local: Ollama with Mistral 7B (FREE, PRIVATE)          │
│   • Cloud: Groq with Llama 3.3 70B (FASTER)                │
│   • The "brain" that actually generates text/code          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤖 The 6 AI Agents Explained

Think of these as 6 different people in a software company, each with a specific job:

### 1. 👨‍💻 Code Generator (Senior Developer)
**Job:** Takes your requirements and writes the initial code

**In Simple Words:** 
- Acts like a senior programmer who can understand what you want
- Writes clean, working code from scratch
- Focuses on making the code runnable and correct

**Example:**
- Input: "Create a function to calculate factorial"
- Output: A complete Python function with proper logic

---

### 2. 🔍 Code Reviewer (QA Engineer)
**Job:** Reviews the generated code for bugs and issues

**In Simple Words:**
- Like a quality checker who finds problems
- Looks for bugs, security issues, and bad practices
- Creates a structured report with recommendations

**What it checks:**
- ✓ Security vulnerabilities
- ✓ Logic errors
- ✓ Code style issues
- ✓ Performance problems

---

### 3. ⚖️ Decision Maker (System Auditor)
**Job:** Decides if the code needs fixing

**In Simple Words:**
- Simple judge that says YES or NO
- If YES → code goes to refiner for fixes
- If NO → code is good enough, skip refining

**Why it's important:**
- Saves time by not refining already-good code
- This is the "conditional logic" feature of LangGraph

---

### 4. 🔧 Code Refiner (Junior Developer)
**Job:** Fixes the code based on review feedback

**In Simple Words:**
- Takes the original code + review comments
- Applies all the suggested fixes
- Makes the code better and cleaner

**Special Feature:**
- Can EXECUTE the code to verify it works!
- Tests it in a sandboxed environment

---

### 5. 🧪 CLI Tester (Tester)
**Job:** Runs the code and captures output

**In Simple Words:**
- Like pressing "Run" in an IDE
- Executes the code in a safe sandbox
- Captures success/failure/output

**This is a "Patent Feature":**
- Unique to our project
- Automated testing with live output
- Reports ✅ PASSED, ❌ FAILED, or ⏱️ TIMEOUT

---

### 6. 📝 Documentation Writer (Technical Writer)
**Job:** Creates professional documentation

**In Simple Words:**
- Writes a README file automatically
- Explains what the code does
- Includes usage examples and installation steps

**What it generates:**
- Overview
- Features
- Requirements
- Usage Examples
- Implementation Details

---

## 🔄 The Complete Workflow

```
User: "Create a login form with validation"
                │
                ↓
   ┌────────────────────────┐
   │   1. CODE GENERATOR    │  ← Writes initial code
   └───────────┬────────────┘
               ↓
   ┌────────────────────────┐
   │    2. CODE REVIEWER    │  ← Reviews for bugs
   └───────────┬────────────┘
               ↓
   ┌────────────────────────┐
   │   3. DECISION MAKER    │  ← YES/NO decision
   └───────────┬────────────┘
               │
       ┌───────┴───────┐
       │               │
      YES              NO
       │               │
       ↓               │
   ┌────────────┐      │
   │ 4. REFINER │      │    ← Fixes code (conditional)
   └─────┬──────┘      │
         │             │
         └──────┬──────┘
                ↓
   ┌────────────────────────┐
   │    5. CLI TESTER       │  ← Tests in sandbox
   └───────────┬────────────┘
               ↓
   ┌────────────────────────┐
   │  6. DOC WRITER         │  ← Generates README
   └───────────┬────────────┘
               ↓
         FINAL OUTPUT
```

**Key Point:** If the Decision Maker says "NO" (code is good), we SKIP the Refiner step! This is the power of **conditional routing** in LangGraph.

---

## 🔄 About the LangGraph Migration (IMPORTANT!)

### Original Plan: CrewAI
We initially used **CrewAI** - a framework for building AI agent teams.

### What We Changed To: LangGraph
We migrated to **LangGraph** - a more powerful framework from LangChain.

### Why Did We Change?

| Feature | CrewAI (Old) | LangGraph (New) |
|---------|--------------|-----------------|
| **Control** | High-level, less control | Low-level, fine-grained control |
| **Conditional Logic** | Limited | ✅ Full support (skip agents) |
| **State Management** | Implicit | ✅ Explicit TypedDict |
| **Debugging** | Harder | ✅ Easier (clear state at each step) |
| **Visualization** | Basic | ✅ Graph-based |
| **Flexibility** | Less | ✅ More (add/remove agents easily) |

### What is LangGraph?

**LangGraph** is a library for building **stateful, multi-actor applications** with LLMs. Think of it as:

- **Graph** = Nodes (agents) + Edges (connections)
- **State** = Shared data that flows through the graph
- **Conditional Edges** = Decision points that route to different nodes

### Key LangGraph Concepts in Our Project:

1. **StateGraph**: The main workflow container
   ```python
   workflow = StateGraph(AgentState)
   ```

2. **Nodes**: Each agent is a node (function)
   ```python
   workflow.add_node("generate", code_generator_node)
   workflow.add_node("review", code_reviewer_node)
   ```

3. **Edges**: Connections between agents
   ```python
   workflow.add_edge("generate", "review")  # After generate, go to review
   ```

4. **Conditional Edges**: Decision-based routing
   ```python
   workflow.add_conditional_edges(
       "decide",
       should_refine,  # Function that returns "refine" or "document"
       {"refine": "refine", "document": "test"}
   )
   ```

5. **State**: Shared TypedDict that flows through all nodes
   ```python
   class AgentState(TypedDict):
       requirements: str
       generated_code: str
       review_report: str
       decision: str  # "YES" or "NO"
       refined_code: str
       documentation: str
   ```

---

## 📁 Key Files Explained

### Backend Files:

| File | Purpose |
|------|---------|
| `app.py` | FastAPI server, handles HTTP requests, SSE streaming |
| `main.py` | Creates LangGraph workflow, orchestrates agents |
| `agents/state.py` | Defines AgentState TypedDict (shared state) |
| `agents/nodes.py` | All 6 agent functions + conditional edge logic |
| `tools/executor.py` | Sandboxed Python code execution |

### Frontend Files:

| File | Purpose |
|------|---------|
| `page.tsx` | Home page with prompt input |
| `workspace/page.tsx` | Main workspace with all panels |
| `components/workspace/AgentPanel.tsx` | Shows 6 agent status cards |
| `components/workspace/CodeWorkspace.tsx` | Monaco code editor |

---

## 🔧 Technology Stack Summary

### Backend:
- **Python 3.11+** - Programming language
- **FastAPI** - Web framework (like Express for Python)
- **LangGraph** - Agent orchestration framework
- **LangChain** - LLM application framework
- **Ollama** - Local LLM runtime (like having ChatGPT on your computer)
- **Mistral 7B** - The actual AI model (7 billion parameters)
- **Groq** - Cloud LLM for faster responses (optional)

### Frontend:
- **Next.js 16** - React framework with server components
- **React 19** - UI library
- **TypeScript** - Type-safe JavaScript
- **TailwindCSS 4** - Utility-first CSS
- **Monaco Editor** - VS Code's editor component
- **Radix UI** - Accessible UI components

---

## 🔐 Security Features

### Sandboxed Execution:
The code tester runs in a **sandbox** - a safe, isolated environment:

**Blocked operations:**
- ❌ `open()` - No file access
- ❌ `input()` - No user input
- ❌ `os.system()` - No system commands
- ❌ `subprocess` - No process spawning
- ❌ Network modules - No internet access
- ❌ `shutil` - No file operations

**Why?** If the AI generates malicious code, it can't harm your computer!

---

## 🌊 Real-Time Streaming (SSE)

### What is SSE?
**Server-Sent Events** - A way for the server to push updates to the browser.

### How it works:
```
Backend                    Frontend
   │                          │
   ├──────"agent_start"──────►│  Agent started
   ├──────"log"──────────────►│  Progress update
   ├──────"code_output"──────►│  Generated code
   ├──────"agent_end"────────►│  Agent finished
   ├──────"task_completed"───►│  All done!
   │                          │
```

### Why SSE instead of WebSocket?
- Simpler to implement
- One-way communication is enough
- Built-in browser support
- No need for bidirectional messages

---

## 💡 Key Concepts to Remember

### 1. Multi-Agent System
- Multiple AI "personalities" with different expertise
- Each focuses on one task
- Collaborate like a software team

### 2. State Management
- All agents share the same state object
- State flows through the graph
- Each agent reads from and writes to state

### 3. Conditional Routing
- Not all paths are always taken
- Decision agent determines the route
- Saves time and resources

### 4. Local LLM (Privacy)
- No data leaves your computer
- Ollama runs Mistral 7B locally
- Alternative to ChatGPT API

### 5. Hybrid LLM
- Can switch between local (Ollama) and cloud (Groq)
- Local = Free, Private, Slower
- Cloud = Fast, Free tier, Better quality

---

## 🎯 Common Viva Questions & Answers

### Q1: What is the main objective of your project?
> To create an autonomous AI system that can generate, review, fix, test, and document code based on natural language requirements, simulating a complete software development team.

### Q2: Why did you use LangGraph instead of CrewAI?
> LangGraph provides better control over the workflow, explicit state management, and most importantly, **conditional routing** - the ability to skip agents when their work isn't needed.

### Q3: How do the agents communicate?
> Through a **shared state object** (AgentState TypedDict). Each agent reads from the state, does its work, and writes back to the state. This state flows through the graph from one agent to the next.

### Q4: What is the role of the Decision Maker agent?
> It acts as a **router** that decides whether the code needs refinement. If it says "NO", we skip the Refiner agent and go directly to testing, saving time and resources.

### Q5: How do you ensure the generated code is safe to run?
> We use a **sandboxed execution environment** that blocks dangerous operations like file I/O, network access, and system commands. The code runs in an isolated subprocess with a timeout.

### Q6: What is SSE and why did you use it?
> **Server-Sent Events** is a technology for real-time server-to-client communication. We use it to stream agent status updates, logs, and results to the frontend as they happen.

### Q7: What LLM models does your system support?
> We support two options:
> 1. **Ollama (Local)** - Mistral 7B, free and private
> 2. **Groq (Cloud)** - Llama 3.3 70B, faster but requires API key

### Q8: How does conditional routing work in LangGraph?
> We define a function (`should_refine`) that returns different route names based on the state. LangGraph uses this to decide which node to go to next. If decision is "NO", it returns "document" (skip refiner), otherwise "refine".

### Q9: What are the 6 agents and their roles?
> 1. **Code Generator** - Writes initial code
> 2. **Code Reviewer** - Checks for bugs/issues
> 3. **Decision Maker** - YES/NO for refinement
> 4. **Code Refiner** - Fixes issues
> 5. **CLI Tester** - Tests code in sandbox
> 6. **Doc Writer** - Creates documentation

### Q10: Explain the AgentState TypedDict.
> It's a Python dictionary with type hints that holds all the shared data:
> - `requirements` - User's input
> - `generated_code` - From Code Generator
> - `review_report` - From Reviewer
> - `decision` - "YES" or "NO"
> - `refined_code` - From Refiner
> - `test_results` - From Tester
> - `documentation` - From Doc Writer

---

## 📊 Project Statistics

| Metric | Value |
|--------|-------|
| **Total Agents** | 6 |
| **Backend Language** | Python 3.11+ |
| **Frontend Framework** | Next.js 16 |
| **AI Framework** | LangGraph (migrated from CrewAI) |
| **Local LLM** | Ollama + Mistral 7B |
| **Cloud LLM** | Groq + Llama 3.3 70B |
| **Real-time Updates** | Server-Sent Events (SSE) |
| **Code Safety** | Sandboxed Execution |
| **Version** | 4.0.0 (Full Stack Edition) |

---

## 🚀 How to Demo the Project

1. **Start Ollama**: `ollama serve`
2. **Start Backend**: `uvicorn app:app --reload --port 8000`
3. **Start Frontend**: `cd frontend/software-agent && npm run dev`
4. **Open Browser**: http://localhost:3000
5. **Enter Prompt**: "Create a function to calculate factorial"
6. **Watch Agents Work**: See real-time updates!

---

## 📝 Key Takeaways for Viva

1. **Multi-Agent Systems** are like virtual software teams
2. **LangGraph** provides state-based workflow orchestration
3. **Conditional Routing** saves resources by skipping unnecessary steps
4. **SSE** enables real-time updates from server to client
5. **Sandboxing** protects against malicious code execution
6. **Hybrid LLM** offers flexibility between local privacy and cloud speed
7. **TypedDict State** ensures type-safe data flow between agents

---

**Good luck with your viva! 🎓✨**

---

*Last Updated: January 29, 2026*
*Project Version: 4.0.0 (Full Stack Edition)*
