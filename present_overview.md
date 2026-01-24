# 🤖 AI Multi-Agent Software Development System - Complete Overview

## 📋 Project Summary

This is an **autonomous AI-powered software development system** that uses **multiple specialized AI agents** working collaboratively to generate, review, refine, and document code based on natural language requirements. The system leverages **local LLMs** (Ollama with Mistral 7B) and provides a real-time web interface to monitor the agents' work.

---

## 🏗️ Architecture Overview

### **System Components**

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACE (Frontend)                 │
│              Next.js 16 + React 19 + TypeScript              │
│                   http://localhost:3000                      │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/SSE
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND API (FastAPI)                       │
│              Python 3.11 + FastAPI + Uvicorn                 │
│                   http://localhost:8000                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              AI ORCHESTRATION (LangGraph)                    │
│    5 Agent Nodes + State Graph + Conditional Routing        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              LOCAL LLM (Ollama)                              │
│          Mistral 7B Instruct Model (4.4 GB)                  │
│                http://localhost:11434                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Core Technologies Stack

### **Backend Stack**
| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.11+ | Core language |
| **FastAPI** | Latest | REST API & SSE streaming |
| **Uvicorn** | Latest | ASGI server |
| **LangGraph** | Latest | Multi-agent workflow orchestration |
| **LangChain** | Latest | LLM framework |
| **LiteLLM** | Latest | LLM provider abstraction |
| **Pydantic** | Latest | Data validation |
| **LangChain-Ollama** | Latest | Ollama integration |

### **Frontend Stack**
| Technology | Version | Purpose |
|------------|---------|---------|
| **Next.js** | 16.1.0 | React framework |
| **React** | 19.2.3 | UI library |
| **TypeScript** | 5.x | Type safety |
| **TailwindCSS** | 4.x | Styling |
| **Monaco Editor** | 4.7.0 | Code editor component |
| **Radix UI** | Latest | Accessible UI components |
| **Lucide React** | Latest | Icon library |

### **AI/LLM Stack**
| Technology | Purpose |
|------------|---------|
| **Ollama** | Local LLM runtime |
| **Mistral 7B Instruct** | Language model for code generation |
| **LangGraph** | Agent workflow orchestration with state management |
| **LangChain** | LLM application framework |

---

## 🤖 The Five AI Agents

### **1. Code Generator (Senior Developer)**
- **Role**: Senior Software Developer
- **Goal**: Generate high-quality, clean, modular code
- **Responsibilities**:
  - Interpret user requirements
  - Write syntactically correct, runnable code
  - Follow best practices for code structure
  - Output code in markdown code blocks
- **Max Iterations**: 3

### **2. Code Reviewer (QA Engineer)**
- **Role**: Expert QA and Security Auditor
- **Goal**: Critically review code for bugs, security, style
- **Responsibilities**:
  - Analyze generated code
  - Identify security vulnerabilities
  - Check for bugs and logic errors
  - Suggest improvements for maintainability
  - Output structured review report
- **Max Iterations**: 3

### **3. Decision Maker (System Auditor)**
- **Role**: System Decision Auditor
- **Goal**: Determine if code needs refinement
- **Responsibilities**:
  - Analyze code quality
  - Make binary decision (YES/NO)
  - Trigger refinement process if needed
- **Max Iterations**: 3
- **Delegation**: Disabled

### **4. Code Refiner (Junior Developer)**
- **Role**: Junior Developer specializing in Refactoring
- **Goal**: Fix code based on review feedback
- **Responsibilities**:
  - Apply all review suggestions
  - Execute code using Python sandbox tool
  - Fix errors iteratively
  - Ensure code runs successfully
- **Max Iterations**: 5
- **Tools**: Python Executor (Sandboxed)

### **5. Documentation Writer (Technical Writer)**
- **Role**: Senior Technical Writer
- **Goal**: Generate professional documentation
- **Responsibilities**:
  - Write comprehensive README
  - Document features and usage
  - Explain implementation details
  - List requirements and dependencies
  - Note limitations and future improvements
- **Max Iterations**: Default

---

## 🔄 Workflow Process

