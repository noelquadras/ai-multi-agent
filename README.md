## 🚀 **Version 3.0.0 - LangGraph Edition**

This project has been **migrated from CrewAI to LangGraph** for better workflow control, conditional logic, and explicit state management!

### **What's New:**
- ✅ **LangGraph** state-based workflow orchestration
- ✅ **Conditional routing** - Skip refinement if code is already good
- ✅ **Explicit state management** with TypedDict
- ✅ **Better debugging** - Inspect state at each node
- ✅ **More flexible** - Easy to modify agent workflow

---

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

* [Node.js](https://nodejs.org/) (v18.x or higher)
* [Python](https://www.python.org/) (v3.11+)
* [Ollama](https://ollama.ai/) - Local LLM runtime
* [Package Manager](https://www.npmjs.com/): npm, yarn, pnpm, or bun

---

## 📦 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/noelquadras/ai-multi-agent.git
cd ai-multi-agent

```

### 2. Backend Setup

It is recommended to use a virtual environment.

```bash
# Navigate to root
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (includes LangGraph, LangChain, etc.)
pip install -r requirements.txt

```

### 3. Ollama Setup

Install and configure Ollama for local LLM:

```bash
# Download and install Ollama from https://ollama.ai/

# Pull the Mistral model (required)
ollama pull mistral:7b-instruct

# Start Ollama (it should auto-start, but if not)
ollama serve

```

### 4. Frontend Setup

```bash
cd frontend/software-agent
npm install

```

---

## 🏃 Usage

You will need **three terminal windows** to run the full stack simultaneously.

### Terminal 1: Start Ollama

```bash
ollama serve

```

> Ollama will be available at: `http://localhost:11434`

### Terminal 2: Start Backend

From the **root** folder:

```bash
# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start FastAPI server
uvicorn app:app --reload --port 8000

```

> The API will be available at: `http://localhost:8000`

### Terminal 3: Start Frontend

From `frontend/software-agent`:

```bash
npm run dev

```

> The application will be available at: `http://localhost:3000`

---

## 🤖 How It Works

The system uses **LangGraph** to orchestrate 5 specialized AI agents:

1. **Code Generator** - Generates initial code from requirements
2. **Code Reviewer** - Reviews code for bugs, security, and quality
3. **Decision Maker** - Decides if refinement is needed (YES/NO)
4. **Code Refiner** - Fixes issues and improves code (conditional)
5. **Documentation Writer** - Generates professional documentation

### **Workflow:**

```
User Input → Generate → Review → Decide
                                    ↓
                        YES → Refine → Document
                         NO → Document (skip refine)
```

**Key Feature**: If the code is already good, the refiner is **skipped** automatically!

---

## 📂 Project Structure

```text
.
├── app.py                      # FastAPI backend + SSE streaming
├── main.py                     # LangGraph workflow orchestration
├── requirements.txt            # Python dependencies
├── venv/                       # Virtual environment (ignored by git)
│
├── agents/
│   ├── state.py                # LangGraph state schema (TypedDict)
│   ├── nodes.py                # 5 agent node implementations
│   └── config.py               # [DEPRECATED] Old CrewAI config
│
├── tasks/
│   └── tasks.py                # [DEPRECATED] Old CrewAI tasks
│
├── tools/
│   ├── executor.py             # Sandboxed Python code executor
│   └── ...
│
└── frontend/
    └── software-agent/         # Next.js/React application
        ├── src/
        │   ├── app/
        │   │   ├── page.tsx            # Home page (prompt input)
        │   │   └── workspace/
        │   │       └── page.tsx        # Workspace (main UI)
        │   └── components/
        │       ├── ui/                 # Reusable UI components
        │       └── workspace/          # Agent panels, code editor
        ├── public/
        └── package.json

```

---

## 🔧 Technology Stack

### **Backend:**
- **LangGraph** - State-based agent workflow orchestration
- **LangChain** - LLM application framework
- **FastAPI** - Modern async web framework
- **Ollama** - Local LLM runtime (Mistral 7B)
- **Pydantic** - Data validation

### **Frontend:**
- **Next.js 16** - React framework
- **React 19** - UI library
- **TypeScript** - Type safety
- **TailwindCSS 4** - Styling
- **Monaco Editor** - Code editor (VS Code)

---

## 📚 Documentation

- **[Complete Overview](present_overview.md)** - Detailed project documentation
- **[Migration Plan](LANGGRAPH_MIGRATION_PLAN.md)** - CrewAI to LangGraph migration
- **[Migration Complete](MIGRATION_COMPLETE.md)** - Migration summary

---

## 🎯 Features

- ✅ **5 Specialized AI Agents** working collaboratively
- ✅ **Real-time Event Streaming** (SSE) for live updates
- ✅ **Conditional Workflow** - Skip unnecessary steps
- ✅ **Sandboxed Code Execution** - Safe Python execution
- ✅ **Local LLM** - Privacy-first (no external API calls)
- ✅ **Modern UI** - Dark theme with Monaco editor
- ✅ **State Management** - Explicit state tracking

---

## 🐛 Troubleshooting

### **CUDA Error with Ollama**

If you get CUDA errors:

```bash
# Stop Ollama
taskkill /F /IM ollama.exe

# Restart Ollama
ollama serve
```

### **Backend Won't Start**

Check that:
- Virtual environment is activated
- All dependencies are installed: `pip install -r requirements.txt`
- Ollama is running: `ollama list`

### **Frontend Issues**

```bash
cd frontend/software-agent
rm -rf node_modules package-lock.json
npm install
npm run dev
```

---

## 🤝 Contributing

This is a forked project. Feel free to:
- Create issues for bugs
- Submit pull requests for improvements
- Fork and modify for your own use

---

## 📄 License

[Add your license here]

---

## 🙏 Credits

- Original project by [noelquadras](https://github.com/noelquadras)
- LangGraph migration by [rakeshacharyaaa](https://github.com/rakeshacharyaaa)

---

**Version**: 3.0.0 (LangGraph Edition)  
**Last Updated**: January 24, 2026
