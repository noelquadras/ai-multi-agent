# tasks/tasks.py
from crewai import Task

class SoftwareTasks:
    def __init__(self, requirements):
        self.requirements = requirements

    # ===========================
    # 1) CODE GENERATION
    # ===========================
    def generate_code_task(self, agent):
        return Task(
            description=(
                "You are the Code Generation Agent.\n"
                "Generate the full and complete code solution for the following requirements:\n"
                f"{self.requirements}\n\n"
                "STRICT RULES:\n"
                "• Output MUST be ONLY a single fenced code block.\n"
                "• NO explanations, NO intro text, NO bullet points.\n"
                "• The code must be syntactically correct and runnable.\n"
                "• Prefer minimal dependencies unless explicitly required.\n"
            ),
            agent=agent,
            expected_output="A single valid markdown code block containing complete runnable code.",
            async_execution=False
        )

    # ===========================
    # 2) CODE REVIEW
    # ===========================
    def review_code_task(self, agent, code_context):
        return Task(
            description=(
                "You are the Code Review Agent.\n"
                "Review the code provided in CONTEXT.\n\n"
                "You MUST output in exactly this strict structure:\n\n"
                "### Summary\n"
                "- One short paragraph summarizing the overall quality.\n\n"
                "### Detailed Review\n"
                "- List specific issues and risks.\n"
                "- Mention security concerns.\n"
                "- Mention style or maintainability concerns.\n\n"
                "### Final Recommendations\n"
                "- Bullet list of improvements the next agent must apply.\n\n"
                "DO NOT write code.\n"
                "DO NOT rewrite the solution.\n"
                "DO NOT add extra sections."
            ),
            agent=agent,
            expected_output="A structured markdown review with EXACT 3 sections.",
            context=[code_context],
            async_execution=False
        )

    # ===========================
    # 3) DECISION MAKING (YES/NO)
    # ===========================
    def make_refine_decision_task(self, agent, code_context):
        return Task(
            description=(
                "Analyze ONLY the code in context and answer:\n"
                "Does the code have bugs OR security vulnerabilities OR incorrect behaviour?\n\n"
                "STRICT OUTPUT RULE:\n"
                "Output ONLY ONE WORD: YES or NO.\n"
                "NO punctuation. NO explanation. ONLY the word."
            ),
            agent=agent,
            expected_output="YES or NO",
            context=[code_context],
            async_execution=False
        )

    # ===========================
    # 4) CODE REFINEMENT
    # ===========================
    def refine_code_task(self, agent, code_context, review_context):
        return Task(
            description=(
                "You are the Code Refinement Agent.\n\n"
                "Your job:\n"
                "1. Read the original code.\n"
                "2. Read the review feedback.\n"
                "3. Apply ALL suggested fixes.\n"
                "4. Execute the code using the 'Execute Python Code' tool.\n"
                "5. If execution fails:\n"
                "   - Fix the error\n"
                "   - Re-run\n"
                "   - Repeat up to 3 total attempts.\n\n"
                "STRICT OUTPUT RULE:\n"
                "Output ONLY a single fenced code block containing the FINAL corrected code.\n"
                "NO explanations.\n"
                "NO comments.\n"
            ),
            agent=agent,
            expected_output="Single final corrected code block.",
            context=[code_context, review_context],
            async_execution=False
        )

    # ===========================
    # 5) DOCUMENTATION
    # ===========================
    def document_code_task(self, agent, code_context, review_context):
        return Task(
            description=(
                "You are the Documentation Agent.\n"
                "Write PROFESSIONAL documentation for the FINAL CODE in context.\n"
                "Documentation MUST include:\n"
                "• Overview\n"
                "• Features\n"
                "• Requirements & dependencies\n"
                "• Installation\n"
                "• Usage examples\n"
                "• Explanation of implementation\n"
                "• Known limitations\n"
                "• Future improvements\n\n"
                "Output MUST be clean markdown, no code unless needed."
            ),
            agent=agent,
            expected_output="A polished, professional README.md styled documentation.",
            context=[code_context, review_context],
            async_execution=False
        )
