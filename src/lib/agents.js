// lib/agents.js

import OpenAI from "openai";
import {
  CODE_GENERATOR_PROMPT,
  CODE_REVIEWER_PROMPT,
  DOCUMENTATION_PROMPT
} from "./agentPrompts";

// --- OLLAMA CLIENT ---
const client = new OpenAI({
  apiKey: "ollama-local",             // placeholder, not required by Ollama
  baseURL: "http://localhost:11434/v1", // Ollama OpenAI-compatible API
});

// Helper to inject template variables
function fill(template, data) {
  return template.replace(/{{(.*?)}}/g, (_, key) => data[key.trim()]);
}

// Local model
const MODEL = "mistral:7b-instruct";

// ---- Utility: Clean code fences ----
function cleanCodeBlocks(text) {
  if (!text) return "";
  return text
    .replace(/```[\s\S]*?```/g, (match) =>
      match
        .replace(/```[a-zA-Z]*/g, "") // remove ```jsx or ```js
        .replace(/```/g, "")
    )
    .trim();
}

// -----------------------------------------------------------------------------
// Agent 1 — Code Generator
// -----------------------------------------------------------------------------
export async function agent1_generateCode(requirements) {
  const prompt = fill(CODE_GENERATOR_PROMPT, { USER_REQUIREMENTS: requirements });

  try {
    const res = await client.chat.completions.create({
      model: MODEL,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.2,
      max_tokens: 1200,
    });

    let output = res.choices?.[0]?.message?.content || "";
    return cleanCodeBlocks(output);

  } catch (err) {
    console.error("Agent 1 Error:", err);
    throw new Error("Code generation failed");
  }
}

// -----------------------------------------------------------------------------
// Agent 2 — Code Reviewer
// -----------------------------------------------------------------------------
export async function agent2_reviewCode(generatedCode) {
  const cleaned = cleanCodeBlocks(generatedCode);
  const prompt = fill(CODE_REVIEWER_PROMPT, { GENERATED_CODE: cleaned });

  try {
    const res = await client.chat.completions.create({
      model: MODEL,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.0,
      max_tokens: 800,
    });

    return res.choices?.[0]?.message?.content || "";

  } catch (err) {
    console.error("Agent 2 Error:", err);
    throw new Error("Code review failed");
  }
}

// -----------------------------------------------------------------------------
// Agent 3 — Documentation Writer
// -----------------------------------------------------------------------------
export async function agent3_documentCode(generatedCode, reviewReport) {
  const cleaned = cleanCodeBlocks(generatedCode);

  const prompt = fill(DOCUMENTATION_PROMPT, {
    GENERATED_CODE: cleaned,
    REVIEW_REPORT: reviewReport,
  });

  try {
    const res = await client.chat.completions.create({
      model: MODEL,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.4,
      max_tokens: 1200,
    });

    return res.choices?.[0]?.message?.content || "";

  } catch (err) {
    console.error("Agent 3 Error:", err);
    throw new Error("Documentation generation failed");
  }
}
