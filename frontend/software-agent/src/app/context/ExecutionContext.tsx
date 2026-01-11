"use client";

import { createContext, useContext, useState, useRef, ReactNode } from "react";

/* 1. Types should usually be exported if they are used in other files */
export type TaskEvent =
  | { type: "agent_start"; agent: string; timestamp: string }
  | { type: "agent_end"; agent: string; timestamp: string }
  | { type: "tool_start"; agent: string; tool: string; timestamp: string }
  | { type: "tool_error"; agent: string; tool: string; error: string; timestamp: string }
  | { type: "system_error"; error: string; timestamp: string }
  | { type: "log"; message: string; timestamp: string };

interface ExecutionContextType {
  prompt: string;
  setPrompt: (v: string) => void;
  taskId: string | null;
  events: TaskEvent[];
  isRunning: boolean;
  startSubscription: (taskId: string) => void;
}

const ExecutionContext = createContext<ExecutionContextType | null>(null);

export function ExecutionProvider({ children }: { children: ReactNode }) {
  const [prompt, setPrompt] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  // Reference for the SSE connection
  const eventSourceRef = useRef<EventSource | null>(null);

  const startSubscription = (id: string) => {
    // Close existing connection if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setTaskId(id);
    setIsRunning(true);
    setEvents([]); // Clear old logs

    const es = new EventSource(`http://localhost:8000/api/task/${id}/events`);

    es.onmessage = (e) => {
      const event: TaskEvent = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);
    };

    es.onerror = () => {
      es.close();
      setIsRunning(false);
    };

    eventSourceRef.current = es;
  };

  return (
    <ExecutionContext.Provider 
      value={{ 
        prompt, 
        setPrompt, 
        taskId, 
        events, 
        isRunning, 
        startSubscription 
      }}
    >
      {children}
    </ExecutionContext.Provider>
  );
}

export function useExecution() {
  const ctx = useContext(ExecutionContext);
  if (!ctx) throw new Error("useExecution must be used within an ExecutionProvider");
  return ctx;
}