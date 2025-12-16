# app.py
import streamlit as st
import sys
import threading
import queue
import importlib
import os
import re
import time
from typing import Dict

# Import Crew runner and sandbox tools
from tools.sandbox_subprocess import run_code_in_subprocess

# -------------------------
# Page config and CSS
# -------------------------
st.set_page_config(page_title="AI Software Crew", page_icon="🤖", layout="wide")
st.markdown("""
<style>
body { background: #0b1220; color: #cfe8ff; }
.panel { padding: 10px; }
.terminal {
  background: #000;
  color: #66ff99;
  padding: 12px;
  border-radius: 6px;
  height: 520px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-family: "Consolas", monospace;
  border: 1px solid #222;
}
.panel-title { font-weight: 600; margin-bottom: 8px; }
.btn { background: #0b5cff; color: #fff; padding: 8px 12px; border-radius: 6px; }
.small { font-size: 12px; color: #9fb0c8; }
</style>
""", unsafe_allow_html=True)

st.title("🤖 AI Software Crew — Live Execution")

# -------------------------
# Layout: left = logs, right = Docker execution
# -------------------------
left_col, right_col = st.columns([2, 2])

# -------------------------
# Sidebar controls
# -------------------------
with st.sidebar:
    st.header("Mission Control")
    model = st.selectbox("Model", ["mistral:7b-instruct", "codellama:13b"], index=0)
    temp = st.slider("Temperature", 0.0, 1.0, 0.2, 0.05)
    max_tokens = st.number_input("Max tokens", min_value=128, max_value=4000, value=1200, step=50)
    requirements = st.text_area(
        "Requirements for Crew",
        height=220,
        placeholder="e.g., Create a CLI app that prints Fibonacci numbers"
    )
    run_crew_btn = st.button("🚀 Run Crew")

# -------------------------
# Thread-safe queue logger
# -------------------------
class QueueLogger:
    def __init__(self, q: queue.Queue):
        self.q = q
        self.ansi = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

    def write(self, message):
        if not message:
            return
        clean = self.ansi.sub("", str(message)).strip()
        if clean:
            self.q.put(clean)

    def flush(self):
        pass

# -------------------------
# Crew runner thread
# -------------------------
def crew_runner(req_text: str, mdl: str, q: queue.Queue, result_holder: Dict):
    os.environ["OPENAI_MODEL_NAME"] = mdl
    os.environ["OPENAI_TEMPERATURE"] = str(temp)
    os.environ["OPENAI_MAX_TOKENS"] = str(max_tokens)

    # Dynamic import of main.py
    try:
        if "main" in sys.modules:
            del sys.modules["main"]
        import main
        importlib.reload(main)
    except Exception as e:
        q.put(f"[ERROR] Failed to import main.py: {e}")
        result_holder["error"] = str(e)
        return

    old_stdout = sys.stdout
    sys.stdout = QueueLogger(q)
    try:
        q.put("[Crew] Starting run_software_crew()")
        out = main.run_software_crew(req_text)
        q.put("[Crew] Completed run_software_crew()")
        result_holder["result"] = out
    except Exception as e:
        q.put(f"[Crew ERROR] {e}")
        result_holder["error"] = str(e)
    finally:
        sys.stdout = old_stdout

# -------------------------
# Junior Dev Docker runner
# -------------------------
def run_junior_dev_docker(code: str, q: queue.Queue):
    q.put("[Docker] Junior Developer running code in Docker...")
    # For simplicity, using sandbox runner (replace with Docker API if desired)
    def stream(line: str, is_err: bool):
        prefix = "[stderr]" if is_err else "[stdout]"
        q.put(f"{prefix} {line}")

    # Try running up to 3 attempts
    attempts = 0
    while attempts < 3:
        attempts += 1
        q.put(f"[Docker] Attempt {attempts}...")
        res = run_code_in_subprocess(code, timeout=60)
        stdout = res.get("stdout", "")
        stderr = res.get("stderr", "")
        if res.get("status") == "success" and res.get("returncode") == 0:
            q.put("[Docker] Execution successful!")
            break
        else:
            q.put(f"[Docker] Execution failed: {stderr or 'Unknown error'}")
            q.put("[Docker] Junior Developer fixing code and retrying...")
            # naive "fix": just try again (replace with actual AI refinement if integrated)
            time.sleep(1)
    q.put("[Docker] Docker execution finished.")

