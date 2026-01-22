# main.py
import os
import re
from dotenv import load_dotenv
from crewai import Crew, Process
from tasks.tasks import SoftwareTasks
from agents.config import (
    code_generator,
    code_reviewer,
    code_refiner,
    doc_writer,
    decision_maker,
)

from app import emit_event  # adjust import path if needed

# Disable telemetry
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"

# Configure Ollama/OpenAI local-compatible API
os.environ["OPENAI_API_KEY"] = "na"
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_MODEL_NAME"] = "qwen2.5:1.5b-instruct"

load_dotenv()


def clean_output(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"```[a-zA-Z]*|```", "", text).strip()


def run_software_crew(requirements: str, task_id: str):
    tasks_manager = SoftwareTasks(requirements)

    task_gen = tasks_manager.generate_code_task(code_generator)
    task_review = tasks_manager.review_code_task(code_reviewer, task_gen)
    task_decision = tasks_manager.decision_task(decision_maker, task_gen)
    task_refine = tasks_manager.refine_code_task(code_refiner, task_gen, task_review)
    task_doc = tasks_manager.document_code_task(doc_writer, task_refine, task_review)

    crew = Crew(
        agents=[
            code_generator,
            code_reviewer,
            decision_maker,
            code_refiner,
            doc_writer,
        ],
        tasks=[
            task_gen,
            task_review,
            task_decision,
            task_refine,
            task_doc,
        ],
        process=Process.sequential,
        verbose=True,
    )

    print("\n--- RUNNING CREW ---\n", flush=True)
    crew.kickoff()
    print("\n--- CREW DONE ---\n", flush=True)

    # =========================
    # EMIT AGENT END EVENTS
    # =========================
    emit_event(task_id, {"type": "agent_end", "agent": "coder"})
    emit_event(task_id, {"type": "agent_end", "agent": "reviewer"})
    emit_event(task_id, {"type": "agent_end", "agent": "decision"})
    emit_event(task_id, {"type": "agent_end", "agent": "refiner"})
    emit_event(task_id, {"type": "agent_end", "agent": "doc_writer"})

    # =========================
    # FINAL CODE OUTPUT
    # =========================
    final_code = clean_output(str(task_refine.output))

    emit_event(
        task_id,
        {
            "type": "code_output",
            "agent": "refiner",
            "code": final_code,
        },
    )

    # =========================
    # TASK COMPLETED
    # =========================
    emit_event(task_id, {"type": "task_completed"})

    results = {
        "generated_code": clean_output(str(task_gen.output)),
        "review_report": str(task_review.output),
        "decision": str(task_decision.output).strip(),
        "refined_code": final_code,
        "documentation": str(task_doc.output),
    }
    
    emit_event(task_id, {
        "type": "code_output",
        "agent": "refiner",
        "code": results["refined_code"],
    })

    emit_event(task_id, {
        "type": "review_output",
        "agent": "reviewer",
        "review": results["review_report"],
    })

    emit_event(task_id, {
        "type": "decision_output",
        "agent": "decision",
        "decision": results["decision"],
    })

    emit_event(task_id, {
        "type": "doc_output",
        "agent": "doc_writer",
        "documentation": results["documentation"],
    })

    return results


if __name__ == "__main__":
    req = input("Enter requirements: ")
    result = run_software_crew(req, task_id="debug")
    print(result)