# agents/config.py
from crewai import Agent, LLM
from dotenv import load_dotenv
from tools.executor import execute as python_executor  # rename for compatibility


# Load environment variables
load_dotenv() 

# --- Initialize Local LLM Connection (The CrewAI Way) ---
# We use the generic LLM class to explicitly define the provider and base_url
# This prevents CrewAI from defaulting to the standard OpenAI endpoint.
ollama_llm = LLM(
    model="ollama/mistral:7b-instruct", # Prefix with 'ollama/' is critical for some versions
    base_url="http://localhost:11434"
)
# ---------------------------------------

# --- Agent Definitions ---

# Agent 1: Code Generator (The Senior Developer)
code_generator = Agent(
    role='Senior Software Developer',
    goal='Write high-quality, clean, modular, and efficient code based on user requirements.',
    backstory=(
        "You are an expert developer with a focus on code integrity and maintainability. "
        "You always enclose your final output in a single markdown code block."
    ),
    verbose=True,
    llm=ollama_llm,
    max_iter=3
)

# Agent 2: Code Reviewer (The QA Engineer)
code_reviewer = Agent(
    role='Expert QA and Security Auditor',
    goal='Provide a structured, critical review of the provided code, focusing on security, bugs, style, and performance.',
    backstory=(
        "You are meticulous and highly critical. Your only focus is to expose flaws and suggest concrete improvements. "
        "You MUST output the final report following the exact structured format."
    ),
    verbose=True,
    llm=ollama_llm,
    max_iter=3
)

# Agent 5: Decision Maker (The Auditor - Runs in Parallel)
decision_maker = Agent(
    role='System Decision Auditor',
    goal='Determine if the code requires mandatory refinement by analyzing it and outputting ONLY the word "YES" or "NO".',
    backstory=(
        "You are a deterministic system auditor. Your single job is to analyze the generated code "
        "and produce a one-word decision: YES or NO."
    ),
    verbose=True, 
    llm=ollama_llm,
    max_iter=3,
    allow_delegation=False
)

# --- UPDATED Agent 4: Code Refiner ---
code_refiner = Agent(
    role='Junior Developer specializing in Refactoring',
    goal='Fix code by applying review suggestions AND running the code to ensure it works.',
    backstory=(
        "You are responsible for the final, bug-free version of the code. "
        "You have access to a Python execution tool. "
        "You should run the code, check the output, and if there is an error, fix it and run it again until it works."
    ),
    verbose=True,
    allow_code_execution=True,
    llm=ollama_llm,
    max_iter=5, # Give them more iterations to try/fix/try/fix
    tools=[python_executor] # <-- GIVE THE AGENT THE TOOL
)

# Agent 3: Documentation Writer (The Technical Writer)
doc_writer = Agent(
    role='Senior Technical Writer',
    goal='Generate professional, complete documentation and README files for the final, correct code.',
    backstory=(
        "You convert complex code into simple, well-formatted markdown documents, making the project easy to understand."
    ),
    verbose=True,
    llm=ollama_llm
)