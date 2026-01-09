"use client";

import { useEffect, useRef, useState } from "react";
import { AgentPanel } from "@/components/workspace/AgentPanel";
import { ActivityPanel, TaskEvent } from "@/components/workspace/ActivityPanel";
import { CodeWorkspace } from "@/components/workspace/CodeWorkspace";
import { PreviewPanel } from "@/components/workspace/PreviewPanel";
import { useExecution } from "@/app/context/ExecutionContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

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
  status: "pending" | "running" | "completed" | "failed";
  events: TaskEvent[];
}

/* =========================
   COMPONENT
========================= */

export default function WorkspacePage() {
  const { taskId } = useExecution();

  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [taskStatus, setTaskStatus] =
    useState<TaskSnapshot["status"]>("pending");
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [finalCode, setFinalCode] = useState("");

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
    doc_writer: {
      id: "doc_writer",
      name: "Doc Writer",
      role: "Documentation",
      status: "idle",
      progress: 0,
    },
  };

  /* =========================
     EVENT → AGENT STATE
  ========================= */

  const applyEventToAgents = (event: TaskEvent) => {
    setAgents((prev) => {
      const map = new Map(prev.map((a) => [a.id, { ...a }]));

      if (
        event.type !== "agent_start" &&
        event.type !== "agent_end" &&
        event.type !== "tool_error"
      ) {
        return Array.from(map.values());
      }

      const agent = map.get(event.agent);
      if (!agent) return Array.from(map.values());

      if (!agent) return Array.from(map.values());

      switch (event.type) {
        case "agent_start":
          agent.status = "thinking";
          agent.progress = Math.max(agent.progress, 5);
          break;

        case "agent_end":
          agent.status = "approved";
          agent.progress = 100;
          break;

        case "tool_error":
          agent.status = "error";
          break;

        default:
          if (agent.status === "thinking" && agent.progress < 90) {
            agent.progress += 10;
          }
      }

      map.set(agent.id, agent);
      return Array.from(map.values());
    });
  };

  /* =========================
     SSE SUBSCRIPTION
  ========================= */

  useEffect(() => {
    if (!taskId) return;

    setAgents(Object.values(AGENT_REGISTRY));
    setEvents([]);

    const es = new EventSource(
      `http://localhost:8000/api/task/${taskId}/events`
    );

    es.onmessage = (e) => {
      const event: TaskEvent = JSON.parse(e.data);

      setEvents((prev) => [...prev, event]);
      applyEventToAgents(event);

      if (event.type === "code_output") {
        setFinalCode(event.code);
      }
    };

    es.onerror = () => {
      es.close();
    };

    eventSourceRef.current = es;
    return () => es.close();
  }, [taskId]);

  /* =========================
     STATUS SNAPSHOT
  ========================= */

  const refreshStatus = async () => {
    if (!taskId) return;
    const res = await fetch(`http://localhost:8000/api/task/${taskId}`);
    const data: TaskSnapshot = await res.json();
    setTaskStatus(data.status);
  };

  useEffect(() => {
    if (!taskId) return;
    refreshStatus();
  }, [taskId]);

  /* =========================
     UI
  ========================= */

  if (!taskId) {
    return (
      <div className="flex h-screen items-center justify-center text-zinc-500">
        No active task
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#050505] overflow-hidden">
      {/* AGENTS */}
      <div className="hidden md:block flex-none">
        <AgentPanel agents={agents} />
      </div>

      {/* MAIN */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* HEADER */}
        <div className="h-12 flex items-center justify-between px-4 border-b border-[#1F1F1F] bg-[#0A0A0A]">
          <Badge className="bg-purple-500/20 text-purple-400">
            {taskStatus.toUpperCase()}
          </Badge>

          <Button
            variant="ghost"
            size="icon"
            onClick={refreshStatus}
            className="text-zinc-400"
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>

        {/* BODY */}
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <CodeWorkspace code={finalCode} isReadOnly />
          </div>

          <div className="hidden xl:block flex-none border-l border-[#1F1F1F]">
            <PreviewPanel taskStatus={{ status: taskStatus }} />
          </div>
        </div>

        {/* ACTIVITY */}
        <div className="h-72 border-t border-[#1F1F1F] overflow-hidden">
          <ActivityPanel events={events} />
        </div>
      </div>
    </div>
  );
}
