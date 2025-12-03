// public/app.js

function appendLog(text) {
  const el = document.getElementById("logs");
  el.textContent += text + "\n";
  el.scrollTop = el.scrollHeight;
}

function appendToOutput(id, text) {
  const el = document.getElementById(id);
  el.textContent += text;
  el.scrollTop = el.scrollHeight;
}

document.getElementById("promptForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  // reset UI
  document.getElementById("logs").textContent = "";
  document.getElementById("out-code").textContent = ""; // Now used for FINAL code
  document.getElementById("out-review").textContent = "";
  document.getElementById("out-docs").textContent = "";

  const prompt = document.getElementById("prompt").value;
  const model = document.getElementById("model").value;
  const temperature = parseFloat(document.getElementById("temperature").value);
  const max_tokens = parseInt(document.getElementById("max_tokens").value, 10);

  appendLog(`Sending prompt → model: ${model}, temp: ${temperature}, max_tokens: ${max_tokens}`);
  document.getElementById("runBtn").disabled = true;

  try {
    const res = await fetch("/api/run/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requirements: prompt, model, temperature, max_tokens }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: "Unknown error" }));
      appendLog("Server error: " + (err.error || JSON.stringify(err)));
      document.getElementById("runBtn").disabled = false;
      return;
    }

    // streaming reader
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let isRefining = false; // New flag to track when the refiner starts

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // lines are JSON objects separated by newline
      let lines = buf.split("\n");
      // keep last partial line
      buf = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        let obj;
        try {
          obj = JSON.parse(line);
        } catch (err) {
          appendLog("parse error: " + line);
          continue;
        }

        // handle events
        if (obj.type === "agent_start") {
          appendLog(`[${obj.agent}] started`);
          if (obj.agent === "refiner") {
            isRefining = true;
            // Clear the code box when refiner starts, as it will replace the content
            document.getElementById("out-code").textContent = "";
          }
        } else if (obj.type === "agent_chunk") {
          // append chunk to proper area
          if (obj.agent === "generator" && !isRefining) {
            // Stream original code only if refiner hasn't started
            appendToOutput("out-code", obj.data); 
          } else if (obj.agent === "refiner") {
            // Stream refined code to the same box
            appendToOutput("out-code", obj.data); 
          } else if (obj.agent === "reviewer") {
            appendToOutput("out-review", obj.data);
          } else if (obj.agent === "documenter") {
            appendToOutput("out-docs", obj.data);
          }
        } else if (obj.type === "agent_done") {
          appendLog(`[${obj.agent}] done`);
        } else if (obj.type === "agent_error") {
          appendLog(`[${obj.agent}] ERROR: ${obj.message}`);
        } else if (obj.type === "complete") {
          appendLog("All agents finished — final results attached.");
          // Use the final payload to ensure content completeness
          if (obj.refinedCode) { // Check for the new refinedCode property
            document.getElementById("out-code").textContent = obj.refinedCode;
            document.getElementById("out-review").textContent = obj.reviewReport;
            document.getElementById("out-docs").textContent = obj.documentation;
          } else if (obj.generatedCode) {
                // Fallback for non-refinement run
                document.getElementById("out-code").textContent = obj.generatedCode;
                document.getElementById("out-review").textContent = obj.reviewReport;
                document.getElementById("out-docs").textContent = obj.documentation;
            }
        } else {
          appendLog("unknown event: " + JSON.stringify(obj));
        }
      }
    }

    appendLog("Stream finished");
  } catch (err) {
    appendLog("Network/stream error: " + String(err));
  } finally {
    document.getElementById("runBtn").disabled = false;
  }
});