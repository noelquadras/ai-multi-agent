"use client";

import { useEffect, useRef } from "react";
import { Terminal, CheckCircle, XCircle, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface CLIPanelProps {
  logs: string[];
  testResults?: string;
}

export function CLIPanel({ logs, testResults }: CLIPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, testResults]);

  const getTestStatus = () => {
    if (!testResults) return null;
    if (testResults.includes("✅ Test PASSED")) {
      return { icon: CheckCircle, color: "text-green-500", label: "PASSED" };
    }
    if (testResults.includes("❌ Test FAILED")) {
      return { icon: XCircle, color: "text-red-500", label: "FAILED" };
    }
    if (testResults.includes("⏱️ Test TIMEOUT")) {
      return { icon: Clock, color: "text-yellow-500", label: "TIMEOUT" };
    }
    return null;
  };

  const status = getTestStatus();

  return (
    <div className="w-[400px] h-full bg-[#0A0A0A] flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#1F1F1F]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-green-500" />
            <h3 className="text-sm font-semibold text-zinc-300">CLI Test Output</h3>
          </div>
          {status && (
            <Badge className={`${status.color} bg-opacity-20`}>
              <status.icon className="w-3 h-3 mr-1" />
              {status.label}
            </Badge>
          )}
        </div>
        <p className="text-xs text-zinc-500 mt-1">
          Sandboxed execution results from the tester agent
        </p>
      </div>

      {/* Terminal Output */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-auto p-4 bg-[#0d1117] font-mono text-xs"
      >
        {/* Command History */}
        {logs.length === 0 && !testResults ? (
          <div className="text-zinc-600 flex items-center gap-2">
            <span className="text-green-500">$</span>
            <span className="animate-pulse">Waiting for test execution...</span>
          </div>
        ) : (
          <div className="space-y-2">
            {logs.map((log, index) => (
              <div key={index} className="flex">
                <span className="text-green-500 mr-2 select-none">$</span>
                <span
                  className={`${
                    log.startsWith("✅")
                      ? "text-green-400"
                      : log.startsWith("❌")
                      ? "text-red-400"
                      : log.startsWith("⏱️")
                      ? "text-yellow-400"
                      : "text-zinc-300"
                  }`}
                >
                  {log}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Test Results */}
        {testResults && (
          <div className="mt-4 pt-4 border-t border-[#2d333b]">
            <div className="text-zinc-500 mb-2">--- Test Summary ---</div>
            <pre className="whitespace-pre-wrap text-zinc-300">{testResults}</pre>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-[#1F1F1F] bg-[#0A0A0A]">
        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-500">
            {logs.length} command{logs.length !== 1 ? "s" : ""} executed
          </span>
          <span className="text-zinc-600 font-mono">sandbox://python3</span>
        </div>
      </div>
    </div>
  );
}