```
┌──────────────────────────────────────────────────────────────┐
│  1. USER SUBMITS PROMPT                                      │
│     "Create a login form with validation"                    │
└────────────────────┬─────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  2. CODE GENERATOR AGENT                                     │
│     • Analyzes requirements                                  │
│     • Generates initial code                                 │
│     • Outputs: Complete code solution                        │
└────────────────────┬─────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  3. CODE REVIEWER AGENT (Parallel with Decision)             │
│     • Reviews code quality                                   │
│     • Identifies bugs and security issues                    │
│     • Outputs: Structured review report                      │
└────────────────────┬─────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  4. DECISION MAKER AGENT (Parallel with Reviewer)            │
│     • Analyzes code                                          │
│     • Decides: YES (needs refinement) or NO                  │
│     • Outputs: YES/NO decision                               │
└────────────────────┬─────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  5. CODE REFINER AGENT                                       │
│     • Applies review suggestions                             │
│     • Executes code in sandbox                               │
│     • Fixes errors iteratively                               │
│     • Outputs: Final corrected code                          │
└────────────────────┬─────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  6. DOCUMENTATION WRITER AGENT                               │
│     • Generates professional docs                            │
│     • Includes usage examples                                │
│     • Outputs: Complete README                               │
└────────────────────┬─────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────────────────┐
│  7. RESULTS DISPLAYED IN UI                                  │
│     • Final code in Monaco editor                            │
│     • Activity log with all events                           │
│     • Agent status indicators                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
ai-multi-agent/
│
├── 📂 Backend (Python)
│   ├── app.py                      # FastAPI server + SSE streaming
│   ├── main.py                     # LangGraph workflow orchestration
│   ├── requirements.txt            # Python dependencies
│   │
│   ├── 📂 agents/
│   │   ├── __init__.py
│   │   ├── state.py                # LangGraph state schema
│   │   ├── nodes.py                # Agent node implementations
│   │   └── config.py               # [DEPRECATED] Old CrewAI config
│   │
│   ├── 📂 tasks/
│   │   └── tasks.py                # [DEPRECATED] Old CrewAI tasks
│   │
│   └── 📂 tools/
│       ├── executor.py             # Sandboxed Python code executor
│       ├── docker_runner.py        # Docker-based execution (optional)
│       └── sandbox_subprocess.py   # Subprocess sandbox utilities
│
├── 📂 Frontend (Next.js)
│   └── 📂 software-agent/
│       ├── package.json            # Node dependencies
│       ├── next.config.ts          # Next.js configuration
│       ├── tsconfig.json           # TypeScript config
│       │
│       ├── 📂 src/
│       │   ├── 📂 app/
│       │   │   ├── layout.tsx      # Root layout
│       │   │   ├── page.tsx        # Home page (prompt input)
│       │   │   ├── globals.css     # Global styles
│       │   │   │
│       │   │   ├── 📂 context/
│       │   │   │   ├── ExecutionContext.tsx  # Global state management
│       │   │   │   └── PromptContext.tsx     # Prompt state
│       │   │   │
│       │   │   └── 📂 workspace/
│       │   │       └── page.tsx    # Workspace view (main UI)
│       │   │
│       │   └── 📂 components/
│       │       ├── 📂 ui/          # Reusable UI components
│       │       │   ├── button.tsx
│       │       │   ├── card.tsx
│       │       │   ├── badge.tsx
│       │       │   ├── textarea.tsx
│       │       │   ├── progress.tsx
│       │       │   └── ...
│       │       │
│       │       └── 📂 workspace/   # Workspace-specific components
│       │           ├── AgentPanel.tsx      # Agent status sidebar
│       │           ├── ActivityPanel.tsx   # Event log
│       │           ├── CodeWorkspace.tsx   # Monaco code editor
│       │           ├── PreviewPanel.tsx    # Preview/output panel
│       │           └── AgentCard.tsx       # Individual agent card
│       │
│       └── 📂 public/              # Static assets
│
├── 📂 venv/                        # Python virtual environment
├── README.md                       # Project documentation
└── present_overview.md             # This file
```

---

