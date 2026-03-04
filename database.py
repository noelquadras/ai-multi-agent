import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import asyncio

# =========================
# SQLITE DATABASE LAYER
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crew_tasks.db")

# =========================
# REAL-TIME STATE (RAM ONLY)
# =========================
# Subscribers are live browser connections. They cannot be saved to a DB.
subscribers: Dict[str, List[asyncio.Queue]] = {}

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
                created_at TEXT,
                decision_signal TEXT,
                rejection_feedback TEXT,
                prompt TEXT,
                human_approval TEXT
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
        
        # Table for deleted tasks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deleted_tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT,
                model TEXT,
                user_id TEXT,
                project_id TEXT,
                created_at TEXT,
                decision_signal TEXT,
                rejection_feedback TEXT,
                prompt TEXT,
                human_approval TEXT,
                deleted_at TEXT
            )
        ''')

        # Table for deleted events
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deleted_events (
                id INTEGER PRIMARY KEY,
                task_id TEXT,
                type TEXT,
                data TEXT,
                timestamp TEXT,
                deleted_at TEXT
            )
        ''')

        # Migration: Add columns to tasks if they don't exist
        for column in ["decision_signal", "rejection_feedback", "prompt", "human_approval"]:
            try:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {column} TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Migration: Add columns to deleted_tasks if they don't exist
        for column in ["decision_signal", "rejection_feedback", "prompt", "human_approval"]:
            try:
                cursor.execute(f"ALTER TABLE deleted_tasks ADD COLUMN {column} TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
        # Table for human chat messages sent mid-workflow
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS human_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                message TEXT,
                consumed INTEGER DEFAULT 0,
                timestamp TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        ''')

        conn.commit()

def soft_delete_task(task_id: str):
    """Moves task and its events to deleted tables and removes from active tables."""
    deleted_at = datetime.now().isoformat()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        # 1. Archive Task
        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
             # Task might already be deleted or not found
            return False

        # Get column names to construct INSERT
        col_names = [description[0] for description in cursor.description]
        placeholders = ", ".join(["?"] * len(col_names))
        columns = ", ".join(col_names)
        
        # Add deleted_at
        insert_sql = f"INSERT INTO deleted_tasks ({columns}, deleted_at) VALUES ({placeholders}, ?)"
        cursor.execute(insert_sql, (*task_row, deleted_at))

        # 2. Archive Events
        cursor.execute("SELECT * FROM events WHERE task_id = ?", (task_id,))
        events_rows = cursor.fetchall()
        
        if events_rows:
            event_col_names = [description[0] for description in cursor.description]
            event_placeholders = ", ".join(["?"] * len(event_col_names))
            event_columns = ", ".join(event_col_names)
            
            event_insert_sql = f"INSERT INTO deleted_events ({event_columns}, deleted_at) VALUES ({event_placeholders}, ?)"
            # Execute many for events
            events_data = [(*row, deleted_at) for row in events_rows]
            cursor.executemany(event_insert_sql, events_data)

        # 3. Delete from active tables
        cursor.execute("DELETE FROM events WHERE task_id = ?", (task_id,))
        cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        
        conn.commit()
    return True

def update_task_status(task_id: str, status: str):
    """Updates the status in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
        conn.commit()

def update_decision_signal(task_id: str, signal: Optional[str]):
    """Updates the decision signal (APPROVED/REJECTED/None) in the DB."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET decision_signal = ? WHERE task_id = ?", (signal, task_id))
        conn.commit()

def clear_decision_signal(task_id: str):
    """Clears the decision signal after it has been consumed."""
    update_decision_signal(task_id, None)

def update_rejection_feedback(task_id: str, feedback: Optional[str]):
    """Stores rejection feedback from the user."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET rejection_feedback = ? WHERE task_id = ?", (feedback, task_id))
        conn.commit()

def get_rejection_feedback(task_id: str) -> Optional[str]:
    """Gets rejection feedback if any."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT rejection_feedback FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        return row[0] if row else None

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get task status, decision_signal, and rejection_feedback."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, decision_signal, rejection_feedback FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if row:
            return {"status": row[0], "decision_signal": row[1], "rejection_feedback": row[2]}
        return None

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


def broadcast_event(task_id: str, event: Dict[str, Any]):
    """Push event to live UI listeners WITHOUT saving to DB (for stream chunks)."""
    event["timestamp"] = datetime.now().isoformat()
    if task_id in subscribers:
        for q in subscribers[task_id]:
            q.put_nowait(event)

def get_task_prompt(task_id: str) -> Optional[str]:
    """Gets the original prompt for a task."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT prompt FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def store_human_message(task_id: str, message: str):
    """Stores a human chat message for the given task."""
    timestamp = datetime.now().isoformat()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO human_messages (task_id, message, consumed, timestamp) VALUES (?, ?, 0, ?)",
            (task_id, message, timestamp)
        )
        conn.commit()


def get_human_messages(task_id: str, mark_consumed: bool = True) -> List[Dict[str, Any]]:
    """Gets all unconsumed human messages for a task.
    Optionally marks them as consumed so they aren't read twice."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, message, timestamp FROM human_messages WHERE task_id = ? AND consumed = 0 ORDER BY id ASC",
            (task_id,)
        )
        rows = cursor.fetchall()
        messages = [{"id": r[0], "message": r[1], "timestamp": r[2]} for r in rows]

        if mark_consumed and messages:
            ids = [m["id"] for m in messages]
            placeholders = ", ".join(["?"] * len(ids))
            cursor.execute(f"UPDATE human_messages SET consumed = 1 WHERE id IN ({placeholders})", ids)
            conn.commit()

        return messages
