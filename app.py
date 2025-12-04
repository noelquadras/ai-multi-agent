# app.py
import streamlit as st
import sys
import time
import re
from main import run_software_crew

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Software Team",
    page_icon="🤖",
    layout="wide"
)

# --- CSS Styling ---
st.markdown("""
    <style>
        .stApp { background-color: #0e1117; color: #ffffff; }
        div.stButton > button:first-child { 
            background-color: #00D100; 
            color: white; 
            font-size: 18px; 
            padding: 12px 24px; 
            border-radius: 10px;
        }
        div[data-testid="stExpander"] div[role="button"] p {
            font-size: 1.1rem;
            font-weight: 600;
        }
        .reportview-container .markdown-text-container { font-family: monospace; }
        code { color: #e6e6e6; }
    </style>
""", unsafe_allow_html=True)

# --- Header ---
st.title("🤖 AI Multi-Agent Software Team")
st.caption("Powered by CrewAI, Ollama, and Mistral-7B")

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Sidebar Input ---
with st.sidebar:
    st.header("🛠️ Project Specs")
    requirements = st.text_area(
        "Describe your software requirement:",
        height=200,
        placeholder="e.g., Create a Python script that scrapes the top 5 news headlines from BBC..."
    )
    run_btn = st.button("🚀 Kickoff Crew")
    
    st.markdown("---")
    st.markdown("### 👨‍💻 The Team")
    st.info("1. **Generator:** Architects initial code.\n2. **Reviewer:** Audits for bugs/security.\n3. **Auditor:** Decides if fixes are needed.\n4. **Refiner:** Fixes the code.\n5. **Writer:** Creates documentation.")

# --- Custom Log Capturer ---
class StreamToExpander:
    def __init__(self, expander):
        self.expander = expander
        self.buffer = []
        self.colors = ['red', 'green', 'blue', 'orange']  # regex coloring logic could go here

    def write(self, data):
        # Filter out ANSI escape codes (terminal colors) for clean UI
        cleaned_data = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', data)
        
        # Check if the data implies a new agent is starting to act
        if "Agent:" in cleaned_data:
            self.buffer.append(f"\n\n**{cleaned_data.strip()}**\n")
        elif "Task:" in cleaned_data:
            self.buffer.append(f"> *{cleaned_data.strip()}*\n")
        elif "Entering new CrewAgentExecutor chain" in cleaned_data:
            self.buffer.append(":blue[**...Thinking...**]\n")
        else:
            self.buffer.append(cleaned_data)
            
        # Update the container in the Streamlit UI
        self.expander.markdown(''.join(self.buffer))

    def flush(self):
        pass

# --- Main Execution Logic ---
if run_btn and requirements:
    
    # 1. Create a container for the live logs
    st.subheader("⚙️ Live Agent Activity")
    log_expander = st.expander("Show Agent Thoughts & Actions", expanded=True)
    
    # 2. Capture stdout (console prints) and redirect to UI
    with log_expander:
        with st.spinner("Agents are brainstorming and coding..."):
            try:
                # Redirect standard output to our custom class
                capture_stream = StreamToExpander(log_expander)
                sys.stdout = capture_stream
                
                # Run the Main Orchestrator
                final_results = run_software_crew(requirements)
                
            except Exception as e:
                st.error(f"An error occurred: {e}")
                final_results = None
            finally:
                # Reset stdout back to normal so we don't break other things
                sys.stdout = sys.__stdout__

    # 3. Display Results in Tabs
    if final_results:
        st.divider()
        st.subheader("✅ Final Deliverables")
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "📝 Final Code", 
            "📋 Review Report", 
            "🏗️ Initial Draft", 
            "📚 Documentation"
        ])
        
        with tab1:
            st.markdown("### Refined & Polished Code")
            st.code(final_results['refined_code'], language='python')
            
        with tab2:
            st.markdown("### QA & Security Review")
            st.markdown(final_results['review_report'])
            if "YES" in final_results['decision'].upper():
                st.warning(f"Auditor Decision: Refinement WAS required.")
            else:
                st.success(f"Auditor Decision: Code looked good (Refinement optional).")

        with tab3:
            st.markdown("### Initial Code Generation")
            st.code(final_results['generated_code'], language='python')

        with tab4:
            st.markdown("### Project Documentation")
            st.markdown(final_results['documentation'])