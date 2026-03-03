"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Terminal,
  EyeOff,
  Eye,
  AlertCircle,
  Wrench,
  Users,
  FileCode,
  CheckCircle,
  XCircle,
  Pause,
  Play,
  TestTube,
  FileText,
  StopCircle,
} from "lucide-react";

/* =========================
   TYPES
========================= */

export type TaskEvent =
  | { type: "agent_start"; agent: string; timestamp: string }
  | { type: "agent_end"; agent: string; timestamp: string }
  | { type: "tool_start"; agent: string; tool: string; timestamp: string }
  | {
    type: "tool_error";
    agent: string;
    tool: string;
    error: string;
    timestamp: string;
  }
  | { type: "system_error"; error: string; timestamp: string }
  | { type: "log"; message: string; timestamp: string }
  | { type: "tool_call"; name: any; args: any; timestamp: string }
  | { type: "code_output"; agent: string; code: string; timestamp: string }
  | { type: "spec_output"; agent: string; spec: string; timestamp: string }
  | { type: "review_output"; agent: string; review: string; timestamp: string }
  | {
    type: "decision_output";
    agent: string;
    decision: string;
    timestamp: string;
  }
  | {
    type: "doc_output";
    agent: string;
    documentation: string;
    timestamp: string;
  }
  | { type: "test_output"; agent: string; results: string; timestamp: string }
  | { type: "cli_output"; message: string; timestamp: string }
  | { type: "task_completed"; timestamp: string }
  | { type: "task_paused"; message: string; timestamp: string }
  | { type: "task_resumed"; message: string; timestamp: string }
  | { type: "human_approval"; approved: boolean; message: string; timestamp: string }
  | { type: "human_message"; message: string; timestamp: string }
  | { type: "task_cancelled"; message: string; timestamp: string }
  | { type: "conversation"; message: string; timestamp: string }
  | { type: "clarification"; message: string; timestamp: string };

interface ActivityPanelProps {
  events?: TaskEvent[];
}

/* =========================
   COMPONENT
========================= */

