# main.py
import os

# --- CRITICAL: Set Environment Variables BEFORE Imports ---
# This forces the OpenAI client to look at your local Ollama server
os.environ["OPENAI_API_KEY"] = "NA" # Dummy key
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1" # Redirect to Ollama
os.environ["OPENAI_MODEL_NAME"] = "mistral:7b-instruct" # Explicit model name for CrewAI
# ---------------------------------------------------------

import re
from dotenv import load_dotenv
from crewai import Crew, Process
from tasks.tasks import SoftwareTasks
from agents.config import code_generator, code_reviewer, code_refiner, doc_writer, decision_maker

# Load the .env file BEFORE any crewai/langchain imports
load_dotenv()

# --- Utility Function ---

def clean_output(text):
    """Removes common markdown fences and conversational filler."""
    if not text:
        return ""
    # This regex is specifically to remove the outer markdown fences often generated
    text = re.sub(r'```[a-zA-Z]*\s*|```', '', text, flags=re.DOTALL)
    return text.strip()

def run_software_crew(requirements: str):
    # 1. Initialize tasks manager
    tasks_manager = SoftwareTasks(requirements)
    
    # 2. Define all tasks, linking them by dependency
    
    # Task 1: Generate Code (No dependencies)
    task_gen = tasks_manager.generate_code_task(code_generator)
    
    # Task 2: Review Code (Depends on Generation) - Runs in parallel with Task 3
    task_review = tasks_manager.review_code_task(code_reviewer, task_gen)
    
    # Task 3: Decision Maker (Depends on Generation) - Runs in parallel with Task 2
    task_decision = tasks_manager.make_refine_decision_task(decision_maker, task_gen)
    
    # Task 4: Refine Code (Depends on Review and Decision)
    # The Refiner agent itself must interpret the output of task_decision to run its logic.
    task_refine = tasks_manager.refine_code_task(
        code_refiner, 
        task_gen,      # Code Context
        task_review    # Review Context
    )
    
    # Task 5: Document Final Code (Depends on Refinement/Code and Review)
    task_doc = tasks_manager.document_code_task(
        doc_writer, 
        task_refine,   # Final Code Context (from Refiner)
        task_review    # Review Report Context
    )
    
    # 3. Initialize Crew
    software_crew = Crew(
        agents=[code_generator, code_reviewer, code_refiner, doc_writer, decision_maker],
        # The order of tasks determines execution sequence: 
        # T1 -> T2/T3 (Parallel) -> T4 -> T5
        tasks=[task_gen, task_review, task_decision, task_refine, task_doc],
        process=Process.sequential, 
        verbose=True # Ensures detailed step-by-step output
    )

    # --- 4. Execute the entire workflow ---
    
    print("\n--- Starting Full Crew Execution (5-Task Workflow) ---")

    # CrewAI handles sequential and parallel execution defined in tasks.py
    final_result_context = software_crew.kickoff()
    
    print("\n--- Crew Execution Finished ---")

    # FIX: Convert CrewOutput to string before cleaning
    # The actual text is often in the 'raw' attribute or by stringifying the object
    final_output_string = str(final_result_context) 

    return clean_output(final_output_string) 

if __name__ == "__main__":
    print("Welcome to the CrewAI Software Team Agent System!")
    print("--------------------------------------------------")
    
    # Ensure the decision_maker agent is correctly loaded by accessing it
    _ = decision_maker 
    
    requirements = input("Enter software requirements: ")
    
    if not requirements:
        print("Requirements cannot be empty. Exiting.")
    else:
        # Note: CrewAI's .kickoff() returns the output of the LAST task.
        # We assume Agent 3 (Documenter) is instructed to wrap up all information.
        final_doc_output = run_software_crew(requirements)
        
        print("\n\n########################################")
        print("### FINAL DOCUMENTATION OUTPUT ###")
        print("########################################")
        print(final_doc_output)