# 🤖 AI Multi-Agent Software Crew

> A full-stack **AI software development team** powered by **LangGraph** and **Next.js** — where a ReAct supervisor orchestrates specialized agents to write, review, test, refine, and document code in real-time.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-blueviolet)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Key Features

- 🧠 **ReAct Supervisor** — An intelligent supervisor that classifies intent (quick task, long task, ambiguous) and dynamically orchestrates agents using a ReAct (Reasoning + Acting) loop with tool-based planning
- 🏗️ **8 Specialized Agents** — Spec Writer, Code Generator, Code Reviewer, Decision Maker, Code Refiner, CLI Tester, Terminal Analyzer, and Doc Writer
- 📡 **Real-Time Streaming** — Live SSE event streaming with agent-level status updates, streaming LLM output, and full event replay from SQLite persistence
- 🔄 **Test-Driven Refinement Loop** — If tests fail, the analyzer routes back to the refiner (with configurable iteration caps and termination guards)
- 🧑‍💻 **Human-in-the-Loop** — Pause/Resume, Cancel, Approve (skip refinement), Reject (force improvement with feedback), and Regenerate controls
- 🔀 **Hybrid LLM Support** — Switch between local **Ollama** and cloud **Groq** models; per-agent model overrides supported
- 🗄️ **Persistent Task History** — SQLite-backed task/event storage with soft-delete archival and full history browsing
- 🖥️ **Interactive PTY Terminal** — Shared terminal session (pywinpty) accessible from both the AI agents and the browser via WebSocket
- 📊 **Benchmark Harness** — HumanEval & MBPP-Plus evaluation with pass@k computation, parallel workers, and JSON result reports
- 🎨 **Modern UI** — Dark/light theme, shadcn/ui components, Monaco editor, chat panel, and hover-activated history sidebar
- 🔐 **Authentication** — NextAuth v5 with GitHub, Google OAuth, and demo credentials
- 📁 **Artifact System** — Each task persists specs, code, reviews, test outputs, and docs to disk (MetaGPT pattern)

---

## 🏛️ Architecture

### Supervisor-Driven Workflow (ReAct Pattern)

The system uses a **ReAct Supervisor** as the central orchestrator. Instead of a fixed pipeline, the supervisor dynamically decides which agent to invoke next based on the current state:

```
User Prompt
  → Supervisor (classify intent)
      ├── QUICK_TASK → Direct LLM response → END
      ├── AMBIGUOUS → Clarification → END
      └── LONG_TASK → ReAct Loop:
            → Spec Writer → Supervisor
            → Coder → Supervisor
            → Reviewer → Supervisor
            → Refiner (if needed) → Supervisor
            → Tester → Supervisor
            → Analyzer → Supervisor
                ├── PASS → Doc Writer → END
                ├── FIX_REQUIRED → Refiner (loop)
                └── REGENERATE → Coder (restart)
```

### Agent Descriptions

| Agent | Role | LLM Usage |
|-------|------|-----------|
| **Supervisor** | ReAct orchestrator — classifies intent, plans tasks, routes to agents | Structured output |
| **Spec Writer** | Generates technical specifications from requirements | Light (Ollama) |
| **Code Generator** | Writes initial Python code from requirements + spec | Heavy (Groq/Ollama) |
| **Code Reviewer** | Structured code review → verdict, score, issues, suggestions | Structured output |
| **Decision Maker** | Deterministic YES/NO from review verdict; LLM fallback | None / Light fallback |
| **Code Refiner** | Fixes code using review/analysis feedback + per-agent memory | Heavy (Groq/Ollama) |
| **CLI Tester** | Executes code in a sandboxed PTY environment | No LLM |
| **Terminal Analyzer** | Structured analysis → PASS / FIX_REQUIRED / REGENERATE | Heavy (Groq/Ollama) |
| **Doc Writer** | Generates professional markdown documentation | Light (Ollama) |

### Termination Guards

The system uses composable termination conditions to prevent runaway loops:
- **Iteration Limit** — Max 15 total node invocations
- **Token Budget** — 200,000 cumulative token cap
- **Debug Loop Cap** — Max 5 refine→test→analyze cycles

---