## 🔌 API Endpoints

### **Backend API (FastAPI)**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/run-crew` | Start new agent crew task |
| `GET` | `/api/task/{task_id}/events` | SSE stream of task events |
| `GET` | `/api/task/{task_id}` | Get task snapshot |

### **Request/Response Examples**

**Start Crew:**
```json
POST /api/run-crew
{
  "prompt": "Create a login form with validation"
}

Response:
{
  "task_id": "crew_20260124_183043"
}
```

**Event Stream (SSE):**
```
GET /api/task/crew_20260124_183043/events

data: {"type": "agent_start", "agent": "coder", "timestamp": "..."}
data: {"type": "log", "message": "Generating code...", "timestamp": "..."}
data: {"type": "code_output", "agent": "refiner", "code": "...", "timestamp": "..."}
data: {"type": "agent_end", "agent": "coder", "timestamp": "..."}
```

---

## 🛠️ Key Features

### **1. Real-Time Event Streaming (SSE)**
- Server-Sent Events for live updates
- Frontend receives agent status changes instantly
- Activity log updates in real-time

### **2. Sandboxed Code Execution**
- Safe Python code execution in isolated subprocess
- Blocked dangerous operations (file I/O, network, subprocess)
- Timeout protection (4 seconds default)
- Resource limits (CPU, memory)

### **3. Multi-Agent Collaboration**
- Sequential task processing
- Context sharing between agents
- Parallel execution where possible (reviewer + decision maker)

### **4. Modern UI/UX**
- Dark theme optimized for coding
- Monaco Editor integration (VS Code editor)
- Real-time agent status indicators
- Activity log with event filtering
- Responsive design

### **5. Local LLM (Privacy-First)**
- No data sent to external APIs
- Runs entirely on local machine
- Uses Ollama for model management
- Supports multiple models (Mistral, Llama, etc.)

---

## 🔐 Security Features

### **Sandboxed Execution**
- Disabled `open()`, `input()`, `os.system()`, `subprocess`
- Import whitelist (only safe modules: math, random, statistics)
- Resource limits (CPU time, memory)
- Timeout enforcement

### **API Security**
- CORS configured for localhost:3000 only
- No authentication (local development)
- Input validation via Pydantic

---

## 🚀 How to Run

### **Prerequisites**
- Python 3.11+
- Node.js 18+
- Ollama installed
- Mistral 7B model downloaded

### **Backend Setup**
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Start backend
uvicorn app:app --reload --port 8000
```

### **Frontend Setup**
```bash
# Navigate to frontend
cd frontend/software-agent

# Install dependencies
npm install

# Start frontend
npm run dev
```

### **Ollama Setup**
```bash
# Pull model
ollama pull mistral:7b-instruct

# Start Ollama (if not running)
ollama serve
```

### **Access Application**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Ollama: http://localhost:11434

---

## 📊 Data Flow

```
User Input (Frontend)
    ↓
POST /api/run-crew (Backend)
    ↓
Create Task ID + Start Background Thread
    ↓
run_software_crew() in main.py
    ↓
LangGraph StateGraph Executes Agent Nodes:
  - Each node is a function
  - State flows between nodes
  - Conditional edges for routing
    ↓
Each Agent Node:
  1. Receives AgentState
  2. Calls Ollama LLM (Mistral 7B)
  3. Updates state
  4. Emits events
  5. Returns updated state
    ↓
Events → emit_event() → task_events storage
    ↓
SSE Stream → Frontend EventSource
    ↓
Frontend Updates:
  - Agent status cards
  - Activity log
  - Code editor
  - Preview panel
```

---

## 🎨 UI Components

### **Home Page (`page.tsx`)**
- Prompt input textarea
- API status indicator
- "Build with AI Team" button
- Redirects to workspace on submit

### **Workspace Page (`workspace/page.tsx`)**
- **Agent Panel**: Shows 5 agents with status (idle/thinking/approved/error)
- **Code Workspace**: Monaco editor displaying generated code
- **Preview Panel**: Output preview (right side)
- **Activity Panel**: Real-time event log (bottom)

### **Component Hierarchy**
```
WorkspacePage
├── AgentPanel
│   └── AgentCard × 5
├── CodeWorkspace (Monaco Editor)
├── PreviewPanel
└── ActivityPanel
    └── Event List
