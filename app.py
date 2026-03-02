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
from fastapi import WebSocket, WebSocketDisconnect
from langgraph.types import Command
from terminal_service import manager as terminal_manager

# Import database layer
from database import (
    init_db, 
    get_db_conn,
    get_task_status,
    update_task_status, 
    update_decision_signal,
    update_rejection_feedback,
    get_task_prompt,
    emit_event, 
    subscribers,
    soft_delete_task,
    store_human_message,
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
async def startup_event():
    init_db()
    # Set main loop for terminal manager and pre-warm session
    loop = asyncio.get_running_loop()
    terminal_manager.set_main_loop(loop)
    # create the shared session on the main loop
    try:
        terminal_manager.get_or_create_session("project_terminal_v1", cwd=os.getcwd())
        print("Terminal session 'project_terminal_v1' initialized on main loop.")
    except Exception as e:
        print(f"Failed to initialize terminal session: {e}")

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
    from agents.cancellation import cancellation_registry
    
    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)
    cancellation_registry.register(task_id)

    try:
        update_task_status(task_id, "running")
        emit_event(task_id, {"type": "log", "message": f"Workflow started with {model}"})
        
        # This calls your main logic in main.py
        run_software_crew(prompt, task_id, model=model, agent_models=agent_models)
        
        update_task_status(task_id, "completed")
        emit_event(task_id, {"type": "task_completed"})
    except RuntimeError as e:
        if "cancelled" in str(e).lower():
            update_task_status(task_id, "cancelled")
            emit_event(task_id, {"type": "task_cancelled", "message": str(e)})
        else:
            update_task_status(task_id, "failed")
            emit_event(task_id, {"type": "system_error", "error": str(e)})
    except Exception as e:
        update_task_status(task_id, "failed")
        emit_event(task_id, {"type": "system_error", "error": str(e)})
    finally:
        cancellation_registry.unregister(task_id)
        sys.stdout = old_stdout


def _resume_graph(task_id: str):
    """
    Resume a graph that was suspended via interrupt().

    Spawns in a background thread.  Uses Command(resume=True) so LangGraph
    re-enters the exact node that called interrupt().
    """
    from main import create_agent_graph
    from agents.cancellation import cancellation_registry

    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)
    # Re-register cancellation token (the original was cleaned up when the
    # previous thread finished)
    cancellation_registry.register(task_id)

    try:
        graph = create_agent_graph()
        config = {"configurable": {"thread_id": task_id}}
        # Command(resume=True) tells LangGraph to resume from the interrupt
        graph.invoke(Command(resume=True), config=config)

        update_task_status(task_id, "completed")
        emit_event(task_id, {"type": "task_completed"})
    except RuntimeError as e:
        if "cancelled" in str(e).lower():
            update_task_status(task_id, "cancelled")
            emit_event(task_id, {"type": "task_cancelled", "message": str(e)})
        else:
            update_task_status(task_id, "failed")
            emit_event(task_id, {"type": "system_error", "error": str(e)})
    except Exception as e:
        update_task_status(task_id, "failed")
        emit_event(task_id, {"type": "system_error", "error": str(e)})
    finally:
        cancellation_registry.unregister(task_id)
        sys.stdout = old_stdout


def _continue_graph(task_id: str, new_message: str):
    """
    Continue a completed/terminated workflow with a new human message.

    Re-invokes the graph from the last checkpoint with reset state
    so the supervisor re-classifies and routes the new message.
    """
    from main import create_agent_graph
    from agents.cancellation import cancellation_registry

    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)
    cancellation_registry.register(task_id)

    try:
        graph = create_agent_graph()
        config = {"configurable": {"thread_id": task_id}}

        # Get current state from checkpoint so we preserve context
        current_state = graph.get_state(config)
        prev_requirements = current_state.values.get("requirements", "") if current_state else ""

        # Build updated state: reset flags, update requirements with new message
        updated_state = {
            "terminate": False,
            "intent": None,
            "quick_task_done": False,
            "requirements": f"{prev_requirements}\n\nUser: {new_message}",
        }

        graph.invoke(updated_state, config=config)

        update_task_status(task_id, "completed")
        emit_event(task_id, {"type": "task_completed"})
    except RuntimeError as e:
        if "cancelled" in str(e).lower():
            update_task_status(task_id, "cancelled")
            emit_event(task_id, {"type": "task_cancelled", "message": str(e)})
        else:
            update_task_status(task_id, "failed")
            emit_event(task_id, {"type": "system_error", "error": str(e)})
    except Exception as e:
        update_task_status(task_id, "failed")
        emit_event(task_id, {"type": "system_error", "error": str(e)})
    finally:
        cancellation_registry.unregister(task_id)
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

