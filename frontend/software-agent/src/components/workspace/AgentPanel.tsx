"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AgentCard } from "./AgentCard";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";

interface BackendAgent {
  id: string;
  name: string;
  role: string;
  status: "idle" | "running" | "completed" | "error" | "stopped";
  message?: string;
}

interface AgentPanelProps {
  agents?: BackendAgent[];
}

type UIStatus = "Idle" | "Running" | "Completed" | "Error" | "Stopped";

const mapStatusToUI = (status: BackendAgent["status"]): UIStatus => {
  switch (status) {
    case "idle":
      return "Idle";
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "error":
      return "Error";
    case "stopped":
      return "Stopped";
  }
};

export function AgentPanel({ agents }: AgentPanelProps) {
  const activeCount =
    agents?.filter((a) => a.status === "running").length ?? 0;

  return (
    <Card className="h-full border-none rounded-none border-r border-border bg-background w-75 flex flex-col">
      <CardHeader className="pb-4 pt-5 px-5 border-b border-border">
        <div className="flex items-center justify-between">
          <Link href="/">
            <Button variant="ghost" className="flex items-center gap-2 px-0 hover:bg-transparent -ml-2">
              <Home className="w-4 h-4 text-purple-500" />
              <span className="text-sm font-bold tracking-wider">HOME</span>
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-mono">
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
                isWorking={agent.status === "running"}
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
