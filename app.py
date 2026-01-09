# app.py - FastAPI Backend (FIXED)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import re
import sys
import threading
from datetime import datetime

# =========================
# AGENT TEMPLATES
# =========================
AGENT_TEMPLATES = {
    "planner": {"id": "planner", "name": "Planner", "role": "Architect"},
    "coder": {"id": "coder", "name": "Coder", "role": "Full Stack Dev"},
    "reviewer": {"id": "reviewer", "name": "Reviewer", "role": "Code Reviewer"},
    "refiner": {"id": "refiner", "name": "Refiner", "role": "Code Refiner"},
    "tester": {"id": "tester", "name": "Tester", "role": "QA Engineer"},
}

# =========================
# IMPORT CREW
# =========================
try:
    from main import run_software_crew
    CREW_AVAILABLE = True
except Exception as e:
    print(f"CREW IMPORT FAILED: {e}")
    CREW_AVAILABLE = False

# =========================
# FASTAPI APP
# =========================
app = FastAPI(
    title="AI Software Crew API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# MODELS
# =========================
class CrewRequest(BaseModel):
    prompt: str
    model: Optional[str] = "mistral:7b-instruct"
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 1200

class CrewResponse(BaseModel):
    success: bool
    task_id: str
    message: str
    timestamp: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    logs: List[str]
    agents: List[Dict[str, Any]]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# =========================
# STORAGE
# =========================
tasks: Dict[str, Dict[str, Any]] = {}
task_logs: Dict[str, List[str]] = {}

# =========================
# LOGGER (AGENT-AWARE)
# =========================
class QueueLogger:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.ansi = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")

    def write(self, message):
        if not message:
            return

        clean = self.ansi.sub("", str(message)).strip()
        if not clean:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        task_logs[self.task_id].append(f"[{ts}] {clean}")

        if clean.startswith("[AGENT_START"):
            agent_id = clean.replace("[AGENT_START", "").replace("]", "").strip()
            if agent_id in tasks[self.task_id]["agents"]:
                tasks[self.task_id]["agents"][agent_id]["status"] = "thinking"
                tasks[self.task_id]["agents"][agent_id]["message"] = "Working"

        if clean.startswith("[AGENT_END"):
            agent_id = clean.replace("[AGENT_END", "").replace("]", "").strip()
            if agent_id in tasks[self.task_id]["agents"]:
                tasks[self.task_id]["agents"][agent_id]["status"] = "approved"
                tasks[self.task_id]["agents"][agent_id]["message"] = "Completed"

    def flush(self):
        pass

# =========================
# BACKGROUND RUNNER
# =========================
def run_crew_in_background(task_id: str, prompt: str, model: str, temperature: float, max_tokens: int):
    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)

    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10

        result = run_software_crew(prompt)

        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = result

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)

    finally:
        sys.stdout = old_stdout

# =========================
# ROUTES
# =========================
@app.get("/api/health")
async def health():
    return {"status": "ok", "crew": CREW_AVAILABLE}

@app.post("/api/run-crew", response_model=CrewResponse)
async def run_crew(req: CrewRequest):
    task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "result": None,
        "error": None,
        "agents": {
            k: {
                **v,
                "status": "idle",
                "message": "Waiting"
            }
            for k, v in AGENT_TEMPLATES.items()
        },
    }

    task_logs[task_id] = []

    thread = threading.Thread(
        target=run_crew_in_background,
        args=(task_id, req.prompt, req.model, req.temperature, req.max_tokens),
        daemon=True,
    )
    thread.start()

    return CrewResponse(
        success=True,
        task_id=task_id,
        message="Crew started",
        timestamp=datetime.now().isoformat(),
    )

@app.get("/api/task/{task_id}", response_model=TaskStatusResponse)
async def task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        logs=task_logs.get(task_id, []),
        agents=list(task["agents"].values()),
        result=task.get("result"),
        error=task.get("error"),
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
