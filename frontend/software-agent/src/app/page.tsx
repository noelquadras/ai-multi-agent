"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { BACKEND_URL } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  ArrowRight,
  Cpu,
  Cloud,
} from "lucide-react";
import { HistorySidebar } from "@/components/HistorySidebar";
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar";

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
  const router = useRouter();
  const { data: session } = useSession();
  const [localPrompt, setLocalPrompt] = useState("");
  const [selectedModel, setSelectedModel] = useState<string>("");

  // New state for per-agent configuration
  const [agentModels, setAgentModels] = useState<AgentModels>({
    coder: "default",
    reviewer: "default",
    refiner: "default",
    tester: "default",
    supervisor: "default",
    spec_writer: "default",
  });

  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">(
    "checking",
  );

  const [models, setModels] = useState<ModelOption[]>([]);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/models`)
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
    fetch(`${BACKEND_URL}/api/health`)
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
      const res = await fetch(`${BACKEND_URL}/api/run-crew`, {
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
    <SidebarProvider>
      <HistorySidebar apiStatus={apiStatus} />
      <SidebarInset>
        <main className="min-h-screen bg-background text-foreground flex flex-col">
          {/* Main Content */}
          <div className="flex-1 flex flex-col items-center pt-24 px-4">
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold">Multi-Agent AI Software Team</h1>
            </div>

            <p className="text-muted-foreground mb-8">
              Describe what you want to build. Our AI agents will generate, review,
              test, and document it.
            </p>

            {/* INPUT CARD */}
            <div className="w-full max-w-3xl bg-card border border-border rounded-xl p-4">
              <Textarea
                placeholder="Describe the application you want to build..."
                value={localPrompt}
                onChange={(e) => setLocalPrompt(e.target.value)}
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
                />
              </div>

              <div className="flex justify-end mt-4">
                <Button
                  disabled={
                    !localPrompt.trim() || apiStatus !== "online"
                  }
                  onClick={startCrew}
                  className="bg-linear-to-r from-purple-600 to-blue-600 text-white hover:opacity-90"
                >
                  <>
                    Build with AI Team
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </>
                </Button>
              </div>
            </div>
          </div>

        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
