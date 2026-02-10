# =========================
# FINAL YEAR PROJECT: AI MULTI-AGENT BACKEND (SQLITE)
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
from datetime import datetime
from dotenv import load_dotenv
import httpx

# Import database layer
from database import (
    init_db, 
    get_db_conn, 
    update_task_status, 
    update_decision_signal,
    update_rejection_feedback,
    get_task_prompt,
    emit_event, 
    subscribers,
    soft_delete_task
)

load_dotenv()

app = FastAPI(title="AI Software Crew API", version="3.1.0")

# --- CORS SETUP ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

# =========================
# LOGGER CLASS
# =========================
class QueueLogger:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.ansi = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")

    def write(self, message):
        if not message: return
        clean = self.ansi.sub("", str(message)).strip()
        if not clean: return

        # Identify special Agent markers or generic logs
        if start := re.search(r"\[AGENT_START\s+(\w+)\]", clean):
            emit_event(self.task_id, {"type": "agent_start", "agent": start.group(1)})
        elif end := re.search(r"\[AGENT_END\s+(\w+)\]", clean):
            emit_event(self.task_id, {"type": "agent_end", "agent": end.group(1)})
        elif code := re.search(r"```(?:python)?\n([\s\S]*?)```", clean):
            emit_event(self.task_id, {"type": "code_output", "agent": "refiner", "code": code.group(1).strip()})
        else:
            emit_event(self.task_id, {"type": "log", "message": clean})

    def flush(self): pass

# =========================
# BACKGROUND WORKER
# =========================
def run_crew(task_id: str, prompt: str, model: str, agent_models: Optional[Dict[str, str]] = None):
    # Lazy import to avoid circular dependency if main imports app
    from main import run_software_crew
    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)

    try:
        update_task_status(task_id, "running")
        emit_event(task_id, {"type": "log", "message": f"Workflow started with {model}"})
        
        # This calls your main logic in main.py
        run_software_crew(prompt, task_id, model=model, agent_models=agent_models)
        
        update_task_status(task_id, "completed")
        emit_event(task_id, {"type": "task_completed"})
    except Exception as e:
        update_task_status(task_id, "failed")
        emit_event(task_id, {"type": "system_error", "error": str(e)})
    finally:
        sys.stdout = old_stdout

# =========================
# API ROUTES
# =========================
class CrewRequest(BaseModel):
    prompt: str
    model: Optional[str] = "ollama"
    agent_models: Optional[Dict[str, str]] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None

@app.get("/api/health")
async def health_check():
    """Confirms the API is up and the Database is reachable."""
    try:
        with get_db_conn() as conn:
            conn.execute("SELECT 1") # A tiny 'poke' to the database
        return {"status": "ok", "version": "3.1.0", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}

@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """Soft deletes a task (moves to archive)."""
    success = soft_delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted", "task_id": task_id}


