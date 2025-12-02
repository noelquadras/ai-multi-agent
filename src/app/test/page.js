"use client";

import { useState } from "react";

export default function MultiAgentUI() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [activeTab, setActiveTab] = useState("code");
  const [model, setModel] = useState("mistral:7b-instruct");

  async function runAgents(e) {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        requirements: prompt,
        model,
      }),
    });

    const data = await res.json();
    setResult(data);
    setLoading(false);
  }

  function copy(text) {
    navigator.clipboard.writeText(text);
    alert("Copied!");
  }

  return (
    <div className="p-6 max-w-3xl mx-auto text-gray-900 dark:text-gray-100">

      <h1 className="text-3xl font-bold mb-6">AI Multi-Agent Workspace</h1>

      {/* Input section */}
      <form onSubmit={runAgents} className="space-y-4 mb-6">
        
        {/* Model Selector */}
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="p-2 border rounded bg-white dark:bg-gray-800"
        >
          <option value="mistral:7b-instruct">Mistral 7B</option>
          <option value="llama3:8b">Llama 3 (8B)</option>
          <option value="gemma2:9b">Gemma 2 (9B)</option>
        </select>

        <textarea
          className="w-full p-4 border rounded bg-white dark:bg-gray-800"
          rows={6}
          placeholder="Describe your task..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          {loading ? "Running Agents..." : "Run"}
        </button>

      </form>

      {/* Tabs */}
      {result && (
        <div>
          <div className="flex gap-4 mb-4 border-b pb-2">
            <button onClick={() => setActiveTab("code")} className={activeTab === "code" ? "font-bold" : ""}>Code</button>
            <button onClick={() => setActiveTab("review")} className={activeTab === "review" ? "font-bold" : ""}>Review</button>
            <button onClick={() => setActiveTab("docs")} className={activeTab === "docs" ? "font-bold" : ""}>Documentation</button>
          </div>

          {/* Tab Panels */}
          {activeTab === "code" && (
            <section>
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold">Generated Code</h2>
                <button onClick={() => copy(result.generatedCode)}>Copy</button>
              </div>
              <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded mt-2 whitespace-pre-wrap">
                {result.generatedCode}
              </pre>
            </section>
          )}

          {activeTab === "review" && (
            <section>
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold">Code Review</h2>
                <button onClick={() => copy(result.reviewReport)}>Copy</button>
              </div>
              <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded mt-2 whitespace-pre-wrap">
                {result.reviewReport}
              </pre>
            </section>
          )}

          {activeTab === "docs" && (
            <section>
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold">Documentation</h2>
                <button onClick={() => copy(result.documentation)}>Copy</button>
              </div>
              <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded mt-2 whitespace-pre-wrap">
                {result.documentation}
              </pre>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
