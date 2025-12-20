"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertCircle, CheckCircle, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

interface CodeWorkspaceProps {
  code?: string;
  isReadOnly?: boolean;
  fileStructure?: Record<string, string>;
  onCopyCode?: (code: string) => void;
}

export function CodeWorkspace({ 
  code = '', 
  isReadOnly = false, 
  fileStructure,
  onCopyCode 
}: CodeWorkspaceProps) {
    const [activeFile, setActiveFile] = useState<string>("main.py");
    const [files, setFiles] = useState<Record<string, string>>({});
    const [copied, setCopied] = useState(false);

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
          "main.py": code
        });
        setActiveFile("main.py");
      } else {
        // Default empty files
        setFiles({
          "main.py": "# No code generated yet\n# Run the AI crew to generate code",
          "requirements.txt": "# Dependencies will be listed here",
          "README.md": "# Project documentation will appear here"
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

    const getFileIcon = (fileName: string) => {
        if (fileName.endsWith('.tsx') || fileName.endsWith('.jsx')) return '⚛';
        if (fileName.endsWith('.ts') || fileName.endsWith('.js')) return '{}';
        if (fileName.endsWith('.py')) return '🐍';
        if (fileName.endsWith('.md')) return '📝';
        if (fileName.endsWith('.txt') || fileName.endsWith('.json')) return '📄';
        return '📄';
    };

    const getFileColor = (fileName: string) => {
        if (fileName.endsWith('.tsx') || fileName.endsWith('.jsx')) return 'text-[#61dafb]';
        if (fileName.endsWith('.ts') || fileName.endsWith('.js')) return 'text-[#f1c40f]';
        if (fileName.endsWith('.py')) return 'text-[#3776ab]';
        if (fileName.endsWith('.md')) return 'text-[#74c0fc]';
        return 'text-zinc-400';
    };

    if (!code && Object.keys(files).length === 0) {
        return (
            <Card className="h-full border-none rounded-none border-r border-[#1F1F1F] bg-[#0A0A0A] flex flex-col">
                <CardHeader className="p-4 border-b border-[#1F1F1F] bg-[#0A0A0A]">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-zinc-300">Code Workspace</h3>
                        <Badge variant="outline" className="border-zinc-800 text-zinc-500 text-[10px]">
                            No Code
                        </Badge>
                    </div>
                </CardHeader>
                <CardContent className="flex-1 flex items-center justify-center">
                    <div className="text-center p-8">
                        <CodeIcon className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
                        <h3 className="text-lg font-semibold text-zinc-300 mb-2">No Code Generated</h3>
                        <p className="text-zinc-500 text-sm max-w-sm">
                            Run the AI crew from the home page to generate code for your application.
                        </p>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="h-full border-none rounded-none border-r border-[#1F1F1F] bg-[#0A0A0A] flex flex-col">
            <CardHeader className="p-0 border-b border-[#1F1F1F] bg-[#0A0A0A] flex flex-row items-center justify-between h-[3.2rem]">
                {/* File Tabs */}
                <div className="flex h-full overflow-x-auto scrollbar-thin">
                    {Object.keys(files).map((fileName) => (
                        <button
                            key={fileName}
                            onClick={() => setActiveFile(fileName)}
                            className={`
                px-4 text-sm border-r border-[#1F1F1F] flex items-center gap-2 h-full transition-colors font-medium whitespace-nowrap
                ${activeFile === fileName
                                    ? "bg-[#141414] text-white border-t-2 border-t-blue-500"
                                    : "bg-[#0A0A0A] text-[#666] hover:bg-[#111] hover:text-zinc-300"}
              `}
                        >
                            <span className={`${getFileColor(fileName)}`}>
                                {getFileIcon(fileName)}
                            </span>
                            {fileName}
                        </button>
                    ))}
                </div>

                {/* Status/Label */}
                <div className="px-4 flex items-center gap-3">
                    {files[activeFile] && files[activeFile].length > 0 && (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleCopyCode}
                            className="h-7 px-2 text-xs text-zinc-400 hover:text-white"
                        >
                            <Copy className="w-3 h-3 mr-1" />
                            {copied ? 'Copied!' : 'Copy'}
                        </Button>
                    )}
                    
                    <Badge variant="outline" className="border-purple-500/20 bg-purple-500/10 text-purple-400 text-[10px] font-bold px-2 py-0.5 rounded-sm">
                        AI-GENERATED
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="flex-1 p-0 overflow-hidden">
                <div className="h-full relative">
                    <pre className="h-full p-4 overflow-auto bg-[#141414] text-sm font-mono text-zinc-300 whitespace-pre-wrap">
                        <code className="block min-h-full">
                            {files[activeFile] || "# File is empty"}
                        </code>
                    </pre>
                    
                    {/* Line numbers */}
                    <div className="absolute left-0 top-0 bottom-0 w-12 bg-[#0A0A0A]/50 border-r border-[#1F1F1F] text-right pr-2 text-xs text-zinc-600 font-mono overflow-hidden">
                        {files[activeFile]?.split('\n').map((_, i) => (
                            <div key={i} className="leading-6">{i + 1}</div>
                        ))}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

function CodeIcon({ className }: { className?: string }) {
    return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
    );
}