@app.websocket("/ws/terminal/{client_id}")
async def websocket_terminal(websocket: WebSocket, client_id: str):
    await websocket.accept()
    # Use a fixed session_id to ensure persistence across page refreshes
    session_id = "project_terminal_v1" 
    
    try:
        session = terminal_manager.get_or_create_session(session_id)
        
        # Task to forward PTY output -> WebSocket
        async def send_output():
            async for data in session.read_stream():
                try:
                    await websocket.send_text(data)
                except Exception:
                    break
        
        reader_task = asyncio.create_task(send_output())
        
        # Main loop: WebSocket input -> PTY
        try:
            while True:
                data = await websocket.receive_text()
                # Simple protocol: "RESIZE:cols:rows" or raw input
                if data.startswith("RESIZE:"):
                    parts = data.split(":")
                    if len(parts) == 3:
                        session.resize(int(parts[1]), int(parts[2]))
                else:
                    session.write(data)
        except WebSocketDisconnect:
            pass
        finally:
            reader_task.cancel()
            
    except Exception as e:
        print(f"Terminal Error: {e}")
        await websocket.close()


@app.websocket("/ws/terminal-commands/{client_id}")
async def websocket_terminal_commands(websocket: WebSocket, client_id: str):
    """
    Streams only structured command events to the frontend.

    Each message is a JSON object:
      {"type": "command_start", "command": "python main.py"}
      {"type": "command_output", "command": "python main.py", "output": "Hello world", "exit_code": 0}
    """
    await websocket.accept()
    session_id = "project_terminal_v1"

    try:
        session = terminal_manager.get_or_create_session(session_id)

        async for event in session.read_command_events():
            try:
                await websocket.send_json(event)
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Terminal Commands WS Error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


# --- CONTROL ROUTES ---

class TerminalCommand(BaseModel):
    command: str
    save_code: Optional[str] = None
    filename: Optional[str] = None
    cwd: Optional[str] = None

