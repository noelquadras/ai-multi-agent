"use client";

import { useState, useEffect } from "react";
import { AgentPanel } from "@/components/workspace/AgentPanel";
import { CodeWorkspace } from "@/components/workspace/CodeWorkspace";
import { ActivityPanel } from "@/components/workspace/ActivityPanel";
import { PreviewPanel } from "@/components/workspace/PreviewPanel";
import {
  Box,
  Play,
  Share2,
  Settings,
  Loader2,
  CheckCircle,
  AlertCircle,
  Copy,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useExecution } from "@/app/context/ExecutionContext";

interface CrewResult {
  generated_code?: string;
  review_report?: string;
  decision?: string;
  refined_code?: string;
  documentation?: string;
}

interface AgentStatus {
  id: string;
  name: string;
  role: string;
  status: "idle" | "thinking" | "approved" | "error";
  message?: string;
}

interface TaskStatus {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  logs: string[];
  agents: AgentStatus[];
  result?: CrewResult;
  error?: string;
}

export default function WorkspacePage() {
  const { taskId } = useExecution();

  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">(
    "checking"
  );
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTaskStatus = async () => {
    if (!taskId) return;
    const res = await fetch(`http://localhost:8000/api/task/${taskId}`);
    const data: TaskStatus = await res.json();
    setTaskStatus(data);
    setLogs(data.logs ?? []);
    setLoading(false);
  };

  const checkApiHealth = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/health");
      setApiStatus(res.ok ? "online" : "offline");
    } catch {
      setApiStatus("offline");
    }
  };

  useEffect(() => {
    checkApiHealth();
  }, []);

  useEffect(() => {
    if (!taskId) return;
    fetchTaskStatus();
  }, [taskId]);

  useEffect(() => {
    if (!taskId || taskStatus?.status !== "running") return;
    const i = setInterval(fetchTaskStatus, 1500);
    return () => clearInterval(i);
  }, [taskId, taskStatus?.status]);

  if (!taskId) {
    return (
      <div className="flex h-screen items-center justify-center text-gray-400">
        No active task.
      </div>
    );
  }

  const renderStatusBadge = () => {
    if (!taskStatus) return null;
    const map = {
      pending: ["PENDING", "bg-yellow-500/20 text-yellow-400"],
      running: [
        `RUNNING (${taskStatus.progress}%)`,
        "bg-blue-500/20 text-blue-400",
      ],
      completed: ["COMPLETED", "bg-green-500/20 text-green-400"],
      failed: ["FAILED", "bg-red-500/20 text-red-400"],
    } as const;

    const [label, cls] = map[taskStatus.status];
    return (
      <Badge className={`${cls} border-transparent`}>
        {taskStatus.status === "running" && (
          <Loader2 className="w-3 h-3 mr-2 animate-spin" />
        )}
        {taskStatus.status === "completed" && (
          <CheckCircle className="w-3 h-3 mr-2" />
        )}
        {taskStatus.status === "failed" && (
          <AlertCircle className="w-3 h-3 mr-2" />
        )}
        {label}
      </Badge>
    );
  };

  return (
    <div className="flex h-screen flex-col bg-[#050505] overflow-hidden">
      {/* Header */}
      <header className="h-16 flex items-center justify-between px-6 border-b border-[#1F1F1F] bg-[#0A0A0A]">
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 rounded bg-purple-600 flex items-center justify-center">
            <Box className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-widest uppercase">
              Nexus Core
            </h1>
            <p className="text-[10px] text-zinc-500">Workspace</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {apiStatus === "online" && (
            <Badge className="bg-green-500/20 text-green-400">API ONLINE</Badge>
          )}
          {renderStatusBadge()}
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchTaskStatus}
            className="text-zinc-400"
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
          <Button className="bg-purple-600 hover:bg-purple-700 text-xs">
            <Play className="w-3 h-3 mr-2" />
            Deploy
          </Button>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Agents */}
        <div className="hidden md:block flex-none">
          <AgentPanel agents={taskStatus?.agents} />
        </div>

        {/* Main */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex flex-1 overflow-hidden">
            <div className="flex-1 overflow-hidden">
              {!loading && taskStatus?.result && (
                <CodeWorkspace
                  code={
                    taskStatus.result.refined_code ||
                    taskStatus.result.generated_code ||
                    ""
                  }
                  isReadOnly
                />
              )}
            </div>

            <div className="hidden xl:block flex-none border-l border-[#1F1F1F]">
              <PreviewPanel taskStatus={taskStatus} />
            </div>
          </div>

          {/* Logs */}
          <div className="h-72 border-t border-[#1F1F1F] overflow-hidden">
            <div className="h-full overflow-y-auto">
              <ActivityPanel logs={logs} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
