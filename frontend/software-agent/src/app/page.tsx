"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Bot,
  ArrowRight,
  Loader2,
  Cpu,
  Cloud,
  LogIn,
  Sun,
  Moon,
} from "lucide-react";
import { useExecution } from "@/app/context/ExecutionContext";
import { UserMenu } from "@/components/auth/UserMenu";
import { useTheme } from "@/hooks/useTheme";
import { HistorySidebar } from "@/components/HistorySidebar";
import { History } from "lucide-react";

/* =========================
   TYPES
========================= */

interface CrewResponse {
  task_id: string;
  model: string;
}

/* =========================
   COMPONENT
========================= */

import { ModelSelector, AgentModels, ModelOption } from "@/components/ModelSelector";

export default function HomePage() {
  const { toggleTheme } = useTheme();
  const router = useRouter();
  const { data: session, status: sessionStatus } = useSession();
  const {
    setPrompt: setGlobalPrompt,
    startSubscription,
    isRunning,
  } = useExecution();
  const [localPrompt, setLocalPrompt] = useState("");
  const [selectedModel, setSelectedModel] = useState<string>("ollama");
  
  // New state for per-agent configuration
  const [agentModels, setAgentModels] = useState<AgentModels>({
    coder: "default",
    reviewer: "default",
    decision: "default",
    refiner: "default",
    doc_writer: "default",
    tester: "default",
  });

  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking",
  );
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  const [models, setModels] = useState<ModelOption[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/api/models")
      .then((res) => res.json())
      .then((data) => {
        const mappedModels = data.models.map((m: any) => ({
          id: m.id,
          name: m.name,
          description: m.description || "AI Model",
          icon: m.type === "cloud" ? Cloud : Cpu,
          speed: m.speed,
          cost: m.cost,
          type: m.type, // Ensure type is passed
        }));
        setModels(mappedModels);
        // Select first model by default if none selected
        if (mappedModels.length > 0 && !selectedModel) {
            setSelectedModel(mappedModels[0].id);
        }
      })
      .catch((err) => console.error("Failed to fetch models:", err));
  }, []);

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

    // Prepare agent_models dictionary, filtering out "default" values
    // If a model is set to "default", we don't send it, so backend uses the main model
    const specificAgentModels: Record<string, string> = {};
    Object.entries(agentModels).forEach(([agent, model]) => {
      if (model !== "default") {
        specificAgentModels[agent] = model;
      }
    });

    try {
      const res = await fetch("http://localhost:8000/api/run-crew", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: localPrompt,
          model: selectedModel,
          agent_models: Object.keys(specificAgentModels).length > 0 ? specificAgentModels : undefined,
          user_id: session?.user?.id,
          project_id: "default",
        }),
      });

      if (!res.ok) {
        alert("Server failed to start task!");
        return;
      }

      const data: CrewResponse = await res.json();

      setGlobalPrompt(localPrompt);
      router.push(`/workspace?taskId=${data.task_id}`);
    } catch (error) {
      console.error("Network error:", error);
    }
  };

  const handleAgentModelChange = (agent: keyof AgentModels, modelId: string) => {
    setAgentModels((prev) => ({
      ...prev,
      [agent]: modelId,
    }));
  };

  /* =========================
     UI
  ========================= */

  return (
    <main className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Top Bar */}
      <div className="h-14 border-b border-border bg-card flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
            <Bot className="text-primary-foreground w-5 h-5" />
          </div>
          <span className="font-semibold text-sm">AI Software Team</span>
        </div>

        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsHistoryOpen(true)}
            className="text-muted-foreground hover:text-foreground"
          >
            <History className="w-4 h-4 mr-2" />
            History
          </Button>

          {sessionStatus === "authenticated" ? (
            <UserMenu />
          ) : sessionStatus === "unauthenticated" ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/auth/signin")}
              className="text-muted-foreground hover:text-foreground"
            >
              <LogIn className="w-4 h-4 mr-2" />
              Sign In
            </Button>
          ) : null}

          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            className="text-muted-foreground hover:text-foreground"
          >
            <Sun className="h-4 w-4 dark:hidden" />
            <Moon className="h-4 w-4 hidden dark:block" />
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col items-center pt-24 px-4">
        {/* Header */}
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold">Autonomous AI Software Team</h1>
        </div>

        <p className="text-muted-foreground mb-8">
          Describe what you want to build. Our AI agents will generate, review,
          test, and document it.
        </p>

        {/* API STATUS */}
        <div className="mb-6">
          {apiStatus === "online" && (
            <Badge className="bg-green-500/20 text-green-500">API ONLINE</Badge>
          )}
          {apiStatus === "offline" && (
            <Badge className="bg-red-500/20 text-red-500">API OFFLINE</Badge>
          )}
          {apiStatus === "checking" && (
            <Badge className="bg-yellow-500/20 text-yellow-500">
              <Loader2 className="w-3 h-3 mr-2 animate-spin" />
              Checking API
            </Badge>
          )}
        </div>

        {/* INPUT CARD */}
        <div className="w-full max-w-3xl bg-card border border-border rounded-xl p-4">
          <Textarea
            placeholder="Describe the application you want to build..."
            value={localPrompt}
            onChange={(e) => setLocalPrompt(e.target.value)}
            disabled={isRunning}
            className="min-h-35 bg-transparent border-none text-foreground resize-none placeholder:text-muted-foreground"
          />

          {/* Model Selection */}
          <div className="mt-4 pt-4 border-t border-border">
             <ModelSelector 
                models={models}
                selectedModel={selectedModel}
                onSelectModel={setSelectedModel}
                agentModels={agentModels}
                onAgentModelChange={handleAgentModelChange}
                disabled={isRunning}
             />
          </div>

          <div className="flex justify-end mt-4">
            <Button
              disabled={
                !localPrompt.trim() || apiStatus !== "online" || isRunning
              }
              onClick={startCrew}
              className="bg-linear-to-r from-purple-600 to-blue-600 text-white hover:opacity-90"
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
      </div>

      <HistorySidebar
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
      />
    </main>
  );
}
