# main.py
import os
import re
from dotenv import load_dotenv
from crewai import Crew, Process
from tasks.tasks import SoftwareTasks
from agents.config import code_generator, code_reviewer, code_refiner, doc_writer, decision_maker

# Disable telemetry
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"

# Configure Ollama/OpenAI local-compatible API
os.environ["OPENAI_API_KEY"] = "na"
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_MODEL_NAME"] = "mistral:7b-instruct"

load_dotenv()

# --- CLEAN OUTPUT (removes ``` wrappers etc) ---
def clean_output(text):
    if not text:
        return ""
    return re.sub(r"```[a-zA-Z]*|```", "", text).strip()


def run_software_crew(requirements: str):
    tasks_manager = SoftwareTasks(requirements)

    task_gen = tasks_manager.generate_code_task(code_generator)
    task_review = tasks_manager.review_code_task(code_reviewer, task_gen)
    task_decision = tasks_manager.make_refine_decision_task(decision_maker, task_gen)
    task_refine = tasks_manager.refine_code_task(code_refiner, task_gen, task_review)
    task_doc = tasks_manager.document_code_task(doc_writer, task_refine, task_review)

    crew = Crew(
        agents=[code_generator, code_reviewer, code_refiner, doc_writer, decision_maker],
        tasks=[task_gen, task_review, task_decision, task_refine, task_doc],
        process=Process.sequential,
        verbose=True
    )

    print("\n--- RUNNING CREW ---\n", flush=True)
    crew.kickoff()
    print("\n--- CREW DONE ---\n", flush=True)

    return {
        "generated_code": clean_output(str(task_gen.output)),
        "review_report": str(task_review.output),
        "decision": str(task_decision.output).strip(),
        "refined_code": clean_output(str(task_refine.output)),
        "documentation": str(task_doc.output),
    }


if __name__ == "__main__":
    req = input("Enter requirements: ")
    result = run_software_crew(req)
    print(result)
