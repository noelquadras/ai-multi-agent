# app.py - FastAPI Backend
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import re
import subprocess
import sys
import json
from datetime import datetime
import asyncio
import threading
import queue
import time

# Import your existing crew functions
try:
    from main import run_software_crew
    from crewai import Crew, Process
    from tasks.tasks import SoftwareTasks
    from agents.config import code_generator, code_reviewer, code_refiner, doc_writer, decision_maker
    CREW_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import crew modules: {e}")
    CREW_AVAILABLE = False
    # Create a mock function for testing
    def run_software_crew(requirements: str):
        return {
            "generated_code": "# Mock code for testing\nprint('Hello from mock crew')",
            "review_report": "Mock review report",
            "decision": "Mock decision",
            "refined_code": "# Mock refined code",
            "documentation": "Mock documentation"
        }

app = FastAPI(
    title="AI Software Crew API",
    description="Autonomous AI software development team backend",
    version="2.0.0"
)

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class CrewRequest(BaseModel):
    prompt: str
    max_iterations: Optional[int] = 3
    model: Optional[str] = "mistral:7b-instruct"
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 1200

class CrewResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    message: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed
    progress: Optional[float] = None  # 0 to 100
    logs: Optional[list] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# In-memory storage for tasks (in production, use Redis or database)
tasks = {}
task_logs = {}

# Queue logger for capturing crew output
class QueueLogger:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.ansi = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        
    def write(self, message):
        if not message:
            return
        clean = self.ansi.sub("", str(message)).strip()
        if clean:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {clean}"
            if self.task_id in task_logs:
                task_logs[self.task_id].append(log_entry)
            else:
                task_logs[self.task_id] = [log_entry]
    
    def flush(self):
        pass

# Background task runner
def run_crew_in_background(task_id: str, prompt: str, model: str, temperature: float, max_tokens: int):
    """Run the software crew in a background thread"""
    try:
        # Update task status
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        
        # Set environment variables
        os.environ["OPENAI_MODEL_NAME"] = model
        os.environ["OPENAI_TEMPERATURE"] = str(temperature)
        os.environ["OPENAI_MAX_TOKENS"] = str(max_tokens)
        
        # Capture stdout
        import sys
        old_stdout = sys.stdout
        sys.stdout = QueueLogger(task_id)
        
        # Add initial log
        logger = QueueLogger(task_id)
        logger.write(f"Starting AI Software Crew with prompt: {prompt[:100]}...")
        logger.write(f"Using model: {model}")
        
        tasks[task_id]["progress"] = 30
        
        try:
            # Run the crew
            result = run_software_crew(prompt)
            
            # Update task with result
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["progress"] = 100
            tasks[task_id]["result"] = result
            tasks[task_id]["error"] = None
            
            logger.write("✓ Crew execution completed successfully!")
            
        except Exception as e:
            error_msg = f"Crew execution failed: {str(e)}"
            logger.write(f"✗ {error_msg}")
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = error_msg
            tasks[task_id]["result"] = None
            
        finally:
            sys.stdout = old_stdout
            
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = f"Background task error: {str(e)}"

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AI Software Crew API",
        "version": "2.0.0",
        "status": "running",
        "crew_available": CREW_AVAILABLE,
        "endpoints": {
            "POST /api/run-crew": "Start a new crew execution",
            "GET /api/task/{task_id}": "Get task status and result",
            "GET /api/health": "Health check"
        }
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "crew_status": "available" if CREW_AVAILABLE else "mock_mode"
    }

@app.post("/api/run-crew", response_model=CrewResponse)
async def run_crew(request: CrewRequest):
    """Start a new AI software crew execution"""
    try:
        # Generate unique task ID
        task_id = f"crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(request.prompt) % 10000:04d}"
        
        # Initialize task
        tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "prompt": request.prompt,
            "model": request.model,
            "created_at": datetime.now().isoformat(),
            "result": None,
            "error": None
        }
        task_logs[task_id] = []
        
        # Start background task
        thread = threading.Thread(
            target=run_crew_in_background,
            args=(task_id, request.prompt, request.model, request.temperature, request.max_tokens),
            daemon=True
        )
        thread.start()
        
        return CrewResponse(
            success=True,
            task_id=task_id,
            message="AI Software Crew started successfully. Use the task_id to check status.",
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start crew: {str(e)}")

@app.get("/api/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get the status of a crew execution task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress", 0),
        logs=task_logs.get(task_id, []),
        result=task.get("result"),
        error=task.get("error")
    )

@app.get("/api/task/{task_id}/logs")
async def get_task_logs(task_id: str, limit: int = 50):
    """Get logs for a specific task"""
    if task_id not in task_logs:
        raise HTTPException(status_code=404, detail="Task not found")
    
    logs = task_logs[task_id]
    if limit > 0:
        logs = logs[-limit:]
    
    return {
        "task_id": task_id,
        "logs": logs,
        "count": len(logs),
        "total": len(task_logs[task_id])
    }

@app.post("/api/test-crew")
async def test_crew(request: CrewRequest):
    """Quick test endpoint (runs synchronously)"""
    try:
        result = run_software_crew(request.prompt)
        return {
            "success": True,
            "message": "Test completed successfully",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Starting AI Software Crew API server...")
    print(f"Crew available: {CREW_AVAILABLE}")
    print("API Documentation: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)