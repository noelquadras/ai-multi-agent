# app.py - FastAPI Backend (EVENT-DRIVEN + SSE)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import re
import sys
import threading
import json
import asyncio
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
app = FastAPI(title="AI Software Crew API", version="2.1.0")

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
    events: List[Dict[str, Any]]
    agents: List[Dict[str, Any]]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# =========================
# STORAGE
# =========================
tasks: Dict[str, Dict[str, Any]] = {}
task_logs: Dict[str, List[str]] = {}
task_events: Dict[str, List[Dict[str, Any]]] = {}

# =========================
# LOGGER (EVENT-DRIVEN)
# =========================
class QueueLogger:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.ansi = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")

    def emit_event(self, event_type: str, agent: Optional[str], message: str):
        event = {
            "type": event_type,
            "agent": agent,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "message": message,
        }
        task_events[self.task_id].append(event)

    def write(self, message):
        if not message:
            return

        clean = self.ansi.sub("", str(message)).strip()
        if not clean:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        task_logs[self.task_id].append(f"[{ts}] {clean}")

        start_match = re.search(r"\[AGENT_START\s+(\w+)\]", clean)
        if start_match:
            agent_id = start_match.group(1)
            if agent_id in tasks[self.task_id]["agents"]:
                tasks[self.task_id]["agents"][agent_id]["status"] = "thinking"
                tasks[self.task_id]["agents"][agent_id]["message"] = "Working"
                self.emit_event("agent_start", agent_id, "Agent started working")

        end_match = re.search(r"\[AGENT_END\s+(\w+)\]", clean)
        if end_match:
            agent_id = end_match.group(1)
            if agent_id in tasks[self.task_id]["agents"]:
                tasks[self.task_id]["agents"][agent_id]["status"] = "approved"
                tasks[self.task_id]["agents"][agent_id]["message"] = "Completed"
                self.emit_event("agent_end", agent_id, "Agent completed task")

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
        tasks[task_id]["progress"] = 5
        task_events[task_id].append({
            "type": "crew_start",
            "agent": None,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "message": "Crew execution started",
        })

        result = run_software_crew(prompt)

        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = result

        task_events[task_id].append({
            "type": "crew_end",
            "agent": None,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "message": "Crew execution completed",
        })

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        task_events[task_id].append({
            "type": "error",
            "agent": None,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "message": str(e),
        })

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
            k: {**v, "status": "idle", "message": "Waiting"}
            for k, v in AGENT_TEMPLATES.items()
        },
    }

    task_logs[task_id] = []
    task_events[task_id] = []

    threading.Thread(
        target=run_crew_in_background,
        args=(task_id, req.prompt, req.model, req.temperature, req.max_tokens),
        daemon=True,
    ).start()

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
        events=task_events.get(task_id, []),
        agents=list(task["agents"].values()),
        result=task.get("result"),
        error=task.get("error"),
    )

@app.get("/api/task/{task_id}/events")
async def stream_events(task_id: str):
    if task_id not in task_events:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_index = 0
        while True:
            events = task_events.get(task_id, [])
            while last_index < len(events):
                yield f"data: {json.dumps(events[last_index])}\n\n"
                last_index += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
