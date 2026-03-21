"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { Terminal as TerminalIcon } from "lucide-react";

const TerminalComponent = dynamic(
  () => import("@/components/Terminal").then((mod) => mod.Terminal),
  { ssr: false }
);

export default function TerminalPage() {
  useEffect(() => {
    document.title = "Terminal - AI Software Crew";
  }, []);

  return (
    <div className="h-screen w-screen bg-[#1a1b26] overflow-hidden flex flex-col">
      <div className="h-9 bg-card border-b border-border flex items-center justify-between px-4 text-xs text-muted-foreground select-none">
        <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <TerminalIcon className="w-3.5 h-3.5" />
            <span>Terminal Session</span>
        </div>
        <div className="text-muted-foreground/60">
            Popped out Mode
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <TerminalComponent className="h-full w-full" />
      </div>
    </div>
  );
}
