"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AgentCard } from "./AgentCard";
import { LayoutGrid } from "lucide-react";

interface BackendAgent {
  id: string;
  name: string;
  role: string;
  status: "idle" | "thinking" | "approved" | "error";
  message?: string;
}

interface AgentPanelProps {
  agents?: BackendAgent[];
}

type UIStatus = "Idle" | "Thinking" | "Approved" | "Error";

const mapStatusToUI = (status: BackendAgent["status"]): UIStatus => {
  switch (status) {
    case "idle":
      return "Idle";
    case "thinking":
      return "Thinking";
    case "approved":
      return "Approved";
    case "error":
      return "Error";
  }
};

export function AgentPanel({ agents }: AgentPanelProps) {
  const activeCount =
    agents?.filter((a) => a.status === "thinking").length ?? 0;

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
            {activeCount > 0 && (
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0 flex-1 min-h-0">
        <ScrollArea className="h-full">
          <div className="space-y-3 p-4">
            {agents?.map((agent) => (
              <AgentCard
                key={agent.id}
                name={agent.name}
                role={agent.role}
                status={mapStatusToUI(agent.status)}
                statusMessage={agent.message ?? ""}
                isWorking={agent.status === "thinking"}
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
