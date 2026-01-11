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

interface CrewResponse {
  task_id: string;
}

/* =========================
   COMPONENT
========================= */

export default function HomePage() {
  const router = useRouter();
  const {
    setPrompt: setGlobalPrompt,
    startSubscription,
    isRunning,
  } = useExecution();
  const [localPrompt, setLocalPrompt] = useState("");
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking"
  );

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
    if (!localPrompt.trim()) return;

    try {
      const res = await fetch("http://localhost:8000/api/run-crew", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      if (!res.ok) {
        alert("Server failed to start task!");
        return;
      }

      const data: CrewResponse = await res.json();

      setGlobalPrompt(localPrompt);
      startSubscription(data.task_id);
      router.push("/workspace");
    } catch (error) {
      console.log("Network error:", error);
    }
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
          <Badge className="bg-green-500/20 text-green-400">API ONLINE</Badge>
        )}
        {apiStatus === "offline" && (
          <Badge className="bg-red-500/20 text-red-400">API OFFLINE</Badge>
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
          value={localPrompt}
          onChange={(e) => setLocalPrompt(e.target.value)}
          disabled={isRunning}
          className="min-h-35 bg-transparent border-none text-zinc-300"
        />

        <div className="flex justify-end mt-4">
          <Button
            disabled={!localPrompt.trim() || apiStatus !== "online" || isRunning}
            onClick={startCrew}
            className="bg-zinc-100 text-black"
          >
            {isRunning ? (
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
    </main>
  );
}
