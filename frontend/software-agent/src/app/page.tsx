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
} from "lucide-react";
import { useExecution } from "@/app/context/ExecutionContext";
import { UserMenu } from "@/components/auth/UserMenu";

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
    "checking"
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
    <main className="min-h-screen bg-[#050505] text-white flex flex-col">
      {/* Top Bar */}
      <div className="h-14 border-b border-[#1F1F1F] bg-[#0A0A0A] flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center">
            <Bot className="text-white w-5 h-5" />
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
              className="text-zinc-400 hover:text-white"
            >
              <LogIn className="w-4 h-4 mr-2" />
              Sign In
            </Button>
          ) : null}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col items-center pt-24 px-4">
        {/* Header */}
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold">Autonomous AI Software Team</h1>
        </div>
        <p className="text-zinc-500 mb-8">
          Describe what you want to build. Our AI agents will generate, review, test, and document it.
        </p>

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

        {/* INPUT CARD */}
        <div className="w-full max-w-3xl bg-[#0A0A0A] border border-[#1F1F1F] rounded-xl p-4">
          <Textarea
            placeholder="Describe the application you want to build..."
            value={localPrompt}
            onChange={(e) => setLocalPrompt(e.target.value)}
            disabled={isRunning}
            className="min-h-35 bg-transparent border-none text-zinc-300 resize-none"
          />

          {/* Model Selection */}
          <div className="mt-4 pt-4 border-t border-[#1F1F1F]">
            <p className="text-xs text-zinc-500 mb-3">Select LLM Model</p>
            <div className="flex gap-3">
              {models.map((model) => (
                <button
                  key={model.id}
                  onClick={() => setSelectedModel(model.id)}
                  disabled={isRunning}
                  className={`flex-1 p-3 rounded-lg border transition-all ${
                    selectedModel === model.id
                      ? "border-purple-500 bg-purple-500/10"
                      : "border-[#2A2A2A] bg-[#141414] hover:border-[#3A3A3A]"
                  } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <model.icon className={`w-4 h-4 ${
                      selectedModel === model.id ? "text-purple-400" : "text-zinc-500"
                    }`} />
                    <span className={`text-sm font-medium ${
                      selectedModel === model.id ? "text-white" : "text-zinc-300"
                    }`}>
                      {model.name}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-500 text-left mb-2">
                    {model.description}
                  </p>
                  <div className="flex gap-2">
                    <Badge variant="outline" className="text-[10px] border-zinc-700">
                      {model.speed}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] border-zinc-700">
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
              className="bg-gradient-to-r from-purple-600 to-blue-600 text-white hover:opacity-90"
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
          <div className="p-4 bg-[#0A0A0A] border border-[#1F1F1F] rounded-lg">
            <div className="w-8 h-8 bg-blue-500/20 rounded-lg flex items-center justify-center mb-3">
              <Bot className="w-4 h-4 text-blue-400" />
            </div>
            <h3 className="font-medium text-sm mb-1">6 AI Agents</h3>
            <p className="text-xs text-zinc-500">
              Coder, Reviewer, Decision, Refiner, Tester, and Doc Writer
            </p>
          </div>
          <div className="p-4 bg-[#0A0A0A] border border-[#1F1F1F] rounded-lg">
            <div className="w-8 h-8 bg-green-500/20 rounded-lg flex items-center justify-center mb-3">
              <Cpu className="w-4 h-4 text-green-400" />
            </div>
            <h3 className="font-medium text-sm mb-1">CLI Testing</h3>
            <p className="text-xs text-zinc-500">
              Automated sandboxed code execution and testing
            </p>
          </div>
          <div className="p-4 bg-[#0A0A0A] border border-[#1F1F1F] rounded-lg">
            <div className="w-8 h-8 bg-purple-500/20 rounded-lg flex items-center justify-center mb-3">
              <Cloud className="w-4 h-4 text-purple-400" />
            </div>
            <h3 className="font-medium text-sm mb-1">Hybrid LLM</h3>
            <p className="text-xs text-zinc-500">
              Local Ollama or cloud Groq models
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
