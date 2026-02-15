"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AgentPanel } from "@/components/workspace/AgentPanel";
import { ActivityPanel, TaskEvent } from "@/components/workspace/ActivityPanel";
import { CodeWorkspace } from "@/components/workspace/CodeWorkspace";
import { CLIPanel } from "@/components/workspace/CLIPanel";
import { RejectModal } from "@/components/workspace/RejectModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import dynamic from "next/dynamic";

const TerminalComponent = dynamic(
  () => import("@/components/Terminal").then((mod) => mod.Terminal),
  { ssr: false }
);
import {
  RefreshCw,
  Pause,
  Play,
  Check,
  X,
  Terminal,
  FileText,
  History,
} from "lucide-react";
import { HistorySidebar } from "@/components/HistorySidebar";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"

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

type SidePanel = "cli" | "docs" | "terminal";

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
  const [sidePanel, setSidePanel] = useState<SidePanel>("cli");
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);


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

  const handleReject = async (feedback: string) => {
    if (!taskId) return;
    await fetch(`http://localhost:8000/api/task/${taskId}/reject`, {
      method: "POST",
    });

    // Call regenerate endpoint which creates a new task with feedback
    const response = await fetch(`http://localhost:8000/api/task/${taskId}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback }),
    });

    if (response.ok) {
      const data = await response.json();
      // Redirect to the new task
      window.location.href = `/workspace?taskId=${data.task_id}`;
    }
  };

  /* =========================
     UI RENDER
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
    <SidebarProvider>
      <HistorySidebar />
      <SidebarInset>
        <div className="flex h-screen bg-background overflow-hidden">
          <div className="hidden md:block flex-none">
            <AgentPanel agents={agents} />
          </div>

          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="h-14 flex items-center justify-between px-4 border-b border-border bg-card">
              <div className="flex items-center gap-3">
                <SidebarTrigger />
                <Badge className={getStatusColor()}>
                  {taskStatus.toUpperCase()}
                </Badge>
                <Badge
                  variant="outline"
                  className="border-border text-muted-foreground text-xs"
                >
                  {taskModel === "groq" ? "🚀 Groq 70B" : "🦙 Ollama Local"}
                </Badge>
              </div>

              <div className="flex items-center gap-2">
                {(taskStatus === "running" || taskStatus === "pending") && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handlePause}
                    className="text-yellow-500 hover:text-yellow-600"
                  >
                    <Pause className="w-4 h-4 mr-1" /> Pause
                  </Button>
                )}
                {taskStatus === "paused" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleResume}
                    className="text-green-500 hover:text-green-600"
                  >
                    <Play className="w-4 h-4 mr-1" /> Resume
                  </Button>
                )}
                <div className="w-px h-6 bg-border mx-2" />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleApprove}
                  disabled={!outputs.code}
                  className="text-green-500 disabled:opacity-50"
                >
                  <Check className="w-4 h-4 mr-1" /> Approve
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsRejectModalOpen(true)}
                  disabled={!outputs.code}
                  className="text-red-500 disabled:opacity-50"
                >
                  <X className="w-4 h-4 mr-1" /> Reject
                </Button>
                <div className="w-px h-6 bg-border mx-2" />

                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => taskId && refreshStatus(taskId)}
                  className="text-muted-foreground"
                >
                  <RefreshCw className="w-4 h-4" />
                </Button>
              </div>
            </div>

            <div className="flex flex-1 overflow-hidden">
              <div className="flex-1 overflow-hidden">
                <CodeWorkspace code={outputs.code} isReadOnly />
              </div>

              <div className="hidden xl:flex flex-col border-l border-border">
                <div className="flex border-b border-border bg-card">
                  <button
                    onClick={() => setSidePanel("cli")}
                    className={`flex items-center gap-2 px-4 py-2 text-sm ${sidePanel === "cli"
                      ? "bg-muted text-foreground border-b-2 border-green-500"
                      : "text-muted-foreground hover:text-foreground"
                      }`}
                  >
                    <Terminal className="w-4 h-4" /> CLI Tests
                    {cliLogs.length > 0 && (
                      <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                    )}
                  </button>
                  <button
                    onClick={() => setSidePanel("terminal")}
                    className={`flex items-center gap-2 px-4 py-2 text-sm ${sidePanel === "terminal"
                      ? "bg-muted text-foreground border-b-2 border-green-500"
                      : "text-muted-foreground hover:text-foreground"
                      }`}
                  >
                    <Terminal className="w-4 h-4" /> Terminal
                  </button>
                  <button
                    onClick={() => setSidePanel("docs")}
                    className={`flex items-center gap-2 px-4 py-2 text-sm ${sidePanel === "docs"
                      ? "bg-muted text-foreground border-b-2 border-blue-500"
                      : "text-muted-foreground hover:text-foreground"
                      }`}
                  >
                    <FileText className="w-4 h-4" /> Docs
                  </button>
                </div>

                <div className="flex-1 overflow-hidden">
                  {sidePanel === "cli" && (
                    <CLIPanel logs={cliLogs} testResults={outputs.testResults} />
                  )}
                  {sidePanel === "terminal" && (
                    <div className="h-full w-full bg-[#1a1b26]">
                      <TerminalComponent className="h-full w-full" />
                    </div>
                  )}
                  {sidePanel === "docs" && (
                    <div className="w-[400px] h-full bg-card p-4 overflow-auto">
                      <h3 className="text-sm font-semibold text-foreground mb-4">
                        Generated Documentation
                      </h3>
                      {outputs.documentation ? (
                        <div className="prose prose-sm max-w-none">
                          <pre className="whitespace-pre-wrap text-xs text-muted-foreground font-mono">
                            {outputs.documentation}
                          </pre>
                        </div>
                      ) : (
                        <p className="text-muted-foreground text-sm">
                          Documentation will appear here once generated.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="h-72 border-t border-border overflow-hidden">
              <ActivityPanel events={events} />
            </div>
          </div>
        </div>
      </SidebarInset>
      <RejectModal
        isOpen={isRejectModalOpen}
        onClose={() => setIsRejectModalOpen(false)}
        onSubmit={handleReject}
      />
    </SidebarProvider>
  );
}

