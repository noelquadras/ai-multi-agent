# Orchestration Flow — Multi-Agent System

## Function: runMultiAgentFlow(requirements)

### Step 1 — Agent 1: Code Generator
- Input: requirements
- Output: generated code

### Step 2 — Agent 2: Code Reviewer
- Input: generated code
- Output: review report

### Step 3 — Agent 3: Documentation Agent
- Input: generated code + review
- Output: full documentation

### Final Output
{
  generatedCode,
  reviewReport,
  documentation
}

## Implementation Type
- Next.js API Route (recommended)
OR
- Firebase Cloud Function

## Next Steps (Day 2)
- Implement agents using OpenAI/Gemini API calls
- Build orchestrator
- Return JSON output to frontend