# -------------------------
# Initialize session_state
# -------------------------
if "crew_queue" not in st.session_state:
    st.session_state["crew_queue"] = queue.Queue()
if "crew_result" not in st.session_state:
    st.session_state["crew_result"] = {"result": None, "error": None}
if "log_lines" not in st.session_state:
    st.session_state["log_lines"] = []
if "crew_running" not in st.session_state:
    st.session_state["crew_running"] = False
if "docker_done" not in st.session_state:
    st.session_state["docker_done"] = False

# -------------------------
# Start Crew thread
# -------------------------
if run_crew_btn and not st.session_state["crew_running"]:
    if not requirements.strip():
        st.warning("Please enter requirements first.")
    else:
        st.session_state["crew_running"] = True
        st.session_state["crew_queue"] = queue.Queue()
        st.session_state["crew_result"] = {"result": None, "error": None}
        t = threading.Thread(
            target=crew_runner,
            args=(requirements, model, st.session_state["crew_queue"], st.session_state["crew_result"]),
            daemon=True
        )
        t.start()

# -------------------------
# Left column: Agent logs
# -------------------------
with left_col:
    st.subheader("Agent Logs")
    log_placeholder = st.empty()

# -------------------------
# Right column: Docker execution logs
# -------------------------
with right_col:
    st.subheader("Docker / Junior Dev Execution")
    docker_placeholder = st.empty()

# -------------------------
# Poll queues and update UI
# -------------------------
log_lines = st.session_state["log_lines"]
crew_queue = st.session_state.get("crew_queue")
crew_result = st.session_state.get("crew_result")

if crew_queue:
    while not crew_queue.empty():
        ln = crew_queue.get_nowait()
        log_lines.append(ln)

st.session_state["log_lines"] = log_lines
log_placeholder.markdown(
    "<div class='terminal'>" + "<br>".join(log_lines) + "</div>", unsafe_allow_html=True
)

# -------------------------
# Launch Docker run automatically if Crew finished
# -------------------------
if crew_result.get("result") and not st.session_state["docker_done"]:
    code_to_run = crew_result["result"].get("refined_code") or crew_result["result"].get("generated_code")
    if code_to_run:
        st.session_state["docker_done"] = True
        docker_queue = queue.Queue()
        t = threading.Thread(target=run_junior_dev_docker, args=(code_to_run, docker_queue), daemon=True)
        t.start()
        st.session_state["docker_queue"] = docker_queue

# -------------------------
# Poll Docker queue
# -------------------------
docker_queue = st.session_state.get("docker_queue")
docker_lines = st.session_state.get("docker_lines", [])
if docker_queue:
    while not docker_queue.empty():
        ln = docker_queue.get_nowait()
        docker_lines.append(ln)
st.session_state["docker_lines"] = docker_lines
docker_placeholder.markdown(
    "<div class='terminal'>" + "<br>".join(docker_lines) + "</div>", unsafe_allow_html=True
)

# -------------------------
# Display final deliverables
# -------------------------
if crew_result.get("error"):
    st.error("Crew Error: " + str(crew_result["error"]))
elif crew_result.get("result"):
    st.markdown("---")
    st.subheader("Final Deliverables")
    r = crew_result["result"]
    st.markdown("### Generated / Refined Code (first 5000 chars):")
    st.code((r.get("refined_code") or r.get("generated_code") or "No code"), language="python")
    st.markdown("### Review Report")
    st.write(r.get("review_report", "—"))
    st.markdown("### Documentation")
    st.write(r.get("documentation", "—"))
