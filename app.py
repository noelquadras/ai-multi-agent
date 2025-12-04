import streamlit as st
import streamlit.components.v1 as components
import sys
import time
import re
import threading
import queue
from main import run_software_crew

# --- Page Config ---
st.set_page_config(
    page_title="AI Software Team",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #c9d1d9; }
    
    /* Terminal Box Styling */
    .terminal-box {
        font-family: 'Consolas', 'Courier New', monospace;
        background-color: #000000;
        color: #00ff00; /* Hacker Green */
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #333;
        height: 500px;
        overflow-y: auto; /* Allow scrolling */
        font-size: 14px;
        line-height: 1.5;
        white-space: pre-wrap; /* Preserve formatting */
        box-shadow: inset 0 0 15px rgba(0,0,0,0.8);
    }
    
    .agent-header { color: #ffcc00; font-weight: bold; font-size: 1.1em; border-bottom: 1px solid #444; padding-bottom: 3px; }
    .task-header { color: #00ccff; font-style: italic; margin-top: 10px; }
    .thought-text { color: #888; font-size: 0.9em; }
    .success-text { color: #00ff00; font-weight: bold; }
    .error-text { color: #ff4444; }
    </style>
""", unsafe_allow_html=True)

st.title("🤖 AI Software Crew")
st.markdown("#### Local Multi-Agent Development Team (Mistral-7B)")

# --- Sidebar ---
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/bot.png", width=80)
    st.header("Mission Control")
    requirements = st.text_area("Requirements:", height=200, placeholder="e.g., Write a Snake Game in Python.")
    run_btn = st.button("🚀 Kickoff Crew", type="primary")

# --- Thread-Safe Logger ---
class QueueLogger:
    """
    Redirects console output to a Python Queue instead of the screen.
    This allows the background thread to write logs safely.
    """
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.terminal = sys.stdout 
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        self.box_escape = re.compile(r'[╭╮╰╯│─]+') 

    def write(self, message):
        # 1. Clean the message
        cleaned = self.ansi_escape.sub('', message)
        cleaned = self.box_escape.sub('', cleaned)
        
        # 2. Put in queue if it's not just whitespace
        if cleaned.strip():
            formatted = cleaned
            if "Agent:" in cleaned:
                formatted = f"\n<span class='agent-header'>🤖 {cleaned.strip()}</span>"
            elif "Task:" in cleaned:
                formatted = f"\n<span class='task-header'>📋 {cleaned.strip()}</span>"
            elif "Entering new CrewAgentExecutor chain" in cleaned:
                formatted = "<span class='thought-text'>...Thinking...</span>"
            elif "Final Answer:" in cleaned:
                formatted = f"\n<span class='success-text'>✅ {cleaned.strip()}</span>"
            
            self.log_queue.put(formatted)

    def flush(self):
        pass

# --- Main Execution Logic ---
if run_btn and requirements:
    st.subheader("⚙️ Live Agent Operations")
    
    # 1. Setup UI Container
    log_container = st.empty()
    scroller_container = st.empty() # Invisible container for JS updates
    log_buffer = []
    
    # 2. Setup Threading
    log_queue = queue.Queue()
    result_container = {"result": None, "error": None}

    def run_in_thread(reqs, q, res_cont):
        sys.stdout = QueueLogger(q)
        try:
            res_cont["result"] = run_software_crew(reqs)
        except Exception as e:
            res_cont["error"] = str(e)
        finally:
            sys.stdout = sys.__stdout__ 

    # 3. Start Background Thread
    bg_thread = threading.Thread(target=run_in_thread, args=(requirements, log_queue, result_container))
    bg_thread.start()

    # 4. Main Loop: Poll Queue -> Update UI
    counter = 0 
    while bg_thread.is_alive() or not log_queue.empty():
        try:
            # Get line from queue
            line = log_queue.get_nowait()
            log_buffer.append(line)
            
            # Update the UI container
            log_content = '<br>'.join(log_buffer)
            html_content = f"""
            <div id='terminal-logs' class='terminal-box'>
                {log_content}
            </div>
            """
            log_container.markdown(html_content, unsafe_allow_html=True)
            
            # --- JS SCROLL INJECTION (Fixed Syntax) ---
            if counter % 5 == 0: # Throttle JS updates
                js = f"""
                    <script>
                        var terminal = window.parent.document.getElementById('terminal-logs');
                        if (terminal) {{
                            terminal.scrollTop = terminal.scrollHeight;
                        }}
                    </script>
                """
                # FIX: Use 'with' block to place component in the specific container
                with scroller_container:
                    components.html(js, height=0, width=0)
            
            counter += 1
            
        except queue.Empty:
            time.sleep(0.1) 

    # 5. Handle Results
    if result_container["error"]:
        st.error(f"Execution Failed: {result_container['error']}")
    
    elif result_container["result"]:
        result = result_container["result"]
        st.markdown("---")
        st.subheader("📦 Final Deliverables")
        
        tab1, tab2, tab3, tab4 = st.tabs(["💻 Code", "🛡️ Review Report", "📚 Documentation", "🔍 Raw Data"])
        
        with tab1:
            code = result.get('refined_code') 
            if not code or code == "None": 
                code = result.get('generated_code')
            st.code(code, language='python')

        with tab2:
            st.markdown(result['review_report'])
            
        with tab3:
            st.markdown(result['documentation'])
            
        with tab4:
            st.json(result)
            st.write(f"Decision: {result.get('decision')}")

elif run_btn and not requirements:
    st.warning("Please enter requirements first.")