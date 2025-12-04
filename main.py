# main.py
import os
import re
from dotenv import load_dotenv
from crewai import Crew, Process
from tasks.tasks import SoftwareTasks
from agents.config import code_generator, code_reviewer, code_refiner, doc_writer, decision_maker

# --- CRITICAL: Set Environment Variables BEFORE Imports ---
os.environ["OPENAI_API_KEY"] = "NA" 
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1" 
os.environ["OPENAI_MODEL_NAME"] = "mistral:7b-instruct" 
# ---------------------------------------------------------

# Load the .env file 
load_dotenv()

def run_software_crew(requirements: str):
    # 1. Initialize tasks manager
    tasks_manager = SoftwareTasks(requirements)
    
    # 2. Define all tasks
    task_gen = tasks_manager.generate_code_task(code_generator)
    task_review = tasks_manager.review_code_task(code_reviewer, task_gen)
    task_decision = tasks_manager.make_refine_decision_task(decision_maker, task_gen)
    
    task_refine = tasks_manager.refine_code_task(
        code_refiner, 
        task_gen,      # Code Context
        task_review    # Review Context
    )
    
    task_doc = tasks_manager.document_code_task(
        doc_writer, 
        task_refine,   # Final Code Context
        task_review    # Review Report Context
    )
    
    # 3. Initialize Crew
    software_crew = Crew(
        agents=[code_generator, code_reviewer, code_refiner, doc_writer, decision_maker],
        tasks=[task_gen, task_review, task_decision, task_refine, task_doc],
        process=Process.sequential, 
        verbose=True 
    )

    # 4. Execute the workflow
    print("\n\n################################################")
    print("## 🚀 STARTING CREW EXECUTION                 ##")
    print("################################################\n")
    
    result = software_crew.kickoff()
    
    print("\n\n################################################")
    print("## ✅ EXECUTION COMPLETE                      ##")
    print("################################################\n")

    # 5. Extract structured outputs from the tasks directly
    # CrewAI stores the output in the task object after execution
    return {
        "generated_code": str(task_gen.output),
        "review_report": str(task_review.output),
        "decision": str(task_decision.output),
        "refined_code": str(task_refine.output),
        "documentation": str(task_doc.output)
    }

if __name__ == "__main__":
    # CLI Fallback
    req = input("Enter requirements: ")
    res = run_software_crew(req)
    print(res)