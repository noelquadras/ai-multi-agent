# =========================
# SSE + EVENT EMITTER BACKEND (B)
# =========================

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List
import re
import sys
import threading
import json
import asyncio
from datetime import datetime

app = FastAPI(title="AI Software Crew API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# STORAGE
# =========================
tasks: Dict[str, Dict[str, Any]] = {}
task_events: Dict[str, List[Dict[str, Any]]] = {}
subscribers: Dict[str, List[asyncio.Queue]] = {}

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

        start = re.search(r"\[AGENT_START\s+(\w+)\]", clean)
        end = re.search(r"\[AGENT_END\s+(\w+)\]", clean)

        if start:
            emit_event(self.task_id, {
                "type": "agent_start",
                "agent": start.group(1),
            })
            return

        if end:
            emit_event(self.task_id, {
                "type": "agent_end",
                "agent": end.group(1),
            })
            return

        emit_event(self.task_id, {
            "type": "log",
            "message": clean,
        })

    def flush(self):
        pass

# =========================
# BACKGROUND RUNNER
# =========================
def run_crew(task_id: str, prompt: str):
    from main import run_software_crew

    old_stdout = sys.stdout
    sys.stdout = QueueLogger(task_id)

    try:
        tasks[task_id]["status"] = "running"
        run_software_crew(prompt)
        tasks[task_id]["status"] = "completed"
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

# =========================
# ROUTES
# =========================
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/run-crew")
async def run_crew_api(req: CrewRequest):
    task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    tasks[task_id] = {"status": "pending"}
    task_events[task_id] = []
    subscribers[task_id] = []

    threading.Thread(
        target=run_crew,
        args=(task_id, req.prompt),
        daemon=True,
    ).start()

    return {"task_id": task_id}

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
        "events": task_events.get(task_id, []),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
