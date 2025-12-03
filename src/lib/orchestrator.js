// lib/orchestrator.js
import {
  agent1_generateCode,
  agent2_reviewCode,
  agent3_documentCode,
  // *** NEW IMPORT ***
  agent4_refineCode 
} from "./agents";

/**
 * Helper function to clean conversational filler from the LLM output.
 * It specifically targets and removes the content enclosed in <think> tags.
 * @param {string} text The raw text output from the LLM.
 * @returns {string} The cleaned text.
 */
function cleanAgentOutput(text) {
  // Regex to match and remove everything from <think> to </think> globally (dotall mode 's').
  const thinkRegex = /<think>.*?<\/think>\n?/gs;
  
  // 1. Remove the think block
  let cleanedText = text.replace(thinkRegex, '').trim();
  
  // 2. Return the cleaned and trimmed text
  return cleanedText;
}


export async function runMultiAgentFlow(requirements, options = {}) {
  console.log("Starting Multi-Agent Flow with Refinement...");
  
  // --- 1. Code Generation ---
  console.log("Agent 1: Generating Code...");
  const rawCode = await agent1_generateCode(requirements, options);
  const code = cleanAgentOutput(rawCode); 

  // --- 2. Code Review ---
  console.log("Agent 2: Reviewing Code...");
  const rawReview = await agent2_reviewCode(code, options);
  const review = cleanAgentOutput(rawReview);
  
  // --- 3. Code Refinement (NEW STEP) ---
  console.log("Agent 4: Refining Code based on Review...");
  
  // Check if the review suggests critical changes that need refinement
  let refinedCode;
  if (review.includes("Bugs/Issues") || review.includes("Security Flaws") || review.includes("Improvements")) {
	
	// If the review has findings, call the refiner
    const rawRefinedCode = await agent4_refineCode(code, review, options);
    refinedCode = cleanAgentOutput(rawRefinedCode);
  } else {
	// If the review is clean, use the original code
	refinedCode = code;
}
  
  // --- 4. Documentation ---
  console.log("Agent 3: Documenting Final Code...");
  // Use the REFINED code for documentation!
  const rawDocs = await agent3_documentCode(refinedCode, review, options); 
  const docs = cleanAgentOutput(rawDocs); 

  console.log("Multi-Agent Flow Complete.");
  return { 
	generatedCode: code, // Original Code
	reviewReport: review, // Original Review
	refinedCode: refinedCode, // Final, Improved Code
	documentation: docs // Documentation for the Refined Code
};
}