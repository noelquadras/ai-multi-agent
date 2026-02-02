"use client";

import { useEffect, useRef, useState } from "react";
// --- FIX 1: Import useSearchParams from next/navigation ---
import { useSearchParams } from "next/navigation";
import { AgentPanel } from "@/components/workspace/AgentPanel";
import { ActivityPanel, TaskEvent } from "@/components/workspace/ActivityPanel";
import { CodeWorkspace } from "@/components/workspace/CodeWorkspace";
import { PreviewPanel } from "@/components/workspace/PreviewPanel";
import { CLIPanel } from "@/components/workspace/CLIPanel";
// --- Note: Ensure useExecution is used or removed if not needed ---
import { useExecution } from "@/app/context/ExecutionContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  RefreshCw,
  Pause,
  Play,
  Check,
  X,
  Terminal,
  Eye,
  FileText,
} from "lucide-react";

/* =========================
   TYPES
========================= */

interface AgentStatus {
  id: string;
  name: string;
  role: string;
  status: "idle" | "thinking" | "approved" | "error";
  progress: number;
}

interface TaskSnapshot {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  model?: string;
  events: TaskEvent[];
}

interface TaskOutputs {
  code: string;
  review: string;
  decision: string;
  documentation: string;
  testResults: string;
}

type SidePanel = "preview" | "cli" | "docs";

/* =========================
   COMPONENT
========================= */

