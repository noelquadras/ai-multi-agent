## 🚀 **Version 4.0.0 - Full Stack Edition**

This project has been enhanced with **authentication, Convex data layer, hybrid LLM support, and CLI testing**!

### **What's New in v4.0.0:**
- ✅ **NextAuth** - GitHub, Google, and demo login support
- ✅ **Convex** - Real-time data layer for projects, tasks, files, and memory
- ✅ **Hybrid LLM** - Choose between local Ollama or cloud Groq (70B)
- ✅ **CLI Testing** - Automated sandboxed code testing with live output
- ✅ **Human-in-the-loop** - Pause/Resume and Approve/Reject controls
- ✅ **6 AI Agents** - Added Tester agent for automated testing
- ✅ **Improved UI** - Model selector, CLI panel, better streaming

---

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

* [Node.js](https://nodejs.org/) (v18.x or higher)
* [Python](https://www.python.org/) (v3.11+)
* [Ollama](https://ollama.ai/) - Local LLM runtime
* [Package Manager](https://www.npmjs.com/): npm, yarn, pnpm, or bun

**Optional:**
* [Convex](https://convex.dev/) account - For data persistence
* [Groq](https://console.groq.com/) API key - For cloud LLM

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

# Install dependencies
pip install -r requirements.txt

# Install optional Groq support
pip install langchain-groq
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

### 5. Environment Configuration

Create environment files:

**Backend (.env in root):**
```env
# Groq API (optional - for cloud LLM)
GROQ_API_KEY=your_groq_api_key

# Convex (optional - for data persistence)
CONVEX_SITE_URL=https://your-project.convex.cloud
CONVEX_DEPLOY_KEY=your_deploy_key
```

**Frontend (.env.local in frontend/software-agent):**
```env
# NextAuth
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your_secret_key_here

# OAuth Providers (optional)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Convex (optional)
NEXT_PUBLIC_CONVEX_URL=https://your-project.convex.cloud
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

The system uses **LangGraph** to orchestrate 6 specialized AI agents:

1. **Code Generator** - Generates initial code from requirements
2. **Code Reviewer** - Reviews code for bugs, security, and quality
3. **Decision Maker** - Decides if refinement is needed (YES/NO)
4. **Code Refiner** - Fixes issues and improves code (conditional)
5. **CLI Tester** - Runs code in sandbox and captures output (new!)
6. **Documentation Writer** - Generates professional documentation

### **Workflow:**

```
User Input → Generate → Review → Decide
                                    ↓
                        YES → Refine → Test → Document
                         NO → Test → Document (skip refine)
```

**Key Features**:
- If the code is already good, the refiner is **skipped** automatically!
- All code is tested in a **sandboxed CLI** environment
- Choose between **local** (Ollama) or **cloud** (Groq) LLMs

---

## 🔐 Authentication

The app supports multiple authentication methods:

1. **Demo Account** - Use `demo@example.com` / `demo123` for testing
2. **GitHub OAuth** - Configure GitHub OAuth app
3. **Google OAuth** - Configure Google Cloud Console

To use without authentication, the app will work but won't persist data.

---

## ☁️ Hybrid LLM Support

Choose the best model for your needs:

| Model | Provider | Speed | Cost | Best For |
|-------|----------|-------|------|----------|
| Mistral 7B | Ollama (Local) | Medium | Free | Privacy, offline use |
| Llama 3.3 70B | Groq (Cloud) | Fast | Free tier | Better code quality |

Select your model on the home page before starting the AI crew!

---

## 📂 Project Structure

```text
.
├── app.py                      # FastAPI backend + SSE streaming
├── main.py                     # LangGraph workflow orchestration
├── requirements.txt            # Python dependencies
├── .env                        # Backend environment variables
│
├── agents/
│   ├── state.py                # LangGraph state schema (TypedDict)
│   └── nodes.py                # 6 agent node implementations
│
├── tools/
│   └── executor.py             # Sandboxed Python code executor
│
└── frontend/
    └── software-agent/
        ├── src/
        │   ├── app/
        │   │   ├── api/auth/       # NextAuth API routes
        │   │   ├── auth/signin/    # Sign-in page
        │   │   ├── page.tsx        # Home page (prompt + model)
        │   │   └── workspace/      # Main workspace
        │   ├── components/
        │   │   ├── auth/           # Auth components
        │   │   ├── providers/      # Session + Convex providers
        │   │   ├── ui/             # Reusable UI components
        │   │   └── workspace/      # Workspace panels
        │   └── lib/
        │       └── auth.ts         # NextAuth configuration
        ├── convex/                 # Convex schema + functions
        │   ├── schema.ts           # Database schema
        │   ├── users.ts            # User management
        │   ├── projects.ts         # Project CRUD
        │   ├── tasks.ts            # Task management
        │   ├── events.ts           # Event logging
        │   ├── files.ts            # File storage
        │   └── memory.ts           # Agent memory
        └── .env.local              # Frontend environment variables
```

---

## 🔧 Technology Stack

### **Backend:**
- **LangGraph** - State-based agent workflow orchestration
- **LangChain** - LLM application framework
- **FastAPI** - Modern async web framework
- **Ollama** - Local LLM runtime (Mistral 7B)
- **Groq** - Cloud LLM API (Llama 3.3 70B)
- **Pydantic** - Data validation

### **Frontend:**
- **Next.js 16** - React framework
- **React 19** - UI library
- **TypeScript** - Type safety
- **TailwindCSS 4** - Styling
- **NextAuth v5** - Authentication
- **Convex** - Real-time database

---

## 🎯 Features

- ✅ **6 Specialized AI Agents** working collaboratively
- ✅ **Real-time Event Streaming** (SSE) for live updates
- ✅ **Conditional Workflow** - Skip unnecessary steps
- ✅ **CLI Testing** - Sandboxed code execution with output
- ✅ **Hybrid LLM** - Local or cloud models
- ✅ **Authentication** - GitHub, Google, demo login
- ✅ **Human-in-the-loop** - Pause, resume, approve, reject
- ✅ **Data Persistence** - Convex real-time database
- ✅ **File Management** - Store generated code files
- ✅ **Modern UI** - Dark theme with Monaco editor

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/run-crew` | Start AI workflow |
| GET | `/api/task/{id}/events` | SSE event stream |
| GET | `/api/task/{id}` | Task status |
| POST | `/api/task/{id}/pause` | Pause task |
| POST | `/api/task/{id}/resume` | Resume task |
| POST | `/api/task/{id}/approve` | Approve code |
| POST | `/api/task/{id}/reject` | Reject code |
| GET | `/api/models` | Available LLMs |

---

## 🐛 Troubleshooting

### **CUDA Error with Ollama**

If you get CUDA errors:

```bash
# Stop Ollama
taskkill /F /IM ollama.exe  # Windows
pkill ollama               # Mac/Linux

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

### **NextAuth Error**

Make sure `NEXTAUTH_SECRET` is set in `.env.local`:
```bash
# Generate a secret
openssl rand -base64 32
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
- Full-stack enhancements for v4.0.0

---

**Version**: 4.0.0 (Full Stack Edition)  
**Last Updated**: January 25, 2026