## 🛠️ Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| [Python](https://www.python.org/) | 3.11+ | Backend runtime |
| [Node.js](https://nodejs.org/) | 18+ | Frontend runtime |
| [Ollama](https://ollama.ai/) | Latest | Local LLM (recommended) |

**Optional:**
- [Groq](https://console.groq.com/) API key — for cloud LLM
- [Convex](https://convex.dev/) project — for the Files/Projects UI features

---

## 📦 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/noelquadras/ai-multi-agent.git
cd ai-multi-agent
```

### 2. Backend Setup (FastAPI)

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Ollama Setup (Local LLM)

```bash
# Pull the default model
ollama pull mistral:7b-instruct

# Ensure Ollama is running
ollama serve
```

### 4. Frontend Setup (Next.js)

```bash
cd frontend/software-agent
npm install
```

---

## ⚙️ Environment Variables

### Backend — `.env` (project root)

```env
# Groq API Key (optional — for cloud LLM)
# Get your FREE key at: https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key

# Convex (optional — for data persistence)
CONVEX_SITE_URL=https://your-project.convex.cloud
```

> **Note:** Model configuration is externalized to `models.json` — you can modify available models there.

### Frontend — `frontend/software-agent/.env.local`

```env
# NextAuth
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your_secret_key_here   # Generate: openssl rand -base64 32

# OAuth Providers (optional)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Convex (optional — for Files/Projects UI)
NEXT_PUBLIC_CONVEX_URL=https://your-project.convex.cloud
```

---

## 🏃 Running (Development)

You need **2–3 terminal windows** running simultaneously:

### Terminal 1 — Ollama (if using local models)

```bash
ollama serve
```
> Available at: `http://localhost:11434`

### Terminal 2 — Backend (FastAPI)

```bash
source venv/bin/activate        # Windows: venv\Scripts\activate
uvicorn app:app --reload --port 8000
```
> API available at: `http://localhost:8000`

### Terminal 3 — Frontend (Next.js)

```bash
cd frontend/software-agent
npm run dev
```
> App available at: `http://localhost:3000`

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check + DB connectivity |
| `POST` | `/api/run-crew` | Start a new workflow — `{ prompt, model?, agent_models? }` |
| `GET` | `/api/task/{id}` | Task snapshot: status, model, all stored events |
| `GET` | `/api/task/{id}/events` | SSE stream (replays stored events, then live) |
| `POST` | `/api/task/{id}/pause` | Pause a running task |
| `POST` | `/api/task/{id}/resume` | Resume a paused task |
| `POST` | `/api/task/{id}/cancel` | Cooperative cancellation (stops at next node boundary) |
| `POST` | `/api/task/{id}/approve` | Skip refinement (human override) |
| `POST` | `/api/task/{id}/reject` | Force refinement with optional feedback |
| `POST` | `/api/task/{id}/regenerate` | Create new task from original prompt + feedback |
| `DELETE` | `/api/task/{id}` | Soft-delete task (archives to deleted tables) |
| `GET` | `/api/task/{id}/artifacts` | List all artifacts for a task |
| `GET` | `/api/task/{id}/artifacts/{path}` | Download a specific artifact file |
| `GET` | `/api/history` | All tasks (most-recent first) |
| `GET` | `/api/models` | Available LLM options (dynamic Ollama + static Groq) |
| `POST` | `/api/terminal/run` | Run a command in the shared PTY terminal |
| `WS` | `/ws/terminal/{client_id}` | WebSocket PTY bridge (browser terminal) |

---

## 📂 Project Structure

```text
.
├── app.py                          # FastAPI API + SSE + WebSocket terminal + task controls
├── main.py                         # LangGraph graph construction + workflow runner
├── database.py                     # SQLite persistence for tasks/events + soft delete
├── terminal_service.py             # PTY session manager (pywinpty) for shared terminal
├── models.json                     # Externalized model configuration (ollama/groq)
├── requirements.txt                # Python dependencies
│
├── agents/
│   ├── state.py                    # AgentState TypedDict (event-sourced)
│   ├── react_supervisor.py         # ReAct supervisor node + router
│   ├── nodes.py                    # Node registry + model config
│   ├── spec_writer.py              # Technical specification generation
│   ├── code_generator.py           # Code generation agent
│   ├── code_reviewer.py            # Structured code review agent
│   ├── decision_maker.py           # YES/NO decision routing
│   ├── code_refiner.py             # Code refinement with memory
│   ├── cli_tester.py               # Sandboxed CLI test execution
│   ├── terminal_analyzer.py        # Test result analysis (PASS/FIX/REGEN)
│   ├── doc_writer.py               # Documentation generation
│   ├── classifier.py               # Task complexity classification
│   ├── schemas.py                  # Pydantic output schemas
│   ├── spec_schema.py              # Spec output schema
│   ├── termination.py              # Composable termination conditions
│   ├── cancellation.py             # Cooperative cancellation registry
│   ├── artifacts.py                # Task artifact persistence
│   ├── memory.py                   # Per-agent conversation memory
│   ├── llm_config.py               # LLM provider configuration
│   └── manager.py                  # Task management utilities
│
├── tools/
│   ├── executor.py                 # Python sandbox executor (PTY-backed)
│   ├── code_analysis.py            # Code analysis utilities
│   ├── file_ops.py                 # File operation tools
│   ├── shell.py                    # Shell command tools
│   ├── web_search.py               # Web search tool
│   ├── langchain_tools.py          # LangChain tool wrappers
│   └── tool_registry.py            # Tool registration system
│
├── scripts/
│   ├── benchmark_runner.py         # CLI benchmark entrypoint
│   └── harness/                    # Benchmark evaluation framework
│       ├── types.py                # EvalConfig, SampleResult, BenchmarkReport
│       ├── dataset.py              # Dataset download + JSONL loader
│       ├── sandbox.py              # Isolated subprocess sandbox
│       ├── evaluator.py            # pass@k computation
│       └── runner.py               # BenchmarkRunner orchestrator
│
├── data/
│   └── benchmarks/                 # HumanEval.jsonl.gz, MbppPlus.jsonl.gz, results
│
└── frontend/
    └── software-agent/             # Next.js 16 application
        ├── src/
        │   ├── app/
        │   │   ├── page.tsx            # Home — prompt input, model selector
        │   │   ├── workspace/page.tsx  # Live workspace — SSE, all panels
        │   │   ├── api/auth/           # NextAuth API routes
        │   │   └── context/            # React context providers
        │   ├── components/
        │   │   ├── workspace/
        │   │   │   ├── ChatPanel.tsx        # Main chat interface
        │   │   │   ├── CodeWorkspace.tsx    # Code display + Run Code
        │   │   │   ├── ActivityPanel.tsx    # Event log with filtering
        │   │   │   ├── CLIPanel.tsx         # CLI test output
        │   │   │   ├── AgentPanel.tsx       # Agent cards with status
        │   │   │   ├── AgentCard.tsx        # Individual agent status card
        │   │   │   ├── FilesPanel.tsx       # File browser (Convex)
        │   │   │   └── RejectModal.tsx      # Rejection feedback modal
        │   │   ├── HistorySidebar.tsx       # Task history (hover-activated)
        │   │   ├── ModelSelector.tsx        # LLM model selection
        │   │   ├── Terminal.tsx             # Interactive PTY terminal
        │   │   ├── providers/              # Theme, Auth, Convex providers
        │   │   └── ui/                     # shadcn/ui component library
        │   └── lib/
        │       └── auth.ts                 # NextAuth v5 configuration
        └── .env.local                      # Frontend environment variables
```

---

## 🔧 Technology Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **LangGraph** | State-based agent workflow orchestration with checkpointing |
| **LangChain** | LLM application framework + structured outputs |
| **FastAPI** | Async web framework with SSE and WebSocket support |
| **Ollama** | Local LLM runtime (Mistral 7B default) |
| **Groq** | Cloud LLM API (Llama 3.3 70B) |
| **SQLite** | Task/event persistence + checkpoint storage |
| **pywinpty** | PTY terminal sessions for Windows |
| **Pydantic** | Data validation + structured output schemas |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **Next.js 16** | React meta-framework |
| **React 19** | UI library |
| **TypeScript** | Type-safe development |
| **TailwindCSS 4** | Utility-first styling |
| **shadcn/ui** | Component library (cards, buttons, badges, etc.) |
| **NextAuth v5** | Authentication (GitHub, Google, demo) |
| **Convex** | Real-time database (optional, for Files UI) |
| **Monaco Editor** | Code editing/display |

---

## 🧪 Benchmark Harness

Run coding benchmarks against the agent pipeline:

```bash
# Download datasets
python scripts/benchmark_runner.py --dataset humaneval --download
python scripts/benchmark_runner.py --dataset mbpp --download

# Quick 5-task run
python scripts/benchmark_runner.py --dataset humaneval --tasks 5

# Full evaluation (3 samples, 4 parallel workers, greedy decoding)
python scripts/benchmark_runner.py \
  --dataset humaneval --tasks 164 --samples 3 --workers 4 \
  --model ollama --temperature 0 --seed 42
```

Results are saved to `data/benchmarks/results_{dataset}_{model}_{timestamp}.json`.

### Supported Datasets

| Dataset | Source | Tasks |
|---------|--------|-------|
| `humaneval` | OpenAI HumanEval | 164 |
| `mbpp` | EvalPlus MBPP-Plus | ~390 |

---

## 🔐 Authentication

The app supports multiple login methods:

| Method | Setup |
|--------|-------|
| **Demo Account** | Use `demo@example.com` / `demo123` — no setup needed |
| **GitHub OAuth** | Configure GitHub OAuth app → set `GITHUB_CLIENT_ID` / `SECRET` |
| **Google OAuth** | Configure Google Cloud Console → set `GOOGLE_CLIENT_ID` / `SECRET` |

---

## 🐛 Troubleshooting

### Backend Won't Start
- Ensure virtual environment is activated
- Verify all dependencies: `pip install -r requirements.txt`
- Check Ollama is running: `ollama list`

### Frontend Issues
```bash
cd frontend/software-agent
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### Groq Errors
- Verify `GROQ_API_KEY` is set in `.env`
- Ensure `langchain-groq` is installed (included in `requirements.txt`)

### Model Configuration
- Check `models.json` for available model options
- Dynamic Ollama models are fetched from `http://localhost:11434/api/tags`

### CUDA Error with Ollama
```bash
# Stop and restart Ollama
taskkill /F /IM ollama.exe  # Windows
pkill ollama               # Mac/Linux
ollama serve
```

### NextAuth Error
Ensure `NEXTAUTH_SECRET` is set in `.env.local`:
```bash
openssl rand -base64 32
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- 🐛 Create issues for bugs
- 🚀 Submit pull requests for improvements
- 🍴 Fork and modify for your own use

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

**Last Updated:** March 5, 2026
