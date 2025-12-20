'use client';

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AgentCard } from "./AgentCard";
import { LayoutGrid } from "lucide-react";
import { useState, useEffect } from "react";

interface AgentPanelProps {
  taskStatus?: {
    status: string;
    progress?: number;
    result?: any;
    error?: string;
  } | null;
}

const initialAgents = [
  {
    name: "Planner",
    role: "Architect",
    status: "Idle" as const,
    confidence: 95,
    errors: 0,
    statusMessage: "Awaiting task assignment",
    isWorking: false
  },
  {
    name: "Coder",
    role: "Full Stack Dev",
    status: "Idle" as const,
    confidence: 92,
    errors: 0,
    statusMessage: "Standing by for requirements",
    isWorking: false
  },
  {
    name: "Tester",
    role: "QA Engineer",
    status: "Idle" as const,
    confidence: 88,
    errors: 0,
    statusMessage: "Ready for testing phase",
    isWorking: false
  },
  {
    name: "Debugger",
    role: "Troubleshooter",
    status: "Idle" as const,
    confidence: 90,
    errors: 0,
    statusMessage: "Monitoring system health",
    isWorking: false
  },
  {
    name: "Reviewer",
    role: "Code Reviewer",
    status: "Idle" as const,
    confidence: 87,
    errors: 0,
    statusMessage: "Ready for code review",
    isWorking: false
  },
  {
    name: "Refiner",
    role: "Code Refiner",
    status: "Idle" as const,
    confidence: 85,
    errors: 0,
    statusMessage: "Waiting for code to refine",
    isWorking: false
  },
];

export function AgentPanel({ taskStatus }: AgentPanelProps) {
  const [agents, setAgents] = useState(initialAgents);

  useEffect(() => {
    if (!taskStatus) {
      // Reset to idle state
      setAgents(initialAgents.map(agent => ({
        ...agent,
        status: "Idle" as const,
        isWorking: false,
        statusMessage: "Awaiting task assignment"
      })));
      return;
    }

    const updateAgentsBasedOnTask = () => {
      const progress = taskStatus.progress || 0;
      const isRunning = taskStatus.status === 'running';
      const isCompleted = taskStatus.status === 'completed';
      const isFailed = taskStatus.status === 'failed';

      if (isFailed) {
        return initialAgents.map(agent => ({
          ...agent,
          status: "Error" as const,
          isWorking: false,
          statusMessage: "Task failed - Check logs"
        }));
      }

      if (isCompleted) {
        return initialAgents.map(agent => ({
          ...agent,
          status: "Approved" as const,
          isWorking: false,
          statusMessage: "Task completed successfully"
        }));
      }

      if (!isRunning) {
        return initialAgents.map(agent => ({
          ...agent,
          status: "Idle" as const,
          isWorking: false,
          statusMessage: "Awaiting task assignment"
        }));
      }

      // Running state - simulate agent workflow
      const newAgents = [...initialAgents];
      
      // Planner: Active first 30%
      if (progress < 30) {
        newAgents[0] = {
          ...newAgents[0],
          status: "Thinking" as const,
          isWorking: true,
          statusMessage: "Designing application architecture",
          confidence: 95 + Math.floor(Math.random() * 5)
        };
      } else if (progress < 50) {
        newAgents[0] = {
          ...newAgents[0],
          status: "Approved" as const,
          isWorking: false,
          statusMessage: "Architecture finalized",
          confidence: 98
        };
      }

      // Coder: Active 20-70%
      if (progress >= 20 && progress < 70) {
        newAgents[1] = {
          ...newAgents[1],
          status: "Thinking" as const,
          isWorking: true,
          statusMessage: "Writing implementation code",
          confidence: 92 + Math.floor(Math.random() * 8),
          errors: progress < 40 ? 0 : 1
        };
      } else if (progress >= 70) {
        newAgents[1] = {
          ...newAgents[1],
          status: "Approved" as const,
          isWorking: false,
          statusMessage: "Code implementation completed",
          confidence: 96
        };
      }

      // Reviewer: Active 40-80%
      if (progress >= 40 && progress < 80) {
        newAgents[4] = {
          ...newAgents[4],
          status: "Thinking" as const,
          isWorking: true,
          statusMessage: "Reviewing generated code",
          confidence: 87 + Math.floor(Math.random() * 10)
        };
      } else if (progress >= 80) {
        newAgents[4] = {
          ...newAgents[4],
          status: "Approved" as const,
          isWorking: false,
          statusMessage: "Code review completed",
          confidence: 92
        };
      }

      // Refiner: Active 60-90%
      if (progress >= 60 && progress < 90) {
        newAgents[5] = {
          ...newAgents[5],
          status: "Thinking" as const,
          isWorking: true,
          statusMessage: "Refining and optimizing code",
          confidence: 85 + Math.floor(Math.random() * 10)
        };
      } else if (progress >= 90) {
        newAgents[5] = {
          ...newAgents[5],
          status: "Approved" as const,
          isWorking: false,
          statusMessage: "Code refinement completed",
          confidence: 94
        };
      }

      // Tester: Active 70-95%
      if (progress >= 70 && progress < 95) {
        newAgents[2] = {
          ...newAgents[2],
          status: "Thinking" as const,
          isWorking: true,
          statusMessage: "Running automated tests",
          confidence: 88 + Math.floor(Math.random() * 10)
        };
      } else if (progress >= 95) {
        newAgents[2] = {
          ...newAgents[2],
          status: "Approved" as const,
          isWorking: false,
          statusMessage: "All tests passed",
          confidence: 95
        };
      }

      // Debugger: Active when errors exist
      const hasErrors = newAgents.some(a => a.errors > 0);
      if (hasErrors) {
        newAgents[3] = {
          ...newAgents[3],
          status: "Thinking" as const,
          isWorking: true,
          statusMessage: "Debugging identified issues",
          confidence: 90
        };
      } else {
        newAgents[3] = {
          ...newAgents[3],
          status: "Idle" as const,
          isWorking: false,
          statusMessage: "No issues detected",
          confidence: 90
        };
      }

      return newAgents;
    };

    setAgents(updateAgentsBasedOnTask());
  }, [taskStatus]); // Removed 'agents' from dependency array

  const activeCount = agents.filter(a => a.isWorking || a.status === "Thinking").length;

  return (
    <Card className="h-full border-none rounded-none border-r border-[#1F1F1F] bg-[#050505] w-[300px] flex flex-col">
      <CardHeader className="pb-4 pt-5 px-5 border-b border-[#1F1F1F]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-zinc-100">
            <LayoutGrid className="w-4 h-4 text-purple-400" />
            <CardTitle className="text-sm font-bold tracking-wider">ARCHONS</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-500 font-mono">
              {activeCount} ACTIVE
            </span>
            {taskStatus?.status === 'running' && (
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0 flex-1">
        <ScrollArea className="h-full">
          <div className="space-y-3 p-4">
            {agents.map((agent) => (
              <AgentCard
                key={agent.name}
                {...agent}
                taskProgress={agent.isWorking ? (taskStatus?.progress || 0) : undefined}
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}