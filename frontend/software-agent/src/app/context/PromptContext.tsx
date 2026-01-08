'use client';

import { createContext, useContext, useState } from "react";

type PromptContextType = {
  prompt: string;
  setPrompt: (value: string) => void;
};

const PromptContext = createContext<PromptContextType | null>(null);

export function PromptProvider({ children }: { children: React.ReactNode }) {
  const [prompt, setPrompt] = useState("");

  return (
    <PromptContext.Provider value={{ prompt, setPrompt }}>
      {children}
    </PromptContext.Provider>
  );
}

export function usePrompt() {
  const context = useContext(PromptContext);
  if (!context) {
    throw new Error("usePrompt must be used within PromptProvider");
  }
  return context;
}
