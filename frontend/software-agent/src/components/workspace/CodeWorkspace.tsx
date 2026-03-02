"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  AlertCircle,
  CheckCircle,
  Copy,
  CodeIcon,
  Play,
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
  onCopyCode?: (code: string) => void;
}

export function CodeWorkspace({
  code = "",
  isReadOnly = false,
  codeFiles = [],
  onCopyCode,
}: CodeWorkspaceProps) {
  const [activeFile, setActiveFile] = useState<string>("");
  const [copied, setCopied] = useState(false);

  // When codeFiles change, auto-select the latest version
  useEffect(() => {
    if (codeFiles.length > 0) {
      const latest = codeFiles[codeFiles.length - 1];
      setActiveFile(latest.filename);
    } else if (code) {
      setActiveFile("code.py");
    }
  }, [codeFiles, code]);

  // Build the display list: either codeFiles or fallback to code prop
  const displayFiles: CodeFile[] =
    codeFiles.length > 0
      ? codeFiles
      : code
        ? [{ filename: "code.py", content: code }]
        : [];

  const activeContent =
    displayFiles.find((f) => f.filename === activeFile)?.content || "";

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
    if (fileName.endsWith(".tsx") || fileName.endsWith(".jsx")) return "⚛";
    if (fileName.endsWith(".ts") || fileName.endsWith(".js")) return "{}";
    if (fileName.endsWith(".py")) return "🐍";
    if (fileName.endsWith(".md")) return "📝";
    if (fileName.endsWith(".txt") || fileName.endsWith(".json")) return "📄";
    return "📄";
  };

  const getFileColor = (fileName: string) => {
    if (fileName.endsWith(".tsx") || fileName.endsWith(".jsx"))
      return "text-[#61dafb]";
    if (fileName.endsWith(".ts") || fileName.endsWith(".js"))
      return "text-[#f1c40f]";
    if (fileName.endsWith(".py")) return "text-[#3776ab]";
    if (fileName.endsWith(".md")) return "text-[#74c0fc]";
    return "text-zinc-400";
  };

  if (displayFiles.length === 0) {
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
            </button>
          ))}
        </div>

        {/* Status / Label */}
        <div className="px-4 flex items-center gap-3">
          {activeContent && activeContent.length > 0 && (
            <>
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
            className="border-primary/20 bg-primary/10 text-primary text-[10px] font-bold px-2 py-0.5 rounded-sm"
          >
            AI-GENERATED
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 p-0 overflow-hidden">
        <div className="h-full overflow-auto bg-muted text-sm font-mono">
          <div className="min-w-fit">
            {(activeContent || "# File is empty").split("\n").map((line, i) => (
              <div key={i} className="flex hover:bg-muted-foreground/5">
                <div className="shrink-0 w-12 bg-muted border-r border-border text-right pr-3 select-none sticky left-0 text-muted-foreground z-10 h-auto">
                  {i + 1}
                </div>
                <pre className="grow pl-4 text-foreground whitespace-pre-wrap font-mono break-all py-[0.1rem]">
                  {line || " "}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </CardContent>


    </Card>
  );
}

