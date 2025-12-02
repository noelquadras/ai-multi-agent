// lib/orchestrator.js
import {
  agent1_generateCode,
  agent2_reviewCode,
  agent3_documentCode
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


export async function runMultiAgentFlow(requirements) {
  console.log("Starting Multi-Agent Flow...");
  
  // 1. Code Generation
  console.log("Agent 1: Generating Code...");
  const rawCode = await agent1_generateCode(requirements);
  const code = cleanAgentOutput(rawCode); // Clean the output

  // 2. Code Review
  console.log("Agent 2: Reviewing Code...");
  const rawReview = await agent2_reviewCode(code);
  const review = cleanAgentOutput(rawReview); // Clean the output

  // 3. Documentation
  console.log("Agent 3: Documenting Code...");
  const rawDocs = await agent3_documentCode(code, review);
  const docs = cleanAgentOutput(rawDocs); // Clean the output

  console.log("Multi-Agent Flow Complete.");
  return { code, review, docs };
}