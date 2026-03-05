"use client";

import { useEffect, useRef } from "react";
import {
  Terminal,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  ChevronRight,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { TerminalCommandRecord } from "@/hooks/useTerminalCommands";

interface CLIPanelProps {
  /** Legacy string logs (from SSE events) */
  logs: string[];
  /** Legacy test results string */
  testResults?: string;
  /** Structured command records from the terminal-commands WebSocket */
  commandRecords?: TerminalCommandRecord[];
}

export function CLIPanel({ logs, testResults, commandRecords = [] }: CLIPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, testResults, commandRecords]);

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

  const getStatusIcon = (record: TerminalCommandRecord) => {
    switch (record.status) {
      case "running":
        return <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin shrink-0" />;
      case "success":
        return <CheckCircle className="w-3.5 h-3.5 text-green-500 shrink-0" />;
      case "error":
        return <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />;
      case "timeout":
        return <Clock className="w-3.5 h-3.5 text-yellow-500 shrink-0" />;
    }
  };

  const getStatusBadge = (record: TerminalCommandRecord) => {
    const colors: Record<string, string> = {
      running: "bg-blue-500/20 text-blue-400 border-blue-500/30",
      success: "bg-green-500/20 text-green-400 border-green-500/30",
      error: "bg-red-500/20 text-red-400 border-red-500/30",
      timeout: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    };
    const labels: Record<string, string> = {
      running: "RUNNING",
      success: `EXIT ${record.exitCode}`,
      error: `EXIT ${record.exitCode}`,
      timeout: "TIMEOUT",
    };
    return (
      <span
        className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${colors[record.status]}`}
      >
        {labels[record.status]}
      </span>
    );
  };

  const hasCommands = commandRecords.length > 0;
  const isEmpty = logs.length === 0 && !testResults && !hasCommands;

  return (
    <div className="w-100 h-full bg-card flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-green-500" />
            <h3 className="text-sm font-semibold text-foreground">
              CLI Output
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {hasCommands && (
              <Badge variant="outline" className="text-[10px] border-border">
                {commandRecords.length} cmd{commandRecords.length !== 1 ? "s" : ""}
              </Badge>
            )}
            {status && (
              <Badge className={`${status.color} bg-opacity-20`}>
                <status.icon className="w-3 h-3 mr-1" />
                {status.label}
              </Badge>
            )}
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Commands executed by agents and their results
        </p>
      </div>

      {/* Terminal Output */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-auto p-4 bg-muted font-mono text-xs"
      >
        {isEmpty ? (
          <div className="text-muted-foreground flex items-center gap-2">
            <span className="text-green-500">$</span>
            <span className="animate-pulse">Waiting for command execution...</span>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Structured command records */}
            {commandRecords.map((record) => (
              <div
                key={record.id}
                className="rounded-md border border-border/50 bg-background/50 overflow-hidden"
              >
                {/* Command header */}
                <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 border-b border-border/30">
                  {getStatusIcon(record)}
                  <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
                  <code className="text-foreground flex-1 truncate">
                    {record.command}
                  </code>
                  {getStatusBadge(record)}
                </div>

                {/* Command output */}
                {record.output && (
                  <pre className="px-3 py-2 text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground max-h-48 overflow-auto">
                    {record.output}
                  </pre>
                )}

                {/* Running indicator */}
                {record.status === "running" && !record.output && (
                  <div className="px-3 py-2 text-blue-400/70 text-[11px] flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Executing...
                  </div>
                )}
              </div>
            ))}

            {/* Legacy string logs */}
            {logs.map((log, index) => (
              <div key={`log-${index}`} className="flex">
                <span className="text-green-500 mr-2 select-none">$</span>
                <span
                  className={`${log.startsWith("✅")
                      ? "text-green-500"
                      : log.startsWith("❌")
                        ? "text-red-500"
                        : log.startsWith("⏱️")
                          ? "text-yellow-500"
                          : "text-foreground"
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
          <div className="mt-4 pt-4 border-t border-border">
            <div className="text-muted-foreground mb-2">
              --- Test Summary ---
            </div>
            <pre className="whitespace-pre-wrap text-foreground">
              {testResults}
            </pre>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-border bg-card">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            {hasCommands
              ? `${commandRecords.filter((c) => c.status !== "running").length}/${commandRecords.length} completed`
              : `${logs.length} log${logs.length !== 1 ? "s" : ""}`}
          </span>
          <span className="text-muted-foreground font-mono">
            sandbox://powershell
          </span>
        </div>
      </div>
    </div>
  );
}
