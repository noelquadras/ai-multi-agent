# 🤖 AI Multi-Agent Architecture

## 🎯 Project Goal
The primary goal of this project is to automate the development workflow by creating a sequence of specialized AI agents that collaboratively fulfill a user's code requirement, resulting in generated code, a detailed review, and comprehensive documentation.

---

## 🏗️ System Structure: Layered Design

The architecture is split into three logical layers to ensure a clean separation of concerns:

### 1. API Layer (`app/api/run/route.js`)
This layer handles the external interface of the application.
* **Purpose:** Receives user requests (via HTTP POST) containing requirements and returns the final processed results.
* **Technology:** Built using **Next.js Route Handlers** for a serverless API endpoint.
* **Responsibility:** Authentication, input validation, and interfacing directly with the Orchestration Layer. It remains "dumb" concerning the agent logic.

### 2. Orchestration Layer (`lib/orchestrator.js`)
This is the **"Boss"** layer that manages the flow of execution and data between the agents.
* **Purpose:** Defines the linear workflow (the "plan") and cleans up agent output.
* **Flow:** Executes agents in a strict sequence:
    1. Agent 1 (Code Generator)
    2. Agent 2 (Code Reviewer)
    3. Agent 3 (Documentation Writer)
* **Key Function:** Includes a **post-processing step** (`cleanAgentOutput`) to ensure structured outputs are passed cleanly from one agent to the next, removing unwanted conversational filler.

### 3. Agent Layer (`lib/agents.js` & `lib/agentPrompts.js`)
This layer defines the individual intelligence and personality of each worker.
* **`lib/agents.js`:** Contains the wrapper functions for the Language Model (LLM) calls, defining parameters (like temperature, max tokens) and connecting to the Hugging Face Inference API via the OpenAI client wrapper.
* **`lib/agentPrompts.js`:** Stores the detailed, specialized **System Prompts** that give each agent its role (Generator, Reviewer, Documenter) and strict output formatting rules.
* **LLM Connection:** Uses the **HuggingFaceTB/SmolLM3-3B:hf-inference** model via the `OpenAI` client compatible with the Hugging Face Router.

---

## 🔄 Execution Flow (Conceptual Diagram)
The process is a sequential pipeline where the output of an upstream agent becomes the input for a downstream agent. 

1.  **API POST Request (Requirements)** $\rightarrow$ Passes requirements to Orchestrator.
2.  **Orchestrator** $\rightarrow$ Calls Agent 1.
3.  **Agent 1 (Code Generator)** $\rightarrow$ Outputs **Code**.
4.  **Orchestrator** $\rightarrow$ Cleans Code, passes **Code** to Agent 2.
5.  **Agent 2 (Code Reviewer)** $\rightarrow$ Outputs **Review Report**.
6.  **Orchestrator** $\rightarrow$ Cleans Report, passes **Code + Review Report** to Agent 3.
7.  **Agent 3 (Documentation Writer)** $\rightarrow$ Outputs **Documentation**.
8.  **Orchestrator** $\rightarrow$ Cleans Documentation, returns final `{code, review, docs}` object.
9.  **API Layer** $\rightarrow$ Sends final JSON response back to the user.