"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Bot,
  Zap,
  ArrowRight,
  Loader2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { useExecution } from "@/app/context/ExecutionContext";

/* =========================
   TYPES
========================= */

type TaskEvent =
  | { type: "agent_start"; agent: string; timestamp: string }
  | { type: "agent_end"; agent: string; timestamp: string }
  | { type: "tool_start"; agent: string; tool: string; timestamp: string }
  | { type: "tool_error"; agent: string; tool: string; error: string; timestamp: string }
  | { type: "system_error"; error: string; timestamp: string }
  | { type: "log"; message: string; timestamp: string };

interface CrewResponse {
  task_id: string;
}

/* =========================
   COMPONENT
========================= */

export default function HomePage() {
  const router = useRouter();
  const { setTaskId, setPrompt: setGlobalPrompt } = useExecution();

  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking"
  );

  const eventSourceRef = useRef<EventSource | null>(null);

  /* =========================
     API HEALTH
  ========================= */

  useEffect(() => {
    fetch("http://localhost:8000/api/health")
      .then((r) => setApiStatus(r.ok ? "online" : "offline"))
      .catch(() => setApiStatus("offline"));
  }, []);

  /* =========================
     START CREW
  ========================= */

  const startCrew = async () => {
    if (!prompt.trim()) return;

    setRunning(true);
    setEvents([]);

    const res = await fetch("http://localhost:8000/api/run-crew", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    const data: CrewResponse = await res.json();
    const taskId = data.task_id;

    setTaskId(taskId);
    setGlobalPrompt(prompt);

    subscribeToEvents(taskId);
    router.push("/workspace");
  };

  /* =========================
     SSE SUBSCRIPTION
  ========================= */

  const subscribeToEvents = (taskId: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(
      `http://localhost:8000/api/task/${taskId}/events`
    );

    es.onmessage = (e) => {
      const event: TaskEvent = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    };

    es.onerror = () => {
      es.close();
      setRunning(false);
    };

    eventSourceRef.current = es;
  };

  /* =========================
     UI
  ========================= */

  return (
    <main className="min-h-screen bg-[#050505] text-white flex flex-col items-center pt-32 px-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-purple-600 rounded-lg flex items-center justify-center">
          <Bot className="text-white" />
        </div>
        <h1 className="text-3xl font-bold">Autonomous AI Software Team</h1>
      </div>

      {/* API STATUS */}
      <div className="mb-6">
        {apiStatus === "online" && (
          <Badge className="bg-green-500/20 text-green-400">
            API ONLINE
          </Badge>
        )}
        {apiStatus === "offline" && (
          <Badge className="bg-red-500/20 text-red-400">
            API OFFLINE
          </Badge>
        )}
        {apiStatus === "checking" && (
          <Badge className="bg-yellow-500/20 text-yellow-400">
            <Loader2 className="w-3 h-3 mr-2 animate-spin" />
            Checking API
          </Badge>
        )}
      </div>

      {/* INPUT */}
      <div className="w-full max-w-3xl bg-[#0A0A0A] border border-[#1F1F1F] rounded-xl p-4">
        <Textarea
          placeholder="Describe the application you want to build..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={running}
          className="min-h-[140px] bg-transparent border-none text-zinc-300"
        />

        <div className="flex justify-end mt-4">
          <Button
            disabled={!prompt.trim() || apiStatus !== "online" || running}
            onClick={startCrew}
            className="bg-zinc-100 text-black"
          >
            {running ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Running Crew
              </>
            ) : (
              <>
                Build with AI Team
                <ArrowRight className="w-4 h-4 ml-2" />
              </>
            )}
          </Button>
        </div>
      </div>

      {/* EVENTS PREVIEW */}
      {events.length > 0 && (
        <div className="mt-8 w-full max-w-3xl bg-black/40 rounded-lg p-4 text-xs font-mono">
          <div className="text-zinc-400 mb-2 flex items-center gap-2">
            <Zap className="w-3 h-3" />
            Live Events
            <Button
              size="icon"
              variant="ghost"
              className="ml-auto"
              onClick={() => setEvents([])}
            >
              <RefreshCw className="w-3 h-3" />
            </Button>
          </div>

          <div className="max-h-64 overflow-y-auto space-y-1">
            {events.slice(-20).map((e, i) => (
              <div key={i} className="text-zinc-300">
                [{new Date(e.timestamp).toLocaleTimeString()}]{" "}
                {e.type === "agent_start" && `🟦 ${e.agent} started`}
                {e.type === "agent_end" && `🟩 ${e.agent} finished`}
                {e.type === "tool_error" && `❌ ${e.tool}: ${e.error}`}
                {e.type === "system_error" && `🔥 ${e.error}`}
                {e.type === "log" && e.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
