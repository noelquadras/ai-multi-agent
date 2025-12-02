// src/app/api/run/route.js
import { NextResponse } from "next/server";
import { agent1_generateCode, agent2_reviewCode, agent3_documentCode } from "../../../lib/agents";


export async function POST(req) {
  try {
    // Parse incoming JSON
    const { requirements } = await req.json();

    if (!requirements) {
      return NextResponse.json(
        { success: false, error: "Missing 'requirements' in request body." },
        { status: 400 }
      );
    }

    // Agent 1: Generate code
    const generatedCode = await agent1_generateCode(requirements);

    // Agent 2: Review the code
    const reviewReport = await agent2_reviewCode(generatedCode);

    // Agent 3: Generate documentation
    const documentation = await agent3_documentCode(generatedCode, reviewReport);

    // Return all results
    return NextResponse.json({
      success: true,
      generatedCode,
      reviewReport,
      documentation,
    });
  } catch (error) {
    console.error("Error in /api/run:", error);
    return NextResponse.json(
      { success: false, error: error.message || "Something went wrong." },
      { status: 500 }
    );
  }
}
