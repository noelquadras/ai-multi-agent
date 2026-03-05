"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  AlertCircle,
  CheckCircle,
  Copy,
  CodeIcon,
  Play,
  FileSearch,
  ClipboardList,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface CodeFile {
  filename: string;
  content: string;
}

interface CodeWorkspaceProps {
  code?: string;
  isReadOnly?: boolean;
  codeFiles?: CodeFile[];
  specFile?: CodeFile | null;
  reviewFile?: CodeFile | null;
  streamingFile?: string | null;
  streamingContent?: string;
  onCopyCode?: (code: string) => void;
}

export function CodeWorkspace({
  code = "",
  isReadOnly = false,
  codeFiles = [],
  specFile = null,
  reviewFile = null,
  streamingFile = null,
  streamingContent = "",
  onCopyCode,
}: CodeWorkspaceProps) {
  const [activeFile, setActiveFile] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  // When codeFiles change, auto-select the latest version
  useEffect(() => {
    // Don't override if we're streaming
    if (streamingFile) return;
    if (codeFiles.length > 0) {
      const latest = codeFiles[codeFiles.length - 1];
      setActiveFile(latest.filename);
    } else if (code) {
      setActiveFile("code.py");
    }
  }, [codeFiles, code, streamingFile]);

  // Auto-select the streaming tab when streaming starts
  useEffect(() => {
    if (streamingFile) {
      setActiveFile(streamingFile);
    }
  }, [streamingFile]);

  // Auto-scroll to bottom while streaming
  useEffect(() => {
    if (streamingFile && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [streamingContent, streamingFile]);

  // Build the display list: code files + spec/review as separate "meta" files
  const displayFiles: CodeFile[] = [
    ...(codeFiles.length > 0
      ? [...codeFiles].reverse()
      : code
        ? [{ filename: "code.py", content: code }]
        : []),
    ...(specFile ? [specFile] : []),
    ...(reviewFile ? [reviewFile] : []),
  ];

  // Determine active content — prefer streaming if the streaming tab is active
  const isStreamingActive = streamingFile && activeFile === streamingFile;
  const activeContent = isStreamingActive
    ? streamingContent
    : displayFiles.find((f) => f.filename === activeFile)?.content || "";

  // Show the streaming tab in the tab list
  const showStreamingTab =
    streamingFile &&
    !displayFiles.some((f) => f.filename === streamingFile);

  const handleCopyCode = () => {
    navigator.clipboard.writeText(activeContent);
    if (onCopyCode) {
      onCopyCode(activeContent);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRunCode = async () => {
    const runFilename = activeFile || "code.py";
    let command = "";
    if (runFilename.endsWith(".py")) {
      command = `python -u ${runFilename}`;
    } else if (runFilename.endsWith(".js")) {
      command = `node ${runFilename}`;
    } else if (runFilename.endsWith(".ts") || runFilename.endsWith(".tsx")) {
      command = `npx ts-node ${runFilename}`;
    } else {
      return;
    }

    try {
      await fetch("http://localhost:8000/api/terminal/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command,
          save_code: activeContent,
          filename: runFilename,
        }),
      });
    } catch (e) {
      console.error("Failed to run code:", e);
    }
  };

  const getFileIcon = (fileName: string) => {
    if (fileName === "spec.md") return "📋";
    if (fileName === "review.md") return "🔍";
    if (fileName === "generating...") return "⚡";
    if (fileName.endsWith(".tsx") || fileName.endsWith(".jsx")) return "⚛";
    if (fileName.endsWith(".ts") || fileName.endsWith(".js")) return "{}";
    if (fileName.endsWith(".py")) return "🐍";
    if (fileName.endsWith(".md")) return "📝";
    if (fileName.endsWith(".txt") || fileName.endsWith(".json")) return "📄";
    return "📄";
  };

  const getFileColor = (fileName: string) => {
    if (fileName === "spec.md") return "text-[#34d399]";
    if (fileName === "review.md") return "text-[#fbbf24]";
    if (fileName === "generating...") return "text-[#818cf8]";
    if (fileName.endsWith(".tsx") || fileName.endsWith(".jsx"))
      return "text-[#61dafb]";
    if (fileName.endsWith(".ts") || fileName.endsWith(".js"))
      return "text-[#f1c40f]";
    if (fileName.endsWith(".py")) return "text-[#3776ab]";
    if (fileName.endsWith(".md")) return "text-[#74c0fc]";
    return "text-zinc-400";
  };

  const isCodeFile = (fileName: string) => {
    return fileName.endsWith(".py") || fileName.endsWith(".js") || fileName.endsWith(".ts") || fileName.endsWith(".tsx");
  };

  if (displayFiles.length === 0 && !streamingFile) {
    return (
      <Card className="h-full border-none rounded-none border-r border-border bg-card flex flex-col">
        <CardHeader className="p-4 border-b border-border bg-card">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              Code Workspace
            </h3>
            <Badge
              variant="outline"
              className="border-border text-muted-foreground text-[10px]"
            >
              No Code
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="flex-1 flex items-center justify-center">
          <div className="text-center p-8">
            <CodeIcon className="w-12 h-12 text-muted-foreground/50 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">
              No Code Generated
            </h3>
            <p className="text-muted-foreground text-sm max-w-sm">
              Run the AI crew from the home page to generate code for your
              application.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full border-none rounded-none border-r border-border bg-card flex flex-col">
      <CardHeader className="p-0 border-b border-border bg-card flex flex-row items-center justify-between h-[3.2rem]">
        {/* File Tabs */}
        <div className="flex h-full overflow-x-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
          {/* Streaming tab (shown when a stream is active and doesn't match an existing file) */}
          {showStreamingTab && (
            <button
              onClick={() => setActiveFile(streamingFile!)}
              className={`
                    px-4 text-sm border-r border-border flex items-center gap-2 h-full transition-colors font-medium whitespace-nowrap
                    ${activeFile === streamingFile
                  ? "bg-muted text-foreground border-t-2 border-t-indigo-500"
                  : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground"
                }
                  `}
            >
              <span className={getFileColor(streamingFile!)}>
                {getFileIcon(streamingFile!)}
              </span>
              {streamingFile}
              <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
            </button>
          )}

          {displayFiles.map((file) => (
            <button
              key={file.filename}
              onClick={() => setActiveFile(file.filename)}
              className={`
                    px-4 text-sm border-r border-border flex items-center gap-2 h-full transition-colors font-medium whitespace-nowrap
                    ${activeFile === file.filename
                  ? "bg-muted text-foreground border-t-2 border-t-blue-500"
                  : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground"
                }
                  `}
            >
              <span className={getFileColor(file.filename)}>
                {getFileIcon(file.filename)}
              </span>
              {file.filename}
              {/* Show pulsing dot on files that are currently being streamed into */}
              {streamingFile === file.filename && (
                <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
              )}
            </button>
          ))}
        </div>

        {/* Status / Label */}
        <div className="px-4 flex items-center gap-3">
          {activeContent && activeContent.length > 0 && (
            <>
              {isCodeFile(activeFile) && !isStreamingActive && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRunCode()}
                  className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground mr-1"
                  title="Run in Terminal"
                >
                  <Play className="w-3 h-3 mr-1" />
                  Run
                </Button>
              )}

              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopyCode}
                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
              >
                <Copy className="w-3 h-3 mr-1" />
                {copied ? "Copied!" : "Copy"}
              </Button>
            </>
          )}

          <Badge
            variant="outline"
            className={`text-[10px] font-bold px-2 py-0.5 rounded-sm ${isStreamingActive
              ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-400"
              : activeFile === "spec.md"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                : activeFile === "review.md"
                  ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
                  : "border-primary/20 bg-primary/10 text-primary"
              }`}
          >
            {isStreamingActive
              ? "STREAMING..."
              : activeFile === "spec.md"
                ? "SPEC"
                : activeFile === "review.md"
                  ? "REVIEW"
                  : "AI-GENERATED"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 p-0 overflow-hidden">
        <div ref={contentRef} className="h-full overflow-auto bg-muted text-sm font-mono">
          <div className="min-w-fit">
            {(activeContent || "# File is empty").split("\n").map((line, i) => (
              <div key={i} className="flex hover:bg-muted-foreground/5">
                <div className="shrink-0 w-12 bg-muted border-r border-border text-right pr-3 select-none sticky left-0 text-muted-foreground z-10 h-auto">
                  {i + 1}
                </div>
                <pre className="grow pl-4 text-foreground whitespace-pre-wrap font-mono break-all py-[0.1rem]">
                  {line || " "}
                  {/* Blinking cursor on the last line while streaming */}
                  {isStreamingActive &&
                    i === (activeContent || "").split("\n").length - 1 && (
                      <span className="inline-block w-2 h-4 bg-indigo-400 animate-pulse ml-0.5 align-middle rounded-sm" />
                    )}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </CardContent>


    </Card>
  );
}
