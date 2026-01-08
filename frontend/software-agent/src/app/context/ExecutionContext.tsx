'use client';

import { createContext, useContext, useState } from "react";

type ExecutionContextType = {
  prompt: string;
  setPrompt: (v: string) => void;
  taskId: string | null;
  setTaskId: (v: string | null) => void;
};

const ExecutionContext = createContext<ExecutionContextType | null>(null);

export function ExecutionProvider({ children }: { children: React.ReactNode }) {
  const [prompt, setPrompt] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);

  return (
    <ExecutionContext.Provider value={{ prompt, setPrompt, taskId, setTaskId }}>
      {children}
    </ExecutionContext.Provider>
  );
}

export function useExecution() {
  const ctx = useContext(ExecutionContext);
  if (!ctx) throw new Error("useExecution must be inside provider");
  return ctx;
}
