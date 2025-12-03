import { 
  agent1_generateCode, 
  agent2_reviewCode, 
  agent3_documentCode,
  // *** NEW IMPORT ***
  agent4_refineCode 
} from "../../../../lib/agents";

export async function POST(req) {
  try {
    const body = await req.json();
    const { requirements, model, temperature, max_tokens } = body ?? {};

    if (!requirements) {
      return new Response(JSON.stringify({ error: "requirements is required" }), { status: 400 });
    }
    if (!model) {
      return new Response(JSON.stringify({ error: "model is required" }), { status: 400 });
    }

    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        // Helper: push an event as a JSON line
        function pushEvent(obj) {
          controller.enqueue(encoder.encode(JSON.stringify(obj) + "\n"));
        }

        // Helper: chunk text into progressive slices to simulate token streaming
        function chunkText(text, size = 120) {
          const chunks = [];
          for (let i = 0; i < text.length; i += size) {
            chunks.push(text.slice(i, i + size));
          }
          return chunks;
        }

        const options = {
          model,
          temperature: typeof temperature === "number" ? temperature : undefined,
          max_tokens: typeof max_tokens === "number" ? max_tokens : undefined,
        };

        // --- AGENT 1: GENERATE CODE ---
        pushEvent({ type: "agent_start", agent: "generator" });

        let genText;
        try {
          genText = await agent1_generateCode(requirements, options);
        } catch (err) {
          pushEvent({ type: "agent_error", agent: "generator", message: String(err) });
          controller.close();
          return;
        }

        // Stream generator output (original code)
        const genChunks = chunkText(genText, 120);
        for (const chunk of genChunks) {
          pushEvent({ type: "agent_chunk", agent: "generator", data: chunk });
          await new Promise((r) => setTimeout(r, 40));
        }
        pushEvent({ type: "agent_done", agent: "generator" });


        // --- AGENT 2: REVIEW CODE ---
        pushEvent({ type: "agent_start", agent: "reviewer" });

        let reviewText;
        try {
          reviewText = await agent2_reviewCode(genText, options);
        } catch (err) {
          pushEvent({ type: "agent_error", agent: "reviewer", message: String(err) });
          controller.close();
          return;
        }

        // Stream reviewer output
        const reviewChunks = chunkText(reviewText, 160);
        for (const chunk of reviewChunks) {
          pushEvent({ type: "agent_chunk", agent: "reviewer", data: chunk });
          await new Promise((r) => setTimeout(r, 40));
        }
        pushEvent({ type: "agent_done", agent: "reviewer" });
        
        
        // --- AGENT 4: REFINE CODE (NEW STEP) ---
        pushEvent({ type: "agent_start", agent: "refiner" }); 

        let refinedText;
        try {
          // Agent 4 takes the original code and the review report
          refinedText = await agent4_refineCode(genText, reviewText, options); 
        } catch (err) {
          pushEvent({ type: "agent_error", agent: "refiner", message: String(err) });
          controller.close();
          return;
        }

        // Stream refiner output
        const refinedChunks = chunkText(refinedText, 120);
        for (const chunk of refinedChunks) {
          // Note: Streaming refined code to the 'out-code' area will overwrite the original code
          pushEvent({ type: "agent_chunk", agent: "generator", data: chunk }); 
          await new Promise((r) => setTimeout(r, 40));
        }
        pushEvent({ type: "agent_done", agent: "refiner" });
        

        // --- AGENT 3: DOCUMENTATION ---
        pushEvent({ type: "agent_start", agent: "documenter" });

        let docText;
        try {
          // Agent 3 takes the REFINED code for documentation
          docText = await agent3_documentCode(refinedText, reviewText, options);
        } catch (err) {
          pushEvent({ type: "agent_error", agent: "documenter", message: String(err) });
          controller.close();
          return;
        }

        const docChunks = chunkText(docText, 160);
        for (const chunk of docChunks) {
          pushEvent({ type: "agent_chunk", agent: "documenter", data: chunk });
          await new Promise((r) => setTimeout(r, 40));
        }
        pushEvent({ type: "agent_done", agent: "documenter" });

        // final combined done event
        pushEvent({
          type: "complete",
          generatedCode: genText, // Original (for reference)
          reviewReport: reviewText,
          refinedCode: refinedText, // Final, fixed code
          documentation: docText,
        });

        controller.close();
      },
      cancel() {
        // nothing for now
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
      },
    });
  } catch (err) {
    console.error("Stream route error:", err);
    return new Response(JSON.stringify({ error: err.message || String(err) }), { status: 500 });
  }
}