@app.get("/api/task/{task_id}")
async def task_snapshot(task_id: str):
    """Fetches full state from DB for a specific task."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, model FROM tasks WHERE task_id = ?", (task_id,))
        task_data = cursor.fetchone()
        if not task_data: raise HTTPException(status_code=404, detail="Task not found")
        
        cursor.execute("SELECT data FROM events WHERE task_id = ? ORDER BY id ASC", (task_id,))
        events = [json.loads(row[0]) for row in cursor.fetchall()]
        
    return {"task_id": task_id, "status": task_data[0], "model": task_data[1], "events": events}

@app.get("/api/task/{task_id}/events")
async def stream_events(task_id: str, request: Request):
    """Real-time SSE stream of logs."""
    queue = asyncio.Queue()
    subscribers.setdefault(task_id, []).append(queue)

    async def event_generator():
        try:
            # 1. Send all past events from DB first so the UI catches up
            with get_db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM events WHERE task_id = ? ORDER BY id ASC", (task_id,))
                for row in cursor.fetchall():
                    yield f"data: {row[0]}\n\n"

            # 2. Keep the connection open for new live events
            while True:
                if await request.is_disconnected(): break
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            if task_id in subscribers:
                subscribers[task_id].remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- CONTROL ROUTES ---

@app.post("/api/task/{task_id}/pause")
async def pause_task(task_id: str):
    update_task_status(task_id, "paused")
    emit_event(task_id, {"type": "task_paused", "message": "Paused by user"})
    return {"status": "paused"}

@app.post("/api/task/{task_id}/resume")
async def resume_task(task_id: str):
    update_task_status(task_id, "running")
    emit_event(task_id, {"type": "task_resumed", "message": "Resumed by user"})
    return {"status": "running"}

# --- Updated Human-in-the-Loop Routes ---
@app.post("/api/task/{task_id}/approve")
async def approve_code(task_id: str):
    # Set signal to APPROVED
    update_decision_signal(task_id, "APPROVED")
    
    # If it was paused (waiting for approval), resume it
    update_task_status(task_id, "running")
    
    emit_event(task_id, {
        "type": "human_approval",
        "approved": True,
        "message": "Code approved by user",
    })
    return {"status": "approved"}

class RejectRequest(BaseModel):
    feedback: Optional[str] = None

@app.post("/api/task/{task_id}/reject")
async def reject_code(task_id: str, body: RejectRequest = None):
    # Set signal to REJECTED
    update_decision_signal(task_id, "REJECTED")
    
    # Store feedback if provided
    if body and body.feedback:
        update_rejection_feedback(task_id, body.feedback)
    
    # If it was paused, resume it
    update_task_status(task_id, "running")
    
    emit_event(task_id, {
        "type": "human_approval",
        "approved": False,
        "message": f"Code rejected by user{' with feedback' if body and body.feedback else ''}",
        "feedback": body.feedback if body else None,
    })
    return {"status": "rejected"}

class RegenerateRequest(BaseModel):
    feedback: Optional[str] = None

@app.post("/api/task/{task_id}/regenerate")
async def regenerate_task(task_id: str, body: RegenerateRequest = None):
    """Regenerate a task with the original prompt + optional feedback."""
    # Get original prompt
    original_prompt = get_task_prompt(task_id)
    if not original_prompt:
        raise HTTPException(status_code=404, detail="Original task not found or has no prompt")
    
    # Get model from original task
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT model FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        model = row[0] if row else "ollama"
    
    # Build new prompt with feedback
    new_prompt = original_prompt
    if body and body.feedback:
        new_prompt = f"""{original_prompt}

---
IMPORTANT USER FEEDBACK (address this as top priority):
{body.feedback}
---"""
    
    # Create new task
    new_task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (task_id, status, model, created_at, decision_signal, prompt) VALUES (?, ?, ?, ?, ?, ?)",
            (new_task_id, "pending", model, datetime.now().isoformat(), None, new_prompt)
        )
        conn.commit()
    
    subscribers[new_task_id] = []
    threading.Thread(target=run_crew, args=(new_task_id, new_prompt, model), daemon=True).start()
    
    return {"task_id": new_task_id, "model": model}

@app.post("/api/run-crew")
async def run_crew_api(req: CrewRequest):
    task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model = req.model or "ollama"

    # Save initial task state
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (task_id, status, model, user_id, project_id, created_at, decision_signal, prompt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, "pending", model, req.user_id, req.project_id, datetime.now().isoformat(), None, req.prompt)
        )
        conn.commit()

    subscribers[task_id] = []
    threading.Thread(target=run_crew, args=(task_id, req.prompt, model, req.agent_models), daemon=True).start()
    return {"task_id": task_id, "model": model}

@app.get("/api/history")
async def get_all_history():
    """Returns all past tasks for a 'History' sidebar."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        cols = [column[0] for column in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

@app.get("/api/models")
async def get_available_models():
    # 1. Fetch local Ollama models
    local_models = []
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                # Transform to our model format
                for model in data.get("models", []):
                    model_name = model["name"]
                    # Clean up name if it has :latest
                    display_name = model_name.split(":")[0]
                    local_models.append({
                        "id": model_name,
                        "name": f"{display_name} (Local)",
                        "speed": "medium",
                        "cost": "free",
                        "description": f"Local Ollama model: {model_name}",
                        "type": "local"
                    })
    except Exception as e:
        print(f"Failed to fetch Ollama models: {e}")

    # 2. Load static/cloud models
    try:
        with open("models.json", "r") as f:
            static_models = json.load(f)
            # Add type field to static models if missing
            for m in static_models:
                if "type" not in m:
                    m["type"] = "cloud" if "Cloud" in m["name"] else "local"
    except Exception:
        static_models = []

    # 3. Combine (local first, then static)
    # Deduplicate by ID if needed, but usually local and static won't clash if named differently
    return {"models": local_models + static_models}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)