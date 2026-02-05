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

/* =========================
   TYPES
========================= */

interface CrewResponse {
  task_id: string;
  model: string;
}

interface ModelOption {
  id: string;
  name: string;
  description: string;
  icon: typeof Cpu;
  speed: string;
  cost: string;
}

/* =========================
   COMPONENT
========================= */

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
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking",
  );

  const models: ModelOption[] = [
    {
      id: "ollama",
      name: "Local (Ollama)",
      description: "Mistral 7B running locally",
      icon: Cpu,
      speed: "Medium",
      cost: "Free",
    },
    {
      id: "groq",
      name: "Cloud (Groq)",
      description: "Llama 3.3 70B via Groq API",
      icon: Cloud,
      speed: "Fast",
      cost: "Free Tier",
    },
  ];

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
        body: JSON.stringify({
          prompt: localPrompt,
          model: selectedModel,
          user_id: session?.user?.id,
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
        </div>

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
            <p className="text-xs text-muted-foreground mb-3">
              Select LLM Model
            </p>

            <div className="flex gap-3">
              {models.map((model) => (
                <button
                  key={model.id}
                  onClick={() => setSelectedModel(model.id)}
                  disabled={isRunning}
                  className={`flex-1 p-3 rounded-lg border transition-all ${
                    selectedModel === model.id
                      ? "border-purple-500 bg-purple-500/10"
                      : "border-border bg-muted hover:border-ring"
                  } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <model.icon
                      className={`w-4 h-4 ${
                        selectedModel === model.id
                          ? "text-primary"
                          : "text-muted-foreground"
                      }`}
                    />
                    <span
                      className={`text-sm font-medium ${
                        selectedModel === model.id
                          ? "text-foreground"
                          : "text-muted-foreground"
                      }`}
                    >
                      {model.name}
                    </span>
                  </div>

                  <p className="text-xs text-muted-foreground text-left mb-2">
                    {model.description}
                  </p>

                  <div className="flex gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {model.speed}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {model.cost}
                    </Badge>
                  </div>
                </button>
              ))}
            </div>
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

        {/* Features */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-3xl">
          {[
            {
              icon: Bot,
              title: "6 AI Agents",
              desc: "Coder, Reviewer, Decision, Refiner, Tester, and Doc Writer",
              color: "text-blue-500",
              bg: "bg-blue-500/20",
            },
            {
              icon: Cpu,
              title: "CLI Testing",
              desc: "Automated sandboxed code execution and testing",
              color: "text-green-500",
              bg: "bg-green-500/20",
            },
            {
              icon: Cloud,
              title: "Hybrid LLM",
              desc: "Local Ollama or cloud Groq models",
              color: "text-purple-500",
              bg: "bg-purple-500/20",
            },
          ].map((f) => (
            <div
              key={f.title}
              className="p-4 bg-card border border-border rounded-lg"
            >
              <div
                className={`w-8 h-8 ${f.bg} rounded-lg flex items-center justify-center mb-3`}
              >
                <f.icon className={`w-4 h-4 ${f.color}`} />
              </div>
              <h3 className="font-medium text-sm mb-1">{f.title}</h3>
              <p className="text-xs text-muted-foreground">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
