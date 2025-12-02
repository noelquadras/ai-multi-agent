"use client";

import { useState } from "react";

export default function MultiAgentUI() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  async function runAgents(e) {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirements: prompt }),
      });

      const data = await res.json();
      setResult(data);
    } catch (err) {
      console.error(err);
      alert("Error occurred.");
    }

    setLoading(false);
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">
        AI Multi-Agent Playground
      </h1>

      <form onSubmit={runAgents} className="space-y-4">
        <textarea
          className="w-full p-4 border rounded-lg"
          rows={6}
          placeholder="Write your task here..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />

        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded"
        >
          {loading ? "Running agents..." : "Run Agents"}
        </button>
      </form>

      {result && (
        <div className="mt-6 space-y-6">
          <section>
            <h2 className="font-semibold text-lg">Generated Code</h2>
            <pre className="bg-gray-100 p-4 rounded whitespace-pre-wrap">
              {result.generatedCode}
            </pre>
          </section>

          <section>
            <h2 className="font-semibold text-lg">Review Report</h2>
            <pre className="bg-gray-100 p-4 rounded whitespace-pre-wrap">
              {result.reviewReport}
            </pre>
          </section>

          <section>
            <h2 className="font-semibold text-lg">Documentation</h2>
            <pre className="bg-gray-100 p-4 rounded whitespace-pre-wrap">
              {result.documentation}
            </pre>
          </section>
        </div>
      )}
    </div>
  );
}
