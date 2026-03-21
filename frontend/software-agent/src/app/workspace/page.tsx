"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ActivityPanel, TaskEvent } from "@/components/workspace/ActivityPanel";
import { CodeWorkspace } from "@/components/workspace/CodeWorkspace";
import { CLIPanel } from "@/components/workspace/CLIPanel";
import { RejectModal } from "@/components/workspace/RejectModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import dynamic from "next/dynamic";
import { ChatPanel } from "@/components/workspace/ChatPanel";
import { useTerminalCommands } from "@/hooks/useTerminalCommands";

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
  Activity,
  StopCircle,
  Loader2,
  ExternalLink,
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
  status: "idle" | "running" | "completed" | "error" | "stopped";
  progress: number;
}

interface TaskSnapshot {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed" | "paused" | "cancelled";
  model?: string;
  prompt?: string;
  created_at?: string;
  events: TaskEvent[];
}

interface TaskOutputs {
  code: string;
  review: string;
  testResults: string;
}


interface CodeFile {
  filename: string;
  content: string;
}

type SidePanel = "cli" | "terminal";

/* =========================
   COMPONENTS
========================= */

function WorkspaceContent() {
  const searchParams = useSearchParams();
  const taskId = searchParams.get("taskId");

  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [taskStatus, setTaskStatus] =
    useState<TaskSnapshot["status"]>("pending");
  const [taskModel, setTaskModel] = useState<string>("");
  const [taskPrompt, setTaskPrompt] = useState<string>("");
  const [taskCreatedAt, setTaskCreatedAt] = useState<string>("");
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [outputs, setOutputs] = useState<TaskOutputs>({
    code: "",
    review: "",
    testResults: "",
  });
  const [cliLogs, setCliLogs] = useState<string[]>([]);
  const [codeFiles, setCodeFiles] = useState<CodeFile[]>([]);
  const [specFile, setSpecFile] = useState<CodeFile | null>(null);
  const [reviewFile, setReviewFile] = useState<CodeFile | null>(null);
  const [streamingFile, setStreamingFile] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [rightActiveTab, setRightActiveTab] = useState<"activity" | "cli">("activity");
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);

  // Terminal pop out state
  const [isTerminalPoppedOut, setIsTerminalPoppedOut] = useState(false);
  const terminalWindowRef = useRef<Window | null>(null);

  const handlePopOutTerminal = () => {
    if (terminalWindowRef.current && !terminalWindowRef.current.closed) {
      terminalWindowRef.current.focus();
      return;
    }

    const win = window.open(
      "/terminal",
      "Terminal",
      "width=1000,height=700,menubar=no,toolbar=no,location=no,status=no"
    );
    if (!win) {
      alert("Please allow popups to pop out the terminal.");
      return;
    }
    
    terminalWindowRef.current = win;
    setIsTerminalPoppedOut(true);

    const checkInterval = setInterval(() => {
      if (win.closed) {
        clearInterval(checkInterval);
        setIsTerminalPoppedOut(false);
        terminalWindowRef.current = null;
      }
    }, 1000);
  };

  // Structured command events from the terminal WebSocket
  const { commands: terminalCommands } = useTerminalCommands();

  const eventSourceRef = useRef<EventSource | null>(null);

  /* =========================
     AGENT REGISTRY
  ========================= */

  const AGENT_REGISTRY: Record<string, AgentStatus> = {
    supervisor: {
      id: "supervisor",
      name: "Supervisor",
      role: "Manager",
      status: "idle",
      progress: 0,
    },
    spec_writer: {
      id: "spec_writer",
      name: "Spec Writer",
      role: "Architect",
      status: "idle",
      progress: 0,
    },
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
    analyzer: {
      id: "analyzer",
      name: "Analyzer",
      role: "Terminal Analysis",
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
            agent.status = "running";
            agent.progress = Math.max(agent.progress, 5);
          } else {
            agent.status = "completed";
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
      setStreamingFile(null);
      setStreamingContent("");
      // Add the new version to the codeFiles list
      const filename = (event as any).filename || "code.py";
      setCodeFiles((prev) => {
        // Avoid duplicates
        if (prev.some((f) => f.filename === filename)) return prev;
        return [...prev, { filename, content: event.code }];
      });
      setRightActiveTab("activity");
    }
    if (event.type === "review_output" && event.review) {
      setOutputs((prev) => ({ ...prev, review: event.review }));
      setReviewFile({ filename: "review.md", content: event.review });
      setStreamingFile(null);
      setStreamingContent("");
      setRightActiveTab("activity");
    }
    if (event.type === "spec_output" && event.spec) {
      setSpecFile({ filename: "spec.md", content: event.spec });
      setStreamingFile(null);
      setStreamingContent("");
      setRightActiveTab("activity");
    }

    // ── Streaming events ────────────────────────────────────────
    if (event.type === "spec_stream") {
      if (event.done) {
        // Stream ended — final spec_output event will commit the file
      } else {
        setStreamingFile((prev) => {
          if (prev !== "spec.md") setStreamingContent("");
          return "spec.md";
        });
        setStreamingContent((prev) => prev + (event.chunk || ""));
      }
    }
    if (event.type === "code_stream") {
      if (event.done) {
        setStreamingFile(null);
        setStreamingContent("");
      } else {
        setStreamingFile((prev) => {
          if (prev !== "generating...") setStreamingContent("");
          return "generating...";
        });
        setStreamingContent((prev) => prev + (event.chunk || ""));
      }
    }
    if (event.type === "review_stream") {
      if (event.done) {
        // Stream ended — final review_output event will commit the file
      } else {
        setStreamingFile((prev) => {
          if (prev !== "review.md") setStreamingContent("");
          return "review.md";
        });
        setStreamingContent((prev) => prev + (event.chunk || ""));
      }
    }

    if (event.type === "test_output" && event.results) {
      setOutputs((prev) => ({ ...prev, testResults: event.results }));
      setRightActiveTab("cli");
    }
    if (event.type === "cli_output" && event.message) {
      setCliLogs((prev) => [...prev, event.message]);
      setRightActiveTab("cli");
    }

    if (["agent_start", "agent_end", "tool_start", "tool_error", "system_error", "human_approval"].includes(event.type)) {
      setRightActiveTab("activity");
    }

    if (event.type === "task_completed") {
      setTaskStatus("completed");
      setAgents((prev) => prev.map(a => ({ ...a, status: a.status === "running" ? "completed" : a.status })));
      setRightActiveTab("activity");
    }
    if (event.type === "task_paused") {
      setTaskStatus("paused");
      setAgents((prev) => prev.map(a => ({ ...a, status: a.status === "running" ? "stopped" : a.status })));
      setRightActiveTab("activity");
    }
    if (event.type === "task_resumed") {
      setTaskStatus("running");
      // Could restore running state but we just rely on next agent_start
      setRightActiveTab("activity");
    }
    if (event.type === "task_cancelled") {
      setTaskStatus("cancelled");
      setAgents((prev) => prev.map(a => ({ ...a, status: a.status === "running" ? "stopped" : a.status })));
      setRightActiveTab("activity");
    }
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
      setTaskPrompt(data.prompt || "");
      setTaskCreatedAt(data.created_at || "");
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
      testResults: "",
    });
    setCliLogs([]);
    setCodeFiles([]);
    setSpecFile(null);
    setReviewFile(null);
    setTaskPrompt("");
    setTaskCreatedAt("");

    // Fetch existing code versions from disk
    fetch(`http://localhost:8000/api/task/${taskId}/code-versions`)
      .then((r) => r.json())
      .then((data) => {
        if (data.files && data.files.length > 0) {
          setCodeFiles(data.files);
          // Set the latest code as output
          const latest = data.files[data.files.length - 1];
          setOutputs((prev) => ({ ...prev, code: latest.content }));
        }
      })
      .catch(() => { });

    // Fetch latest spec from disk
    fetch(`http://localhost:8000/api/task/${taskId}/spec`)
      .then((r) => r.json())
      .then((data) => {
        if (data.spec) {
          setSpecFile({ filename: "spec.md", content: data.spec });
        }
      })
      .catch(() => { });

    // Fetch latest review from disk
    fetch(`http://localhost:8000/api/task/${taskId}/review`)
      .then((r) => r.json())
      .then((data) => {
        if (data.review) {
          setReviewFile({ filename: "review.md", content: data.review });
        }
      })
      .catch(() => { });

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

  const handleCancel = async () => {
    if (!taskId) return;
    await fetch(`http://localhost:8000/api/task/${taskId}/cancel`, {
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
      case "cancelled":
        return "bg-orange-500/20 text-orange-400";
      default:
        return "bg-purple-500/20 text-purple-400";
    }
  };

  return (
    <SidebarProvider defaultOpen={false}>
      <HistorySidebar agents={agents} />
      <SidebarInset>
        <div className="flex h-screen bg-background overflow-hidden">

          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="h-14 flex items-center justify-between px-4 border-b border-border bg-card">
              <div className="flex items-center gap-3">
                <div className="w-1" />
                <Badge className={getStatusColor()}>
                  {taskStatus.toUpperCase()}
                </Badge>
                <Badge
                  variant="outline"
                  className="border-border text-muted-foreground text-xs"
                >
                  {!taskModel ? (
                    <span className="flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" /> Loading...
                    </span>
                  ) : taskModel.toLowerCase().includes("groq") || taskModel.includes("-") ? (
                    `🚀 ${taskModel}`
                  ) : (
                    `🦙 ${taskModel}`
                  )}
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
                {(taskStatus === "running" || taskStatus === "paused") && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCancel}
                    className="text-red-500 hover:text-red-600"
                  >
                    <StopCircle className="w-4 h-4 mr-1" /> Cancel
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
              <div className="w-[350px] border-r border-border shrink-0 flex flex-col overflow-hidden">
                <ChatPanel
                  taskId={taskId}
                  events={events}
                  initialPrompt={taskPrompt}
                  initialTimestamp={taskCreatedAt}
                  onSendMessage={async (message) => {
                    try {
                      await fetch(`http://localhost:8000/api/task/${taskId}/message`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message }),
                      });
                    } catch (err) {
                      console.error("Failed to send message:", err);
                    }
                  }}
                  isLoading={taskStatus === "running"}
                />
              </div>

              <div className="flex-1 overflow-hidden">
                <CodeWorkspace code={outputs.code} codeFiles={codeFiles} specFile={specFile} reviewFile={reviewFile} streamingFile={streamingFile} streamingContent={streamingContent} isReadOnly />
              </div>

              <div className="hidden xl:flex flex-col border-l border-border w-[450px]">
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="flex border-b border-border bg-card">
                    <button
                      onClick={() => setRightActiveTab("activity")}
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 text-xs font-medium ${rightActiveTab === "activity"
                        ? "bg-muted text-foreground border-b-2 border-purple-500"
                        : "text-muted-foreground hover:text-foreground"
                        }`}
                    >
                      <Activity className="w-3.5 h-3.5" /> Activity
                    </button>

                    <button
                      onClick={() => setRightActiveTab("cli")}
                      className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 text-xs font-medium ${rightActiveTab === "cli"
                        ? "bg-muted text-foreground border-b-2 border-green-500"
                        : "text-muted-foreground hover:text-foreground"
                        }`}
                    >
                      <Terminal className="w-3.5 h-3.5" /> CLI Tests
                      {cliLogs.length > 0 && (
                        <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                      )}
                    </button>
                  </div>
                  <div className="flex-1 overflow-hidden relative">
                    {rightActiveTab === "activity" && (
                      <ActivityPanel events={events} />
                    )}
                    {rightActiveTab === "cli" && (
                      <div className="absolute inset-0 overflow-hidden">
                        <CLIPanel logs={cliLogs} testResults={outputs.testResults} commandRecords={terminalCommands} />
                      </div>
                    )}
                  </div>


                </div>

                <div className="h-72 border-t border-border overflow-hidden flex flex-col shrink-0">
                  <div className="flex items-center justify-between border-b border-border bg-card px-4 py-1.5">
                    <div className="flex items-center gap-2 text-sm text-foreground font-medium">
                      <Terminal className="w-4 h-4" /> Terminal
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-foreground hover:bg-muted"
                      onClick={handlePopOutTerminal}
                      title="Pop out terminal"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </Button>
                  </div>

                  <div className="flex-1 overflow-hidden bg-[#1a1b26] relative">
                    {isTerminalPoppedOut ? (
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground bg-card/80 backdrop-blur-sm z-10">
                        <Terminal className="w-7 h-7 opacity-40 animate-pulse" />
                        <span className="text-xs">Terminal is popped out</span>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="h-7 text-xs border-border hover:bg-muted mt-1"
                          onClick={() => {
                            if (terminalWindowRef.current) {
                              terminalWindowRef.current.close();
                            }
                            setIsTerminalPoppedOut(false);
                          }}
                        >
                          Restore View
                        </Button>
                      </div>
                    ) : (
                      <TerminalComponent className="h-full w-full" />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </SidebarInset>
      <RejectModal
        isOpen={isRejectModalOpen}
        onClose={() => setIsRejectModalOpen(false)}
        onSubmit={handleReject}
      />
    </SidebarProvider >
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center">Loading Workspace...</div>}>
      <WorkspaceContent />
    </Suspense>
  );
}