export default function WorkspacePage() {
  const searchParams = useSearchParams();
  const taskId = searchParams.get("taskId");

  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [taskStatus, setTaskStatus] =
    useState<TaskSnapshot["status"]>("pending");
  const [taskModel, setTaskModel] = useState<string>("ollama");
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [outputs, setOutputs] = useState<TaskOutputs>({
    code: "",
    review: "",
    decision: "",
    documentation: "",
    testResults: "",
  });
  const [cliLogs, setCliLogs] = useState<string[]>([]);
  const [sidePanel, setSidePanel] = useState<SidePanel>("preview");

  const eventSourceRef = useRef<EventSource | null>(null);

  /* =========================
     AGENT REGISTRY
  ========================= */

  const AGENT_REGISTRY: Record<string, AgentStatus> = {
    coder: {
      id: "coder",
      name: "Coder",
      role: "Developer",
      status: "idle",
      progress: 0,
    },
    reviewer: {
      id: "reviewer",
      name: "Reviewer",
      role: "QA Engineer",
      status: "idle",
      progress: 0,
    },
    decision: {
      id: "decision",
      name: "Decision",
      role: "Auditor",
      status: "idle",
      progress: 0,
    },
    refiner: {
      id: "refiner",
      name: "Refiner",
      role: "Refactoring",
      status: "idle",
      progress: 0,
    },
    tester: {
      id: "tester",
      name: "Tester",
      role: "CLI Testing",
      status: "idle",
      progress: 0,
    },
    doc_writer: {
      id: "doc_writer",
      name: "Doc Writer",
      role: "Documentation",
      status: "idle",
      progress: 0,
    },
  };

  /* =========================
     EVENT → STATE UPDATES
  ========================= */

  const applyEvent = (event: TaskEvent) => {
    setAgents((prev) => {
      const map = new Map(prev.map((a) => [a.id, { ...a }]));
      if (event.type === "agent_start" || event.type === "agent_end") {
        const agent = map.get(event.agent);
        if (agent) {
          if (event.type === "agent_start") {
            agent.status = "thinking";
            agent.progress = Math.max(agent.progress, 5);
          } else {
            agent.status = "approved";
            agent.progress = 100;
          }
          map.set(agent.id, agent);
        }
      }
      if (event.type === "tool_error" && event.agent) {
        const agent = map.get(event.agent);
        if (agent) {
          agent.status = "error";
          map.set(agent.id, agent);
        }
      }
      return Array.from(map.values());
    });

    if (event.type === "code_output" && event.code) {
      setOutputs((prev) => ({ ...prev, code: event.code }));
    }
    if (event.type === "review_output" && event.review) {
      setOutputs((prev) => ({ ...prev, review: event.review }));
    }
    if (event.type === "decision_output" && event.decision) {
      setOutputs((prev) => ({ ...prev, decision: event.decision }));
    }
    if (event.type === "doc_output" && event.documentation) {
      setOutputs((prev) => ({ ...prev, documentation: event.documentation }));
    }
    if (event.type === "test_output" && event.results) {
      setOutputs((prev) => ({ ...prev, testResults: event.results }));
    }
    if (event.type === "cli_output" && event.message) {
      setCliLogs((prev) => [...prev, event.message]);
    }

    if (event.type === "task_completed") setTaskStatus("completed");
    if (event.type === "task_paused") setTaskStatus("paused");
    if (event.type === "task_resumed") setTaskStatus("running");
  };

  /* =========================
     SSE SUBSCRIPTION & REFRESH
  ========================= */

  const refreshStatus = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/task/${id}`);
      if (!res.ok) throw new Error("Task not found");
      const data: TaskSnapshot = await res.json();
      setTaskStatus(data.status);
      setTaskModel(data.model || "ollama");
      // Pre-apply historical events to the UI
      if (data.events) {
        data.events.forEach(applyEvent);
      }
    } catch (err) {
      console.error("Failed to fetch task status:", err);
    }
  };

  useEffect(() => {
    if (!taskId) return;

    // Reset state for new task
    setAgents(Object.values(AGENT_REGISTRY));
    setEvents([]);
    setOutputs({
      code: "",
      review: "",
      decision: "",
      documentation: "",
      testResults: "",
    });
    setCliLogs([]);

    // Initial fetch to sync with DB
    refreshStatus(taskId);

    const es = new EventSource(
      `http://localhost:8000/api/task/${taskId}/events`,
    );

    es.onmessage = (e) => {
      const event: TaskEvent = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
      applyEvent(event);
    };

    es.onerror = () => {
      es.close();
    };

    eventSourceRef.current = es;
    return () => es.close();
  }, [taskId]);

  /* =========================
     HUMAN-IN-THE-LOOP ACTIONS
  ========================= */

  const handlePause = async () => {
    if (!taskId) return;
    await fetch(`http://localhost:8000/api/task/${taskId}/pause`, {
      method: "POST",
    });
  };

  const handleResume = async () => {
    if (!taskId) return;
    await fetch(`http://localhost:8000/api/task/${taskId}/resume`, {
      method: "POST",
    });
  };

  const handleApprove = async () => {
    if (!taskId) return;
    await fetch(`http://localhost:8000/api/task/${taskId}/approve`, {
      method: "POST",
    });
  };

  const handleReject = async () => {
    if (!taskId) return;
    await fetch(`http://localhost:8000/api/task/${taskId}/reject`, {
      method: "POST",
    });
  };

  /* =========================
     UI RENDER (NO CHANGES)
  ========================= */

  if (!taskId) {
    return (
      <div className="flex h-screen items-center justify-center text-zinc-500">
        No active task
      </div>
    );
  }

  const getStatusColor = () => {
    switch (taskStatus) {
      case "running":
        return "bg-blue-500/20 text-blue-400";
      case "completed":
        return "bg-green-500/20 text-green-400";
      case "paused":
        return "bg-yellow-500/20 text-yellow-400";
      case "failed":
        return "bg-red-500/20 text-red-400";
      default:
        return "bg-purple-500/20 text-purple-400";
    }
  };

  return (
    <div className="flex h-screen bg-[#050505] overflow-hidden">
      <div className="hidden md:block flex-none">
        <AgentPanel agents={agents} />
      </div>

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="h-14 flex items-center justify-between px-4 border-b border-[#1F1F1F] bg-[#0A0A0A]">
          <div className="flex items-center gap-3">
            <Badge className={getStatusColor()}>
              {taskStatus.toUpperCase()}
            </Badge>
            <Badge
              variant="outline"
              className="border-zinc-700 text-zinc-400 text-xs"
            >
              {taskModel === "groq" ? "🚀 Groq 70B" : "🦙 Ollama Local"}
            </Badge>
          </div>

          <div className="flex items-center gap-2">
            {taskStatus === "running" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePause}
                className="text-yellow-400 hover:text-yellow-300"
              >
                <Pause className="w-4 h-4 mr-1" /> Pause
              </Button>
            )}
            {taskStatus === "paused" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResume}
                className="text-green-400 hover:text-green-300"
              >
                <Play className="w-4 h-4 mr-1" /> Resume
              </Button>
            )}
            <div className="w-px h-6 bg-zinc-700 mx-2" />
            <Button
              variant="ghost"
              size="sm"
              onClick={handleApprove}
              disabled={!outputs.code}
              className="text-green-400 disabled:opacity-50"
            >
              <Check className="w-4 h-4 mr-1" /> Approve
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReject}
              disabled={!outputs.code}
              className="text-red-400 disabled:opacity-50"
            >
              <X className="w-4 h-4 mr-1" /> Reject
            </Button>
            <div className="w-px h-6 bg-zinc-700 mx-2" />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => taskId && refreshStatus(taskId)}
              className="text-zinc-400"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <CodeWorkspace code={outputs.code} isReadOnly />
          </div>

          <div className="hidden xl:flex flex-col border-l border-[#1F1F1F]">
            <div className="flex border-b border-[#1F1F1F] bg-[#0A0A0A]">
              <button
                onClick={() => setSidePanel("preview")}
                className={`flex items-center gap-2 px-4 py-2 text-sm ${sidePanel === "preview" ? "bg-[#141414] text-white border-b-2 border-purple-500" : "text-zinc-500 hover:text-zinc-300"}`}
              >
                <Eye className="w-4 h-4" /> Preview
              </button>
              <button
                onClick={() => setSidePanel("cli")}
                className={`flex items-center gap-2 px-4 py-2 text-sm ${sidePanel === "cli" ? "bg-[#141414] text-white border-b-2 border-green-500" : "text-zinc-500 hover:text-zinc-300"}`}
              >
                <Terminal className="w-4 h-4" /> CLI Tests{" "}
                {cliLogs.length > 0 && (
                  <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                )}
              </button>
              <button
                onClick={() => setSidePanel("docs")}
                className={`flex items-center gap-2 px-4 py-2 text-sm ${sidePanel === "docs" ? "bg-[#141414] text-white border-b-2 border-blue-500" : "text-zinc-500 hover:text-zinc-300"}`}
              >
                <FileText className="w-4 h-4" /> Docs
              </button>
            </div>

            <div className="flex-1 overflow-hidden">
              {sidePanel === "preview" && (
                <PreviewPanel
                  taskStatus={{
                    status: taskStatus,
                    result: {
                      refined_code: outputs.code,
                      generated_code: outputs.code,
                      documentation: outputs.documentation,
                      review_report: outputs.review,
                    },
                  }}
                />
              )}
              {sidePanel === "cli" && (
                <CLIPanel logs={cliLogs} testResults={outputs.testResults} />
              )}
              {sidePanel === "docs" && (
                <div className="w-[400px] h-full bg-[#0A0A0A] p-4 overflow-auto">
                  <h3 className="text-sm font-semibold text-zinc-300 mb-4">
                    Generated Documentation
                  </h3>
                  {outputs.documentation ? (
                    <div className="prose prose-invert prose-sm max-w-none">
                      <pre className="whitespace-pre-wrap text-xs text-zinc-400 font-mono">
                        {outputs.documentation}
                      </pre>
                    </div>
                  ) : (
                    <p className="text-zinc-500 text-sm">
                      Documentation will appear here once generated.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="h-72 border-t border-[#1F1F1F] overflow-hidden">
          <ActivityPanel events={events} />
        </div>
      </div>
    </div>
  );
}
