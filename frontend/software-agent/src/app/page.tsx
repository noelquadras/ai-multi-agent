'use client';

import Link from "next/link";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Bot, Zap, Code2, ArrowRight, Terminal, Loader2, CheckCircle, AlertCircle, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";

// Types for API responses
interface CrewRequest {
  prompt: string;
  max_iterations?: number;
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

interface CrewResponse {
  success: boolean;
  task_id?: string;
  message: string;
  result?: any;
  error?: string;
  timestamp: string;
}

interface TaskStatus {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress?: number;
  logs?: string[];
  result?: any;
  error?: string;
}

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [apiStatus, setApiStatus] = useState<"idle" | "checking" | "online" | "offline">("idle");

  // Check API health on component mount
  useEffect(() => {
    checkApiHealth();
  }, []);

  // Poll task status if task is running
  useEffect(() => {
    let interval: NodeJS.Timeout;
    
    if (taskId && taskStatus?.status === "running") {
      interval = setInterval(() => {
        fetchTaskStatus(taskId);
      }, 2000); // Poll every 2 seconds
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [taskId, taskStatus?.status]);

  const checkApiHealth = async () => {
    setApiStatus("checking");
    try {
      const response = await fetch("http://localhost:8000/api/health");
      if (response.ok) {
        setApiStatus("online");
      } else {
        setApiStatus("offline");
      }
    } catch (error) {
      setApiStatus("offline");
    }
  };

  const handleRunCrew = async () => {
    if (!prompt.trim()) {
      alert("Please describe the application you want to build");
      return;
    }

    if (apiStatus !== "online") {
      alert("Backend API is not available. Please start the FastAPI server first.");
      return;
    }

    setIsRunning(true);
    setTaskId(null);
    setTaskStatus(null);
    setLogs([]);

    try {
      const request: CrewRequest = {
        prompt: prompt.trim(),
        max_iterations: 3,
        model: "mistral:7b-instruct",
        temperature: 0.2,
        max_tokens: 1200
      };

      const response = await fetch("http://localhost:8000/api/run-crew", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });

      const data: CrewResponse = await response.json();

      if (data.success && data.task_id) {
        setTaskId(data.task_id);
        // Start polling for status
        setTimeout(() => fetchTaskStatus(data.task_id!), 1000);
      } else {
        throw new Error(data.message || "Failed to start crew");
      }
    } catch (error: any) {
      console.error("Error starting crew:", error);
      setLogs(prev => [...prev, `Error: ${error.message}`]);
      setIsRunning(false);
    }
  };

  const fetchTaskStatus = async (id: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/task/${id}`);
      const data: TaskStatus = await response.json();
      
      setTaskStatus(data);
      
      // Update logs
      if (data.logs) {
        setLogs(data.logs);
      }
      
      // If task is completed or failed, stop running state
      if (data.status === "completed" || data.status === "failed") {
        setIsRunning(false);
      }
    } catch (error) {
      console.error("Error fetching task status:", error);
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setPrompt(e.target.value);
  };

  const renderStatusBadge = () => {
    switch (apiStatus) {
      case "online":
        return (
          <Badge className="bg-green-500/20 text-green-400 border-green-500/30">
            <div className="w-2 h-2 rounded-full bg-green-500 mr-2"></div>
            API Online
          </Badge>
        );
      case "offline":
        return (
          <Badge className="bg-red-500/20 text-red-400 border-red-500/30">
            <div className="w-2 h-2 rounded-full bg-red-500 mr-2"></div>
            API Offline
          </Badge>
        );
      case "checking":
        return (
          <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30">
            <Loader2 className="w-3 h-3 animate-spin mr-2" />
            Checking API...
          </Badge>
        );
      default:
        return null;
    }
  };

  const renderTaskStatus = () => {
    if (!taskStatus) return null;

    switch (taskStatus.status) {
      case "pending":
        return (
          <div className="flex items-center text-yellow-400">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            Preparing to start...
          </div>
        );
      case "running":
        return (
          <div className="space-y-2">
            <div className="flex items-center text-blue-400">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              AI Crew working... ({taskStatus.progress || 0}%)
            </div>
            {taskStatus.progress && (
              <div className="w-full bg-gray-800 rounded-full h-2">
                <div 
                  className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${taskStatus.progress}%` }}
                ></div>
              </div>
            )}
          </div>
        );
      case "completed":
        return (
          <div className="flex items-center text-green-400">
            <CheckCircle className="w-4 h-4 mr-2" />
            Completed successfully!
          </div>
        );
      case "failed":
        return (
          <div className="flex items-center text-red-400">
            <AlertCircle className="w-4 h-4 mr-2" />
            Failed: {taskStatus.error || "Unknown error"}
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <main className="min-h-screen bg-[#050505] text-white overflow-hidden relative selection:bg-purple-500/30">
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 flex items-center justify-between px-6 py-4 md:px-12 bg-transparent backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <span className="font-semibold text-lg tracking-tight">Autonomous <span className="text-muted-foreground">AI</span></span>
        </div>
        <div className="flex items-center gap-4">
          {renderStatusBadge()}
          <Button 
            variant="ghost" 
            size="sm"
            onClick={checkApiHealth}
            disabled={apiStatus === "checking"}
            className="text-gray-400 hover:text-white"
          >
            <RefreshCw className={`w-3 h-3 mr-2 ${apiStatus === "checking" ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button variant="secondary" className="bg-[#1A1A1A] hover:bg-[#252525] text-white border border-[#333] rounded-md h-9 px-4">
            Sign In
          </Button>
        </div>
      </nav>

      {/* Background Gradients */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-150 bg-purple-900/20 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-125 h-125 bg-indigo-900/10 blur-[100px] rounded-full pointer-events-none" />

      <div className="relative z-10 flex flex-col items-center justify-center pt-32 pb-20 px-4">
        {/* Version Badge */}
        <div className="mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#110C1D] border border-purple-500/30 text-xs font-medium text-purple-300 shadow-[0_0_15px_rgba(168,85,247,0.15)]">
            <Zap className="w-3 h-3 fill-purple-300" />
            V2.0 AUTONOMOUS ENGINEERING ENGINE
          </div>
        </div>

        {/* Hero Title */}
        <h1 className="text-center text-6xl md:text-8xl font-bold tracking-tight mb-6 leading-[1.1]">
          Autonomous<br />
          <span className="text-transparent bg-clip-text bg-linear-to-r from-purple-400 to-indigo-400">
            AI Software Team
          </span>
        </h1>

        {/* Subtitle */}
        <p className="text-center text-lg text-zinc-400 max-w-2xl mb-12 leading-relaxed">
          A Lovable-style AI app builder powered by an autonomous software engineering team. From planning to deployment, fully automated.
        </p>

        {/* API Status Warning */}
        {apiStatus === "offline" && (
          <div className="mb-6 p-4 bg-red-900/30 border border-red-800 rounded-lg max-w-2xl w-full">
            <div className="flex items-start">
              <AlertCircle className="w-5 h-5 text-red-400 mr-3 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium text-red-300">Backend API is offline</p>
                <p className="text-sm text-red-400/80 mt-1">
                  Please start the FastAPI server in your terminal:
                </p>
                <code className="block mt-2 p-2 bg-black/50 rounded text-sm font-mono">
                  uvicorn app:app --reload --port 8000
                </code>
              </div>
            </div>
          </div>
        )}

        {/* Task Status Display */}
        {taskStatus && (
          <div className="mb-6 p-4 bg-gray-900/50 border border-gray-800 rounded-lg max-w-2xl w-full">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold">Crew Execution Status</h3>
              {renderTaskStatus()}
            </div>
            
            {/* Progress Bar */}
            {taskStatus.progress !== undefined && (
              <div className="mb-3">
                <div className="flex justify-between text-sm text-gray-400 mb-1">
                  <span>Progress</span>
                  <span>{taskStatus.progress}%</span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-2">
                  <div 
                    className="bg-linear-to-r from-purple-500 to-indigo-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${taskStatus.progress}%` }}
                  ></div>
                </div>
              </div>
            )}
            
            {/* Live Logs */}
            {logs.length > 0 && (
              <div className="mt-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-400">Live Logs</span>
                  <span className="text-xs text-gray-500">{logs.length} entries</span>
                </div>
                <div className="max-h-48 overflow-y-auto bg-black/30 rounded p-3">
                  {logs.slice(-10).map((log, index) => (
                    <div key={index} className="font-mono text-xs text-gray-300 py-1 border-b border-gray-800/50 last:border-0">
                      {log}
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Results Preview */}
            {taskStatus.status === "completed" && taskStatus.result && (
              <div className="mt-4 p-3 bg-green-900/20 border border-green-800/50 rounded">
                <div className="flex items-center text-green-400 mb-2">
                  <CheckCircle className="w-4 h-4 mr-2" />
                  <span className="font-medium">Results Ready!</span>
                </div>
                <p className="text-sm text-gray-300">
                  Code generated: {taskStatus.result.refined_code?.length || 0} characters
                </p>
                <div className="mt-2 flex gap-2">
                  <Button 
                    size="sm" 
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => {
                      if (taskStatus.result) {
                        console.log("Full results:", taskStatus.result);
                        alert("Check browser console for full results");
                      }
                    }}
                  >
                    View Results
                  </Button>
                  <Link href="/workspace">
                    <Button size="sm" variant="outline" className="border-gray-700">
                      Open Workspace
                    </Button>
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Input Card */}
        <div className="w-full max-w-3xl relative group">
          <div className="absolute -inset-0.5 bg-linear-to-r from-purple-500/20 to-indigo-500/20 rounded-2xl blur opacity-75 group-hover:opacity-100 transition duration-1000"></div>
          <div className="relative bg-[#0A0A0A] border border-[#1F1F1F] rounded-2xl p-4 shadow-2xl">
            <div className="min-h-50 relative">
              <Textarea
                onChange={handleTextareaChange} 
                placeholder="Describe the application you want to build..."
                className="w-full h-full min-h-45 bg-transparent border-none resize-none text-lg text-zinc-300 placeholder:text-zinc-600 focus-visible:ring-0 p-4"
                disabled={isRunning}
                value={prompt}
              />
            </div>

            <div className="flex items-center justify-between border-t border-[#1F1F1F] pt-4 mt-2 px-2">
              <div className="flex gap-4 text-xs text-zinc-500 font-mono">
                <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#151515]">
                  <Code2 className="w-3 h-3" /> Next.js 15
                </span>
                <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#151515]">
                  <Zap className="w-3 h-3" /> AI-Powered
                </span>
              </div>
              <div className="flex gap-3">
                {isRunning ? (
                  <Button disabled className="bg-zinc-800 text-zinc-400 font-medium rounded-lg px-4 py-2 flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Running Crew...
                  </Button>
                ) : (
                  <Button 
                    onClick={handleRunCrew}
                    disabled={!prompt.trim() || apiStatus !== "online"}
                    className="bg-zinc-100 hover:bg-white text-black font-medium rounded-lg px-4 py-2 flex items-center gap-2 transition-all hover:shadow-[0_0_20px_rgba(255,255,255,0.3)] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Build with AI Team
                    <ArrowRight className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Instructions */}
        <div className="mt-8 max-w-2xl w-full">
          <div className="p-4 bg-gray-900/30 border border-gray-800 rounded-lg">
            <h4 className="font-medium text-gray-300 mb-2">How it works:</h4>
            <ol className="text-sm text-gray-400 space-y-2 list-decimal list-inside">
              <li>Describe your application in natural language</li>
              <li>Click "Build with AI Team" to deploy autonomous agents</li>
              <li>Watch as AI agents plan, code, review, and refine</li>
              <li>Get production-ready code with documentation</li>
            </ol>
          </div>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl w-full mt-24">
          <FeatureCard
            icon={<Bot className="w-6 h-6 text-purple-400" />}
            title="Autonomous Planning"
            description="Agents collaborate to architect your solution before writing a single line of code."
          />
          <FeatureCard
            icon={<Zap className="w-6 h-6 text-indigo-400" />}
            title="Self-Healing Tests"
            description="Integrated testers and debuggers catch and fix issues in real-time."
          />
          <FeatureCard
            icon={<Terminal className="w-6 h-6 text-blue-400" />}
            title="Transparent Logs"
            description="Complete visibility into every decision made by the autonomous team."
          />
        </div>
      </div>
    </main>
  );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode, title: string, description: string }) {
  return (
    <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-[#1F1F1F] hover:border-purple-500/20 transition-colors group">
      <div className="w-12 h-12 rounded-lg bg-[#110C1D] flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
        {icon}
      </div>
      <h3 className="text-xl font-semibold mb-2 text-zinc-100">{title}</h3>
      <p className="text-zinc-500 leading-relaxed text-sm">
        {description}
      </p>
    </div>
  );
}