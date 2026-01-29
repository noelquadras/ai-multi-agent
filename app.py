# =========================
# SSE + EVENT EMITTER BACKEND (B)
# =========================

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import re
import sys
import threading
import json
import asyncio
import os
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AI Software Crew API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONVEX INTEGRATION
# =========================
CONVEX_URL = os.getenv("CONVEX_SITE_URL", "")
CONVEX_DEPLOY_KEY = os.getenv("CONVEX_DEPLOY_KEY", "")

async def convex_mutation(function_name: str, args: Dict[str, Any]):
    """Call a Convex mutation function."""
    if not CONVEX_URL:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CONVEX_URL}/api/mutation",
                json={"path": function_name, "args": args},
                headers={"Authorization": f"Bearer {CONVEX_DEPLOY_KEY}"} if CONVEX_DEPLOY_KEY else {},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Convex mutation error: {e}")
    return None

async def convex_query(function_name: str, args: Dict[str, Any]):
    """Call a Convex query function."""
    if not CONVEX_URL:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CONVEX_URL}/api/query",
                json={"path": function_name, "args": args},
                headers={"Authorization": f"Bearer {CONVEX_DEPLOY_KEY}"} if CONVEX_DEPLOY_KEY else {},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Convex query error: {e}")
    return None

# =========================
# STORAGE
# =========================
tasks: Dict[str, Dict[str, Any]] = {}
task_events: Dict[str, List[Dict[str, Any]]] = {}
subscribers: Dict[str, List[asyncio.Queue]] = {}

# Store model config per task
task_model_config: Dict[str, str] = {}

# =========================
# EVENT EMITTER
# =========================
def emit_event(task_id: str, event: Dict[str, Any]):
    event["timestamp"] = datetime.now().isoformat()
    task_events.setdefault(task_id, []).append(event)

    for q in subscribers.get(task_id, []):
        q.put_nowait(event)

# =========================
# LOGGER → EVENTS
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

        # --- AGENT START ---
        start = re.search(r"\[AGENT_START\s+(\w+)\]", clean)
        if start:
            emit_event(self.task_id, {
                "type": "agent_start",
                "agent": start.group(1),
            })
            return

        # --- AGENT END ---
        end = re.search(r"\[AGENT_END\s+(\w+)\]", clean)
        if end:
            emit_event(self.task_id, {
                "type": "agent_end",
                "agent": end.group(1),
            })
            return

        # --- FINAL CODE BLOCK ---
        code_match = re.search(
            r"```(?:python)?\n([\s\S]*?)```",
            clean
        )
        if code_match:
            emit_event(self.task_id, {
                "type": "code_output",
                "agent": "refiner",
                "code": code_match.group(1).strip(),
            })
            return

        # --- FALLBACK LOG ---
        emit_event(self.task_id, {
            "type": "log",
            "message": clean,
        })

    def flush(self):
        pass

# =========================
# BACKGROUND RUNNER
# =========================
def run_crew(task_id: str, prompt: str, model: str = "ollama"):
    from main import run_software_crew

    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)

    try:
        tasks[task_id]["status"] = "running"
        emit_event(task_id, {
            "type": "log",
            "message": f"Starting workflow with model: {model}",
        })
        run_software_crew(prompt, task_id, model=model)
        tasks[task_id]["status"] = "completed"
        emit_event(task_id, {
            "type": "task_completed",
        })
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        emit_event(task_id, {
            "type": "system_error",
            "error": str(e),
        })
    finally:
        sys.stdout = old_stdout

# =========================
# MODELS
# =========================
class CrewRequest(BaseModel):
    prompt: str
    model: Optional[str] = "ollama"  # "ollama" or "groq"
    user_id: Optional[str] = None
    project_id: Optional[str] = None

class PauseRequest(BaseModel):
    task_id: str

class ResumeRequest(BaseModel):
    task_id: str

# =========================
# ROUTES
# =========================
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}

@app.post("/api/run-crew")
async def run_crew_api(req: CrewRequest):
    task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    tasks[task_id] = {
        "status": "pending",
        "model": req.model,
        "user_id": req.user_id,
        "project_id": req.project_id,
    }
    task_events[task_id] = []
    subscribers[task_id] = []
    task_model_config[task_id] = req.model or "ollama"

    threading.Thread(
        target=run_crew,
        args=(task_id, req.prompt, req.model or "ollama"),
        daemon=True,
    ).start()

    return {"task_id": task_id, "model": req.model}

@app.get("/api/task/{task_id}/events")
async def stream_events(task_id: str, request: Request):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    queue = asyncio.Queue()
    subscribers.setdefault(task_id, []).append(queue)

    async def event_generator():
        try:
            for e in task_events.get(task_id, []):
                yield f"data: {json.dumps(e)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            subscribers[task_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )

@app.get("/api/task/{task_id}")
async def task_snapshot(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "status": tasks[task_id]["status"],
        "model": tasks[task_id].get("model", "ollama"),
        "events": task_events.get(task_id, []),
    }

@app.post("/api/task/{task_id}/pause")
async def pause_task(task_id: str):
    """Pause a running task (stub for human-in-the-loop)."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if tasks[task_id]["status"] != "running":
        raise HTTPException(status_code=400, detail="Task is not running")
    
    tasks[task_id]["status"] = "paused"
    emit_event(task_id, {
        "type": "task_paused",
        "message": "Task paused by user",
    })
    
    return {"status": "paused", "task_id": task_id}

@app.post("/api/task/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a paused task (stub for human-in-the-loop)."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if tasks[task_id]["status"] != "paused":
        raise HTTPException(status_code=400, detail="Task is not paused")
    
    tasks[task_id]["status"] = "running"
    emit_event(task_id, {
        "type": "task_resumed",
        "message": "Task resumed by user",
    })
    
    return {"status": "running", "task_id": task_id}

@app.post("/api/task/{task_id}/approve")
async def approve_code(task_id: str):
    """Approve generated code (human-in-the-loop stub)."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    emit_event(task_id, {
        "type": "human_approval",
        "approved": True,
        "message": "Code approved by user",
    })
    
    return {"status": "approved", "task_id": task_id}

@app.post("/api/task/{task_id}/reject")
async def reject_code(task_id: str):
    """Reject generated code (human-in-the-loop stub)."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    emit_event(task_id, {
        "type": "human_approval",
        "approved": False,
        "message": "Code rejected by user - regenerating",
    })
    
    return {"status": "rejected", "task_id": task_id}

@app.get("/api/models")
async def get_available_models():
    """Get list of available LLM models."""
    return {
        "models": [
            {
                "id": "ollama",
                "name": "Ollama (Local)",
                "description": "Local Mistral 7B model",
                "speed": "medium",
                "cost": "free",
            },
            {
                "id": "groq",
                "name": "Groq (Cloud)",
                "description": "Llama 3.3 70B via Groq API",
                "speed": "fast",
                "cost": "free tier available",
            },
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)