export function ActivityPanel({ events = [] }: ActivityPanelProps) {
  const [showSystem, setShowSystem] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);

  /* =========================
     AUTO SCROLL
  ========================= */

  useEffect(() => {
    if (!scrollRef.current || !stickToBottomRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events, activeAgent, showSystem]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    stickToBottomRef.current = scrollHeight - scrollTop - clientHeight < 40;
  };

  /* =========================
     AGENT LIST
  ========================= */

  const agents = Array.from(
    new Set(events.filter((e) => "agent" in e).map((e) => (e as any).agent)),
  );

  /* =========================
     FILTER EVENTS
  ========================= */

  const visibleEvents = events.filter((e) => {
    if (!showSystem && e.type === "log") return false;

    if (activeAgent) {
      return "agent" in e && e.agent === activeAgent;
    }

    return true;
  });

  /* =========================
     RENDER
  ========================= */

  return (
    <Card className="h-full border-none rounded-none border-t border-border bg-background">
      {/* HEADER */}
      <CardHeader className="h-10 px-4 flex flex-row items-center justify-between border-b border-border bg-card">
        <div className="flex items-center gap-2 text-muted-foreground text-xs font-bold">
          <Terminal className="w-3 h-3 text-purple-500" />
          ACTIVITY
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setShowSystem((s) => !s)}
            className="h-7 w-7"
          >
            {showSystem ? (
              <Eye className="w-3 h-3" />
            ) : (
              <EyeOff className="w-3 h-3" />
            )}
          </Button>

          <Badge
            variant="outline"
            className="border-border text-muted-foreground text-[10px]"
          >
            {visibleEvents.length} events
          </Badge>
        </div>
      </CardHeader>

      {/* AGENT FILTER */}
      {agents.length > 0 && (
        <div className="px-4 py-2 border-b border-border bg-card flex items-center gap-2 overflow-x-auto">
          <Users className="w-3 h-3 text-muted-foreground bg-card" />

          <AgentFilterButton
            label="All"
            active={activeAgent === null}
            onClick={() => setActiveAgent(null)}
          />

          {agents.map((agent) => (
            <AgentFilterButton
              key={agent}
              label={agent}
              active={activeAgent === agent}
              onClick={() => setActiveAgent(agent)}
            />
          ))}
        </div>
      )}

      {/* CONTENT */}
      <CardContent className="p-0 h-full">
        <ScrollArea className="h-full">
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="h-full px-4 py-3 overflow-y-auto space-y-1 font-mono text-[11px] text-foreground"
          >
            {visibleEvents.length === 0 && (
              <div className="text-muted-foreground">
                No activity for selected agent
              </div>
            )}

            {visibleEvents.map((e, i) => (
              <EventRow key={i} event={e} />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

/* =========================
   SUB COMPONENTS
========================= */

function AgentFilterButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-2 py-1 text-[10px] rounded border transition-colors whitespace-nowrap ${active
        ? "bg-purple-500/20 text-purple-300 border-purple-500/40"
        : "bg-card text-zinc-500 border-zinc-800 hover:text-zinc-300"
        }`}
    >
      {label}
    </button>
  );
}

function EventRow({ event }: { event: TaskEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString();

  let color = "text-zinc-400";
  let label = "System";
  let message = "";
  let icon = null;

  switch (event.type) {
    case "agent_start":
      color = "text-blue-400";
      label = event.agent;
      message = "started working";
      break;

    case "agent_end":
      color = "text-green-400";
      label = event.agent;
      message = "completed task";
      break;

    case "tool_start":
      color = "text-purple-400";
      label = event.agent;
      icon = <Wrench className="w-3 h-3" />;
      message = `Using tool: ${event.tool}`;
      break;

    case "tool_error":
      color = "text-red-400";
      label = event.agent;
      message = `${event.tool}: ${event.error}`;
      break;

    case "system_error":
      color = "text-red-500";
      icon = <AlertCircle className="w-3 h-3" />;
      message = event.error;
      break;

    case "code_output":
      color = "text-emerald-400";
      label = event.agent;
      icon = <FileCode className="w-3 h-3" />;
      message = "emitted final code output";
      break;

    case "review_output":
      color = "text-yellow-400";
      label = event.agent;
      icon = <FileText className="w-3 h-3" />;
      message = "completed code review";
      break;

    case "spec_output":
      color = "text-emerald-400";
      label = event.agent;
      icon = <FileText className="w-3 h-3" />;
      message = "generated technical specification";
      break;

    case "decision_output":
      color = "text-purple-400";
      label = event.agent;
      message = `decision: ${event.decision}`;
      break;

    case "doc_output":
      color = "text-blue-400";
      label = event.agent;
      icon = <FileText className="w-3 h-3" />;
      message = "generated documentation";
      break;

    case "test_output":
      color = "text-cyan-400";
      label = event.agent;
      icon = <TestTube className="w-3 h-3" />;
      message = "completed CLI tests";
      break;

    case "cli_output":
      color = "text-green-400";
      label = "CLI";
      icon = <Terminal className="w-3 h-3" />;
      message = event.message;
      break;

    case "task_completed":
      color = "text-green-500";
      icon = <CheckCircle className="w-3 h-3" />;
      message = "Task completed successfully!";
      break;

    case "task_paused":
      color = "text-yellow-500";
      icon = <Pause className="w-3 h-3" />;
      message = event.message;
      break;

    case "task_resumed":
      color = "text-green-500";
      icon = <Play className="w-3 h-3" />;
      message = event.message;
      break;

    case "human_approval":
      color = event.approved ? "text-green-500" : "text-red-500";
      icon = event.approved ? (
        <CheckCircle className="w-3 h-3" />
      ) : (
        <XCircle className="w-3 h-3" />
      );
      label = "Human";
      message = event.message;
      break;

    case "human_message":
      color = "text-blue-400";
      label = "Human";
      message = event.message;
      break;

    case "log":
      message = event.message;
      break;

    case "task_cancelled":
      color = "text-orange-500";
      icon = <StopCircle className="w-3 h-3" />;
      message = event.message || "Task cancelled by user";
      break;

    case "conversation":
      color = "text-violet-400";
      label = "Supervisor";
      message = event.message;
      break;

    case "clarification":
      color = "text-amber-400";
      label = "Supervisor";
      message = `❓ ${event.message}`;
      break;
  }

  return (
    <div className="flex items-start gap-2 py-0.5">
      <span className="text-zinc-600">[{time}]</span>
      <span className={`font-bold ${color}`}>{label}</span>
      {icon}
      <span className={color}>{message}</span>
    </div>
  );
}
