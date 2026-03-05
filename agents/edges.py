"""
DEPRECATED: Conditional edge functions for the LangGraph agent workflow.

These functions have been absorbed into the respective agent nodes as part
of the Pub-Sub architecture refactoring:
  - should_refine          → decision_maker.py (emits DECISION_REFINE or DECISION_APPROVED)
  - should_refine_after_analysis → terminal_analyzer.py (emits ANALYSIS_PASS/FIX/REGENERATE)

This file is kept for reference only. Do not import from this module.
"""
