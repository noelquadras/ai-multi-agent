"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AgentCard } from "./AgentCard";
import { LayoutGrid } from "lucide-react";
import { useState, useEffect } from "react";

interface AgentPanelProps {
  taskStatus?: {
    status: "pending" | "running" | "completed" | "failed";
    progress?: number;
  } | null;
}

type AgentPhase = "Idle" | "Thinking" | "Approved" | "Error";

interface AgentUI {
  name: string;
  role: string;
  status: AgentPhase;
  confidence: number;
  errors: number;
  statusMessage: string;
  isWorking: boolean;
}

const initialAgents: AgentUI[] = [
  {
    name: "Planner",
    role: "Architect",
    status: "Idle",
    confidence: 95,
    errors: 0,
    statusMessage: "Awaiting task assignment",
    isWorking: false,
  },
  {
    name: "Coder",
    role: "Full Stack Dev",
    status: "Idle",
    confidence: 92,
    errors: 0,
    statusMessage: "Standing by for requirements",
    isWorking: false,
  },
  {
    name: "Tester",
    role: "QA Engineer",
    status: "Idle",
    confidence: 88,
    errors: 0,
    statusMessage: "Ready for testing phase",
    isWorking: false,
  },
  {
    name: "Debugger",
    role: "Troubleshooter",
    status: "Idle",
    confidence: 90,
    errors: 0,
    statusMessage: "Monitoring system health",
    isWorking: false,
  },
  {
    name: "Reviewer",
    role: "Code Reviewer",
    status: "Idle",
    confidence: 87,
    errors: 0,
    statusMessage: "Ready for code review",
    isWorking: false,
  },
  {
    name: "Refiner",
    role: "Code Refiner",
    status: "Idle",
    confidence: 85,
    errors: 0,
    statusMessage: "Waiting for code to refine",
    isWorking: false,
  },
];

export function AgentPanel({ taskStatus }: AgentPanelProps) {
  const [agents, setAgents] = useState<AgentUI[]>(initialAgents);

  useEffect(() => {
    if (!taskStatus) {
      setAgents(initialAgents);
      return;
    }

    const progress = taskStatus.progress ?? 0;
    const isRunning = taskStatus.status === "running";
    const isCompleted = taskStatus.status === "completed";
    const isFailed = taskStatus.status === "failed";

    if (isFailed) {
      setAgents(
        initialAgents.map((a) => ({
          ...a,
          status: "Error",
          isWorking: false,
          statusMessage: "Task failed",
        }))
      );
      return;
    }

    if (isCompleted) {
      setAgents(
        initialAgents.map((a) => ({
          ...a,
          status: "Approved",
          isWorking: false,
          statusMessage: "Task completed successfully",
        }))
      );
      return;
    }

    if (!isRunning) {
      setAgents(initialAgents);
      return;
    }

    const updated = initialAgents.map((a) => ({ ...a }));

    // Planner (0–30)
    if (progress < 30) {
      updated[0].status = "Thinking";
      updated[0].isWorking = true;
      updated[0].statusMessage = "Designing architecture";
    } else {
      updated[0].status = "Approved";
    }

    // Coder (20–70)
    if (progress >= 20 && progress < 70) {
      updated[1].status = "Thinking";
      updated[1].isWorking = true;
      updated[1].statusMessage = "Writing code";
    } else if (progress >= 70) {
      updated[1].status = "Approved";
    }

    // Reviewer (40–80)
    if (progress >= 40 && progress < 80) {
      updated[4].status = "Thinking";
      updated[4].isWorking = true;
      updated[4].statusMessage = "Reviewing code";
    }

    // Refiner (60–90)
    if (progress >= 60 && progress < 90) {
      updated[5].status = "Thinking";
      updated[5].isWorking = true;
      updated[5].statusMessage = "Refining code";
    }

    // Tester (70–95)
    if (progress >= 70 && progress < 95) {
      updated[2].status = "Thinking";
      updated[2].isWorking = true;
      updated[2].statusMessage = "Running tests";
    }

    setAgents(updated);
  }, [taskStatus]);

  const activeCount = agents.filter(
    (a) => a.isWorking || a.status === "Thinking"
  ).length;

  return (
    <Card className="h-full border-none rounded-none border-r border-[#1F1F1F] bg-[#050505] w-75 flex flex-col">
      <CardHeader className="pb-4 pt-5 px-5 border-b border-[#1F1F1F]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-zinc-100">
            <LayoutGrid className="w-4 h-4 text-purple-400" />
            <CardTitle className="text-sm font-bold tracking-wider">
              ARCHONS
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-500 font-mono">
              {activeCount} ACTIVE
            </span>
            {taskStatus?.status === "running" && (
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0 flex-1 min-h-0">
        <ScrollArea className="h-full">
          <div className="space-y-3 p-4">
            {agents.map((agent) => (
              <AgentCard
                key={agent.name}
                {...agent}
                taskProgress={
                  agent.isWorking ? taskStatus?.progress || 0 : undefined
                }
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
