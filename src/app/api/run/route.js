import { NextResponse } from "next/server";
import { 
  agent1_generateCode, 
  agent2_reviewCode, 
  agent3_documentCode 
} from "../../../lib/agents";

export async function POST(req) {
  try {
    const { requirements, model } = await req.json();

    // Validate input
    if (!requirements) {
      return NextResponse.json(
        { success: false, error: "requirements is required" },
        { status: 400 }
      );
    }

    if (!model) {
      return NextResponse.json(
        { success: false, error: "model is required" },
        { status: 400 }
      );
    }

    // Agent 1 — generate code
    const generatedCode = await agent1_generateCode(requirements, model);

    // Agent 2 — review code
    const reviewReport = await agent2_reviewCode(generatedCode, model);

    // Agent 3 — write documentation
    const documentation = await agent3_documentCode(generatedCode, reviewReport, model);

    // Return results
    return NextResponse.json({
      success: true,
      generatedCode,
      reviewReport,
      documentation
    });

  } catch (error) {
    console.error("Error in /api/run:", error);
    return NextResponse.json(
      { success: false, error: error.message || "Something went wrong." },
      { status: 500 }
    );
  }
}
