// lib/agents.js

import OpenAI from "openai";
import {
  CODE_GENERATOR_PROMPT,
  CODE_REVIEWER_PROMPT,
  DOCUMENTATION_PROMPT
} from "./agentPrompts";

// Ollama/OpenAI-compatible client
const client = new OpenAI({
  apiKey: "ollama-local",
  baseURL: "http://localhost:11434/v1",
});

// Helper to inject template variables
function fill(template, data) {
  return template.replace(/{{(.*?)}}/g, (_, key) => data[key.trim()]);
}

// Remove markdown code fences
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

// Default model (fallback)
const DEFAULT_MODEL = "mistral:7b-instruct";

// Utility to call the chat completion
async function callModel({ model, messages, temperature = 0.2, max_tokens = 1000 }) {
  const usedModel = model || DEFAULT_MODEL;

  const res = await client.chat.completions.create({
    model: usedModel,
    messages,
    temperature,
    max_tokens,
  });

  const text = res.choices?.[0]?.message?.content ?? "";
  return text;
}

// Agent 1 — Code Generator
export async function agent1_generateCode(requirements, options = {}) {
  const prompt = fill(CODE_GENERATOR_PROMPT, { USER_REQUIREMENTS: requirements });
  try {
    const raw = await callModel({
      model: options.model,
      messages: [{ role: "user", content: prompt }],
      temperature: options.temperature ?? 0.2,
      max_tokens: options.max_tokens ?? 1200,
    });
    return cleanCodeBlocks(raw);
  } catch (err) {
    console.error("agent1_generateCode error:", err);
    throw err;
  }
}

// Agent 2 — Code Reviewer
export async function agent2_reviewCode(generatedCode, options = {}) {
  const prompt = fill(CODE_REVIEWER_PROMPT, { GENERATED_CODE: generatedCode });
  try {
    const raw = await callModel({
      model: options.model,
      messages: [{ role: "user", content: prompt }],
      temperature: options.temperature ?? 0.0,
      max_tokens: options.max_tokens ?? 800,
    });
    return raw;
  } catch (err) {
    console.error("agent2_reviewCode error:", err);
    throw err;
  }
}

// Agent 3 — Documentation Writer
export async function agent3_documentCode(generatedCode, reviewReport, options = {}) {
  const prompt = fill(DOCUMENTATION_PROMPT, {
    GENERATED_CODE: generatedCode,
    REVIEW_REPORT: reviewReport,
  });
  try {
    const raw = await callModel({
      model: options.model,
      messages: [{ role: "user", content: prompt }],
      temperature: options.temperature ?? 0.4,
      max_tokens: options.max_tokens ?? 1000,
    });
    return raw;
  } catch (err) {
    console.error("agent3_documentCode error:", err);
    throw err;
  }
}