@app.post("/api/terminal/run")
async def run_terminal_command(body: TerminalCommand):
    """
    Executes a command in the shared terminal session.
    Optionally saves code to a file before running.
    """
    session_id = "project_terminal_v1"
    try:
        # Resolve working directory
        cwd = "../../temp-run"
        cwd_abs = os.path.abspath(cwd)
        
        # Ensure the directory exists
        if not os.path.exists(cwd_abs):
            os.makedirs(cwd_abs, exist_ok=True)

        # If code is provided, save it to the file in the correct directory
        if body.save_code and body.filename:
            # Security check: ensure filename is simple (no path traversal)
            if ".." in body.filename or "/" in body.filename or "\\" in body.filename:
                raise HTTPException(status_code=400, detail="Invalid filename")
            
            file_path = os.path.join(cwd_abs, body.filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(body.save_code)

        session = terminal_manager.get_or_create_session(session_id)
        
        # Combine cd and command to ensure they run in sequence defined by shell
        # Use ; for PowerShell compatibility
        if body.cwd:
             # This path is actually unreachable because we force cwd above, 
             # but strictly speaking logic should use the resolved cwd_abs
             pass
        
        full_command = f'cd "{cwd_abs}"; {body.command}'
        
        # Use new robust command execution
        result = await session.run_command(full_command)
        
        return {
            "status": "completed", 
            "command": body.command,
            "output": result["output"],
            "exit_code": result["exit_code"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/task/{task_id}/pause")
async def pause_task(task_id: str):
    update_task_status(task_id, "paused")
    emit_event(task_id, {"type": "task_paused", "message": "Paused by user"})
    return {"status": "paused"}

@app.post("/api/task/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a paused task by re-entering the graph at the interrupted node."""
    update_task_status(task_id, "running")
    emit_event(task_id, {"type": "task_resumed", "message": "Resumed by user"})
    # Spawn a new thread to resume the graph from the interrupt point
    threading.Thread(target=_resume_graph, args=(task_id,), daemon=True).start()
    return {"status": "running"}

@app.post("/api/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cooperative cancellation — stops the task at the next node boundary.
    
    If the task is currently paused (suspended via interrupt()), we need to
    resume the graph so that check_interrupts can see the cancellation flag
    and raise RuntimeError.  If it's running, the registry flag alone is enough.
    """
    from agents.cancellation import cancellation_registry
    cancellation_registry.cancel(task_id)
    update_task_status(task_id, "cancelled")
    emit_event(task_id, {"type": "task_cancelled", "message": "Cancelled by user"})

    # If the graph is suspended at an interrupt(), wake it up so it can
    # observe the cancellation flag and exit cleanly.
    task_state = get_task_status(task_id)
    if task_state and task_state.get("status") in ("paused", "cancelled"):
        threading.Thread(target=_resume_graph, args=(task_id,), daemon=True).start()

    return {"status": "cancel_requested"}

# --- Updated Human-in-the-Loop Routes ---
@app.post("/api/task/{task_id}/approve")
async def approve_code(task_id: str):
    # Set signal to APPROVED
    update_decision_signal(task_id, "APPROVED")
    
    # If it was paused (waiting for approval), resume the graph
    task_state = get_task_status(task_id)
    if task_state and task_state.get("status") == "paused":
        update_task_status(task_id, "running")
        threading.Thread(target=_resume_graph, args=(task_id,), daemon=True).start()
    
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
    
    # If it was paused, resume the graph
    task_state = get_task_status(task_id)
    if task_state and task_state.get("status") == "paused":
        update_task_status(task_id, "running")
        threading.Thread(target=_resume_graph, args=(task_id,), daemon=True).start()
    
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

class HumanMessageRequest(BaseModel):
    message: str

@app.post("/api/task/{task_id}/message")
async def post_human_message(task_id: str, body: HumanMessageRequest):
    """Receives a human chat message and stores it for the supervisor to pick up.
    If the task has already completed, re-enters the workflow."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    trimmed = body.message.strip()

    # Persist so the supervisor can read it on the next iteration
    store_human_message(task_id, trimmed)

    # Broadcast as an SSE event so the UI confirms delivery
    emit_event(task_id, {
        "type": "human_message",
        "message": trimmed,
    })

    # If the task is completed/failed, re-enter the workflow with the new message
    task_state = get_task_status(task_id)
    if task_state and task_state.get("status") in ("completed", "failed"):
        update_task_status(task_id, "running")
        emit_event(task_id, {"type": "log", "message": "Continuing workflow with new message."})
        threading.Thread(
            target=_continue_graph,
            args=(task_id, trimmed),
            daemon=True,
        ).start()
        return {"status": "continued"}

    return {"status": "sent"}

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


# --- ARTIFACT ROUTES ---

@app.get("/api/task/{task_id}/artifacts")
async def get_task_artifacts(task_id: str):
    """Returns a manifest of all disk-persisted artifacts for a task."""
    from agents.artifacts import list_artifacts
    manifest = list_artifacts(task_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="No artifacts found for this task")
    return {"task_id": task_id, "artifacts": manifest}


@app.get("/api/task/{task_id}/artifacts/{artifact_path:path}")
async def get_artifact_content(task_id: str, artifact_path: str):
    """Download a specific artifact file."""
    from agents.artifacts import load_artifact
    # Security: block path traversal
    if ".." in artifact_path:
        raise HTTPException(status_code=400, detail="Invalid path")
    content = load_artifact(task_id, artifact_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"task_id": task_id, "path": artifact_path, "content": content}


@app.get("/api/task/{task_id}/code-versions")
async def get_code_versions(task_id: str):
    """Return all versioned code files for a task."""
    from pathlib import Path
    code_dir = Path("tasks") / task_id / "code"
    if not code_dir.exists():
        return {"task_id": task_id, "files": []}

    files = []
    for f in sorted(code_dir.glob("solution_v*.py")):
        files.append({
            "filename": f.name,
            "content": f.read_text(encoding="utf-8"),
        })
    # Also include legacy solution.py if it exists
    legacy = code_dir / "solution.py"
    if legacy.exists():
        files.insert(0, {
            "filename": "solution.py",
            "content": legacy.read_text(encoding="utf-8"),
        })
    return {"task_id": task_id, "files": files}

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