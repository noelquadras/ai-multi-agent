"use client";

import { useState, useEffect } from "react";
import { Cpu, Cloud, ChevronDown, ChevronRight, Settings2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

/* =========================
   TYPES
========================= */

export interface ModelOption {
  id: string;
  name: string;
  description: string;
  // icon: any; // We'll handle icons internally based on type if needed, or pass them
  type: "local" | "cloud";
  speed: string;
  cost: string;
}

export interface AgentModels {
  coder: string;
  reviewer: string;
  refiner: string;
  tester: string;
  supervisor: string;
  spec_writer: string;
}


interface ModelSelectorProps {
  models: ModelOption[];
  selectedModel: string;
  onSelectModel: (modelId: string) => void;
  agentModels: AgentModels;
  onAgentModelChange: (agent: keyof AgentModels, modelId: string) => void;
  disabled?: boolean;
}

/* =========================
   COMPONENT
========================= */

export function ModelSelector({
  models,
  selectedModel,
  onSelectModel,
  agentModels,
  onAgentModelChange,
  disabled = false,
}: ModelSelectorProps) {

  // Helper to get model object by ID
  const getModel = (id: string) => models.find((m) => m.id === id);

  return (
    <div className="w-full space-y-4">
      {/* PRIMARY MODEL SELECTION */}
      <div className="space-y-2">
        <Label className="text-sm font-medium">Primary Model (Default)</Label>
        <Select
          value={selectedModel}
          onValueChange={onSelectModel}
          disabled={disabled}
        >
          <SelectTrigger className="w-full h-12">
            <SelectValue placeholder="Select a model" />
          </SelectTrigger>
          <SelectContent>
            {models.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                <div className="flex items-center gap-2">
                  {model.type === "cloud" ? (
                    <Cloud className="w-4 h-4 text-blue-500" />
                  ) : (
                    <Cpu className="w-4 h-4 text-purple-500" />
                  )}
                  <span className="font-medium">{model.name}</span>
                  <span className="text-xs text-muted-foreground ml-2">
                    ({model.speed}, {model.cost})
                  </span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {getModel(selectedModel)?.description || "Select the main AI model for the crew."}
        </p>
      </div>

      {/* ADVANCED CONFIGURATION */}
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="advanced-models" className="border-none">
          <AccordionTrigger className="text-xs text-muted-foreground hover:no-underline py-2">
            <div className="flex items-center gap-2">
              <Settings2 className="w-3 h-3" />
              <span>Advanced: Configure Agents Individually</span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-2 pb-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-muted/30 p-4 rounded-lg border border-border">
              {Object.keys(agentModels).map((agentKey) => {
                const agent = agentKey as keyof AgentModels;
                // Determine label based on agent key
                const label = agent.charAt(0).toUpperCase() + agent.slice(1).replace("_", " ");

                return (
                  <div key={agent} className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{label} Agent</Label>
                    <Select
                      value={agentModels[agent]}
                      onValueChange={(val) => onAgentModelChange(agent, val)}
                      disabled={disabled}
                    >
                      <SelectTrigger className="h-9 text-xs bg-background">
                        <SelectValue placeholder="Default" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="default">
                          <span className="text-muted-foreground">Use Primary Model</span>
                        </SelectItem>
                        {models.map((model) => (
                          <SelectItem key={model.id} value={model.id} className="text-xs">
                            {model.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                );
              })}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
