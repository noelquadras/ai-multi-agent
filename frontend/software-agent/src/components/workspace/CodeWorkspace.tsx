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
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface CodeWorkspaceProps {
  code?: string;
  isReadOnly?: boolean;
  fileStructure?: Record<string, string>;
  onCopyCode?: (code: string) => void;
}

export function CodeWorkspace({
  code = "",
  isReadOnly = false,
  fileStructure,
  onCopyCode,
}: CodeWorkspaceProps) {
  const [activeFile, setActiveFile] = useState<string>("code.py");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [copied, setCopied] = useState(false);

  const [showRunDialog, setShowRunDialog] = useState(false);
  const [executionPath, setExecutionPath] = useState("./temp_run");

  useEffect(() => {
    // Initialize files from props
    if (fileStructure) {
      setFiles(fileStructure);
      const firstFile = Object.keys(fileStructure)[0];
      if (firstFile) {
        setActiveFile(firstFile);
      }
    } else if (code) {
      // If only code is provided, create a single file
      setFiles({
        "code.py": code,
      });
      setActiveFile("code.py");
    } else {
      // Default empty files
      setFiles({
        "code.py":
          "# No code generated yet\n# Run the AI crew to generate code",
        "requirements.txt": "# Dependencies will be listed here",
        "README.md": "# Project documentation will appear here",
      });
    }
  }, [code, fileStructure]);

  const handleCopyCode = () => {
    const currentCode = files[activeFile];
    navigator.clipboard.writeText(currentCode);
    if (onCopyCode) {
      onCopyCode(currentCode);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRunCode = async (cwd?: string) => {
    let command = "";
    if (activeFile.endsWith(".py")) {
      command = `python ${activeFile}`;
    } else if (activeFile.endsWith(".js")) {
      command = `node ${activeFile}`;
    } else if (activeFile.endsWith(".ts") || activeFile.endsWith(".tsx")) {
      command = `npx ts-node ${activeFile}`;
    } else {
      return; // file type not supported for direct run
    }

    try {
      await fetch("http://localhost:8000/api/terminal/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command,
          save_code: files[activeFile],
          filename: activeFile,
          cwd: cwd || "."
        }),
      });
    } catch (e) {
      console.error("Failed to run code:", e);
    }
  };

  const initiateRun = () => {
    setShowRunDialog(true);
  };

  const confirmRun = () => {
    setShowRunDialog(false);
    handleRunCode(executionPath);
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

  if (!code && Object.keys(files).length === 0) {
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
        <div className="flex h-full overflow-x-auto scrollbar-thin">
          {Object.keys(files).map((fileName) => (
            <button
              key={fileName}
              onClick={() => setActiveFile(fileName)}
              className={`
                    px-4 text-sm border-r border-border flex items-center gap-2 h-full transition-colors font-medium whitespace-nowrap
                    ${activeFile === fileName
                  ? "bg-muted text-foreground border-t-2 border-t-blue-500"
                  : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground"
                }
                  `}
            >
              <span className={getFileColor(fileName)}>
                {getFileIcon(fileName)}
              </span>
              {fileName}
            </button>
          ))}
        </div>

        {/* Status / Label */}
        <div className="px-4 flex items-center gap-3">
          {files[activeFile] && files[activeFile].length > 0 && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={initiateRun}
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
        <div className="h-full relative">
          <pre className="h-full p-4 overflow-auto bg-muted text-sm font-mono text-foreground whitespace-pre-wrap">
            <code className="block min-h-full">
              {files[activeFile] || "# File is empty"}
            </code>
          </pre>

          {/* Line numbers */}
          <div className="absolute left-0 top-0 bottom-0 w-12 bg-card/50 border-r border-border text-right pr-2 text-xs text-muted-foreground font-mono overflow-hidden">
            {files[activeFile]?.split("\n").map((_, i) => (
              <div key={i} className="leading-6">
                {i + 1}
              </div>
            ))}
          </div>
        </div>
      </CardContent>

      {/* Run Configuration Modal */}
      {showRunDialog && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between py-3 border-b border-border">
              <h3 className="text-sm font-semibold">Run Configuration</h3>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setShowRunDialog(false)}
              >
                <X className="w-4 h-4" />
              </Button>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="execution-path" className="text-xs">
                  Execution Directory
                </Label>
                <Input
                  id="execution-path"
                  value={executionPath}
                  onChange={(e) => setExecutionPath(e.target.value)}
                  placeholder="./temp_run"
                  className="h-8 text-sm font-mono"
                />
                <p className="text-[10px] text-muted-foreground">
                  Specify a directory to run the code. Using a separate directory prevents the server from reloading.
                </p>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowRunDialog(false)}
                  className="h-8"
                >
                  Cancel
                </Button>
                <Button size="sm" onClick={confirmRun} className="h-8">
                  <Play className="w-3 h-3 mr-2" />
                  Run Code
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </Card>
  );
}
