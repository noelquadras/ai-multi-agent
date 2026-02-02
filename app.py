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
import sqlite3
from dotenv import load_dotenv

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

# =========================
# SQLITE DATABASE LAYER
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crew_tasks.db")

def get_db_conn():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    """Creates tables if they don't exist."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Primary table for overall task status
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT,
                model TEXT,
                user_id TEXT,
                project_id TEXT,
                created_at TEXT
            )
        ''')
        # Table for every log/event produced by the agents
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                type TEXT,
                data TEXT,
                timestamp TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        ''')
        conn.commit()

@app.on_event("startup")
def startup_event():
    init_db()

# =========================
# REAL-TIME STATE (RAM ONLY)
# =========================
# Subscribers are live browser connections. They cannot be saved to a DB.
subscribers: Dict[str, List[asyncio.Queue]] = {}

# =========================
# CORE LOGIC HELPERS
# =========================
def update_task_status(task_id: str, status: str):
    """Updates the status in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
        conn.commit()

def emit_event(task_id: str, event: Dict[str, Any]):
    """Saves event to DB and broadcasts to any live UI listeners."""
    timestamp = datetime.now().isoformat()
    event["timestamp"] = timestamp
    
    # 1. Save to SQLite
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (task_id, type, data, timestamp) VALUES (?, ?, ?, ?)",
            (task_id, event.get("type"), json.dumps(event), timestamp)
        )
        conn.commit()

    # 2. Push to active website users (Real-time)
    if task_id in subscribers:
        for q in subscribers[task_id]:
            q.put_nowait(event)

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
def run_crew(task_id: str, prompt: str, model: str):
    from main import run_software_crew
    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)

    try:
        update_task_status(task_id, "running")
        emit_event(task_id, {"type": "log", "message": f"Workflow started with {model}"})
        
        # This calls your main logic in main.py
        run_software_crew(prompt, task_id, model=model)
        
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
    emit_event(task_id, {
        "type": "human_approval",
        "approved": True,
        "message": "Code approved by user",
    })
    return {"status": "approved"}

@app.post("/api/task/{task_id}/reject")
async def reject_code(task_id: str):
    emit_event(task_id, {
        "type": "human_approval",
        "approved": False,
        "message": "Code rejected by user - regenerating",
    })
    return {"status": "rejected"}

@app.post("/api/run-crew")
async def run_crew_api(req: CrewRequest):
    task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model = req.model or "ollama"

    # Save initial task state
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (task_id, status, model, user_id, project_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, "pending", model, req.user_id, req.project_id, datetime.now().isoformat())
        )
        conn.commit()

    subscribers[task_id] = []
    threading.Thread(target=run_crew, args=(task_id, req.prompt, model), daemon=True).start()
    return {"task_id": task_id, "model": model}

@app.get("/api/history")
async def get_all_history():
    """BONUS: Returns all past tasks for a 'History' sidebar."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        cols = [column[0] for column in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

@app.get("/api/models")
async def get_available_models():
    return {"models": [
        {"id": "ollama", "name": "Ollama (Local)", "speed": "medium", "cost": "free"},
        {"id": "groq", "name": "Groq (Cloud)", "speed": "fast", "cost": "free tier"}
    ]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)