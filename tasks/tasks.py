# tasks/tasks.py
from crewai import Task

class SoftwareTasks:
    def __init__(self, requirements):
        self.requirements = requirements

    def generate_code_task(self, agent):
        return Task(
            description=f"Generate the full code solution for the following requirements: {self.requirements}. "
                        "The output MUST be a complete code block, nothing else.",
            agent=agent,
            expected_output="A single markdown code block containing the complete, runnable code.",
        )

    def review_code_task(self, agent, code_context):
        return Task(
            description=(
                f"Review the code provided in the context for security, bugs, and style. The output MUST follow the "
                f"STRICT OUTPUT FORMAT for Code Reviewers (Summary, Detailed Review, Final Recommendations)."
            ),
            agent=agent,
            expected_output="A structured review report in markdown format.",
            context=[code_context],
            # CHANGE: Set to False to allow Streamlit to capture the logs live
            async_execution=False 
        )

    def make_refine_decision_task(self, agent, code_context):
        return Task(
            description=(
                f"Analyze the code provided in the context. Decide if the code needs revision/refinement due to bugs or security flaws. "
                f"Your final answer MUST be ONLY one word: 'YES' or 'NO'."
            ),
            agent=agent,
            expected_output="A single word: 'YES' or 'NO'.",
            context=[code_context],
            # CHANGE: Set to False to allow Streamlit to capture the logs live
            async_execution=False 
        )

    def refine_code_task(self, agent, code_context, review_context):
        return Task(
            description=(
                "Based on the original code and the review report (available in context), "
                "rewrite the code to implement all necessary fixes and improvements. "
                "The output MUST be ONLY the fixed code block."
            ),
            agent=agent,
            expected_output="The full, corrected, and refined code solution.",
            context=[code_context, review_context],
            async_execution=False
        )

    def document_code_task(self, agent, code_context, review_context):
        return Task(
            description=(
                "Generate the final, professional documentation (including README sections) "
                "for the LATEST version of the code (provided in context)."
            ),
            agent=agent,
            expected_output="A complete, professional documentation file in markdown.",
            context=[code_context, review_context]
        )