```

---

## 🧪 Testing Example

**User Input:**
```
"Create a login form with username, password, and submit button"
```

**Agent Workflow:**
1. **Coder**: Generates HTML form with inputs
2. **Reviewer**: Checks for CSRF protection, validation
3. **Decision**: Decides if refinement needed (YES/NO)
4. **Refiner**: Adds security headers, validation logic
5. **Doc Writer**: Creates README with usage instructions

**Output:**
- Complete HTML login form
- Security features (CSP headers, CSRF tokens)
- Professional documentation

---

## 🔧 Configuration

### **LLM Configuration** (`agents/config.py`)
```python
ollama_llm = LLM(
    model="ollama/mistral:7b-instruct",
    base_url="http://localhost:11434"
)
```

### **Environment Variables** (`main.py`)
```python
os.environ["OPENAI_API_KEY"] = "na"
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_MODEL_NAME"] = "mistral:7b-instruct"
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"
```

---

## 📈 Performance Considerations

### **Response Times**
- Code Generation: 10-30 seconds (depends on complexity)
- Code Review: 5-15 seconds
- Decision Making: 2-5 seconds
- Refinement: 15-45 seconds (includes execution)
- Documentation: 10-20 seconds

**Total Time**: 1-3 minutes for complete workflow

### **Resource Usage**
- **Ollama (Mistral 7B)**: 4-6 GB RAM
- **Backend**: 200-500 MB RAM
- **Frontend**: 100-200 MB RAM

---

## 🐛 Known Limitations

1. **LLM Accuracy**: May generate incorrect code for complex tasks
2. **Sandbox Restrictions**: Limited to safe Python modules
3. **No Persistence**: Tasks not saved to database
4. **Single User**: No multi-user support
5. **Local Only**: Requires local Ollama installation

---

## 🚀 Future Improvements

1. **Database Integration**: Save tasks and results
2. **User Authentication**: Multi-user support
3. **More Languages**: Support for JavaScript, Java, etc.
4. **Advanced Sandbox**: Docker-based execution
5. **Model Selection**: Choose different LLMs
6. **Export Features**: Download code as files
7. **Version Control**: Git integration
8. **Collaborative Editing**: Real-time multi-user editing

---

## 📚 Key Libraries & Frameworks

### **Backend**
- **LangGraph**: State-based agent workflow orchestration
- **LangChain**: LLM application framework
- **FastAPI**: Modern async web framework
- **Pydantic**: Data validation
- **LiteLLM**: LLM provider abstraction
- **LangChain-Ollama**: Ollama integration

### **Frontend**
- **Next.js 16**: React framework with App Router
- **React 19**: Latest React with concurrent features
- **Monaco Editor**: VS Code editor component
- **Radix UI**: Accessible component primitives
- **TailwindCSS 4**: Utility-first CSS framework

---

## 🎯 Project Goals

1. ✅ **Autonomous Code Generation**: AI generates code without human intervention
2. ✅ **Quality Assurance**: Built-in review and refinement process
3. ✅ **Real-Time Feedback**: Live updates on agent progress
4. ✅ **Local Privacy**: No external API calls
5. ✅ **Modern UX**: Beautiful, intuitive interface

---

## 📝 Summary

This project demonstrates a **production-ready AI multi-agent system** for autonomous software development. It combines:

- **5 specialized AI agents** working collaboratively
- **Local LLM** (Mistral 7B via Ollama) for privacy
- **Real-time streaming** (SSE) for live updates
- **Modern web stack** (Next.js 16 + React 19)
- **Sandboxed execution** for safe code testing
- **Professional UI** with Monaco editor integration

The system can generate, review, refine, and document code based on natural language requirements, providing a glimpse into the future of AI-assisted software development.

---

**Last Updated**: January 24, 2026
**Status**: ✅ Fully Operational (Migrated to LangGraph)
**Version**: 3.0.0 (LangGraph Edition)
