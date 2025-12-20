'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { AgentPanel } from "@/components/workspace/AgentPanel";
import { CodeWorkspace } from "@/components/workspace/CodeWorkspace";
import { ActivityPanel } from "@/components/workspace/ActivityPanel";
import { PreviewPanel } from "@/components/workspace/PreviewPanel";
import { Box, Play, Share2, Settings, Loader2, CheckCircle, AlertCircle, Code, FileText, Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
// import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

interface CrewResult {
  generated_code?: string;
  review_report?: string;
  decision?: string;
  refined_code?: string;
  documentation?: string;
}

interface TaskStatus {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress?: number;
  logs?: string[];
  result?: CrewResult;
  error?: string;
}

export default function WorkspacePage() {
  const searchParams = useSearchParams();
  const taskId = searchParams.get('task_id');
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('code');
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");
  const [logs, setLogs] = useState<string[]>([]);

  // Check API health on mount
  useEffect(() => {
    checkApiHealth();
  }, []);

  // Load task status if taskId exists
  useEffect(() => {
    if (taskId) {
      fetchTaskStatus(taskId);
    } else {
      setLoading(false);
    }
  }, [taskId]);

  // Poll task status if it's running
  useEffect(() => {
    let interval: NodeJS.Timeout;
    
    if (taskId && taskStatus?.status === "running") {
      interval = setInterval(() => {
        fetchTaskStatus(taskId);
      }, 2000);
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [taskId, taskStatus?.status]);

  const checkApiHealth = async () => {
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

  const fetchTaskStatus = async (id: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/task/${id}`);
      const data: TaskStatus = await response.json();
      setTaskStatus(data);
      
      // Update logs
      if (data.logs) {
        setLogs(data.logs);
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching task status:', error);
      setLoading(false);
    }
  };

  const refreshTaskStatus = () => {
    if (taskId) {
      fetchTaskStatus(taskId);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const renderStatusBadge = () => {
    if (!taskStatus) return null;

    switch (taskStatus.status) {
      case "pending":
        return (
          <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30">
            <Loader2 className="w-3 h-3 animate-spin mr-2" />
            PENDING
          </Badge>
        );
      case "running":
        return (
          <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
            <Loader2 className="w-3 h-3 animate-spin mr-2" />
            RUNNING ({taskStatus.progress || 0}%)
          </Badge>
        );
      case "completed":
        return (
          <Badge className="bg-green-500/20 text-green-400 border-green-500/30">
            <CheckCircle className="w-3 h-3 mr-2" />
            COMPLETED
          </Badge>
        );
      case "failed":
        return (
          <Badge className="bg-red-500/20 text-red-400 border-red-500/30">
            <AlertCircle className="w-3 h-3 mr-2" />
            FAILED
          </Badge>
        );
      default:
        return null;
    }
  };

  const renderApiStatusBadge = () => {
    switch (apiStatus) {
      case "online":
        return (
          <Badge className="bg-green-500/20 text-green-400 border-green-500/30">
            <div className="w-2 h-2 rounded-full bg-green-500 mr-2"></div>
            API ONLINE
          </Badge>
        );
      case "offline":
        return (
          <Badge className="bg-red-500/20 text-red-400 border-red-500/30">
            <div className="w-2 h-2 rounded-full bg-red-500 mr-2"></div>
            API OFFLINE
          </Badge>
        );
      case "checking":
        return (
          <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30">
            <Loader2 className="w-3 h-3 animate-spin mr-2" />
            CHECKING...
          </Badge>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[#050505]">
      {/* Global Header */}
      <header className="h-16 flex-none flex items-center justify-between px-6 border-b border-[#1F1F1F] bg-[#0A0A0A]">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-purple-600 flex items-center justify-center">
              <Box className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white tracking-widest uppercase">Nexus Core</h1>
              <p className="text-[10px] text-zinc-500 font-medium">Workspace</p>
            </div>
          </div>

          <div className="h-8 w-[1px] bg-[#1F1F1F]" />

          <div className="flex flex-col">
            <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Active Construct</span>
            <span className="text-xs text-zinc-300 font-medium">
              {taskStatus ? `Task: ${taskStatus.task_id.substring(0, 8)}...` : 'No Active Task'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* Status Indicators */}
          <div className="flex items-center gap-3">
            {renderApiStatusBadge()}
            {taskStatus && renderStatusBadge()}
            
            {taskStatus && (
              <Button
                variant="ghost"
                size="sm"
                onClick={refreshTaskStatus}
                className="text-gray-400 hover:text-white h-8 w-8 p-0"
                title="Refresh Status"
              >
                <RefreshCw className="w-3 h-3" />
              </Button>
            )}
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#110C1D] border border-purple-500/30">
            <div className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
            <span className="text-[10px] font-bold text-purple-300 tracking-wider">
              {taskStatus?.status === 'running' ? 'AGENTS WORKING' : 'INTELLIGENCE SYNCHRONIZED'}
            </span>
          </div>

          <div className="flex items-center gap-4 text-zinc-500">
            <Share2 className="w-4 h-4 hover:text-white cursor-pointer transition-colors" />
            <Settings className="w-4 h-4 hover:text-white cursor-pointer transition-colors" />
          </div>

          <Button className="bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs tracking-wide px-4 h-9 flex items-center gap-2">
            <Play className="w-3 h-3 fill-current" />
            Initiate Deployment
          </Button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Agents */}
        <div className="flex-none hidden md:block">
          <AgentPanel taskStatus={taskStatus} />
        </div>

        {/* Center/Right Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Top: Editor and Preview */}
          <div className="flex-1 flex min-h-0 bg-[#0A0A0A]">
            {/* Editor Area with Tabs */}
            <div className="flex-1 min-w-0 flex flex-col">
              {/* Task Status Bar */}
              {taskStatus && (
                <div className="flex-none border-b border-[#1F1F1F] bg-[#0F0F0F] p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-gray-400 font-mono">
                        Task ID: {taskStatus.task_id}
                      </span>
                      {taskStatus.progress !== undefined && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400">Progress:</span>
                          <div className="w-32 bg-gray-800 rounded-full h-1.5">
                            <div 
                              className="bg-gradient-to-r from-purple-500 to-indigo-500 h-1.5 rounded-full transition-all duration-300"
                              style={{ width: `${taskStatus.progress}%` }}
                            ></div>
                          </div>
                          <span className="text-xs text-gray-300 w-8">{taskStatus.progress}%</span>
                        </div>
                      )}
                    </div>
                    
                    {taskStatus.result && (
                      <div className="flex gap-2">
                        {taskStatus.result.refined_code && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => copyToClipboard(taskStatus.result!.refined_code!)}
                            className="border-gray-700 h-7 text-xs"
                          >
                            <Copy className="w-3 h-3 mr-1" />
                            Copy Code
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Content Tabs */}
              {/* <div className="flex-1 flex flex-col min-h-0">
                <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                  <div className="flex-none border-b border-[#1F1F1F]">
                    <TabsList className="bg-transparent p-2">
                      <TabsTrigger value="code" className="data-[state=active]:bg-gray-900">
                        <Code className="w-3 h-3 mr-2" />
                        Generated Code
                      </TabsTrigger>
                      <TabsTrigger value="review" className="data-[state=active]:bg-gray-900">
                        <AlertCircle className="w-3 h-3 mr-2" />
                        Review Report
                      </TabsTrigger>
                      <TabsTrigger value="docs" className="data-[state=active]:bg-gray-900">
                        <FileText className="w-3 h-3 mr-2" />
                        Documentation
                      </TabsTrigger>
                    </TabsList>
                  </div>

                  <TabsContent value="code" className="flex-1 p-0 overflow-auto">
                    {loading ? (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                          <Loader2 className="w-8 h-8 animate-spin text-gray-600 mx-auto mb-4" />
                          <p className="text-gray-400">Loading generated code...</p>
                        </div>
                      </div>
                    ) : taskStatus?.result ? (
                      <div className="h-full">
                        <CodeWorkspace 
                          code={taskStatus.result.refined_code || taskStatus.result.generated_code || ''}
                          isReadOnly={true}
                        />
                      </div>
                    ) : taskStatus?.error ? (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center p-6">
                          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
                          <h3 className="text-lg font-semibold text-red-400 mb-2">Error Loading Code</h3>
                          <p className="text-gray-400 text-sm max-w-md">
                            {taskStatus.error}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center p-6">
                          <Code className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                          <h3 className="text-lg font-semibold text-gray-300 mb-2">No Code Generated</h3>
                          <p className="text-gray-400 text-sm">
                            Run a crew from the home page to generate code
                          </p>
                        </div>
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="review" className="flex-1 p-6 overflow-auto">
                    {loading ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="w-8 h-8 animate-spin text-gray-600" />
                      </div>
                    ) : taskStatus?.result ? (
                      <div className="space-y-6">
                        <div className="bg-black/30 rounded-lg p-4 border border-gray-800">
                          <h4 className="text-sm font-semibold text-gray-300 mb-3">Code Review Report</h4>
                          <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
                            {taskStatus.result.review_report || 'No review report available'}
                          </pre>
                        </div>
                        
                        <div className="bg-black/30 rounded-lg p-4 border border-gray-800">
                          <h4 className="text-sm font-semibold text-gray-300 mb-3">Refinement Decision</h4>
                          <div className="text-sm text-gray-300">
                            {taskStatus.result.decision || 'No decision recorded'}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                          <AlertCircle className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                          <p className="text-gray-400">No review data available</p>
                        </div>
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="docs" className="flex-1 p-6 overflow-auto">
                    {loading ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="w-8 h-8 animate-spin text-gray-600" />
                      </div>
                    ) : taskStatus?.result ? (
                      <div className="bg-black/30 rounded-lg p-6 border border-gray-800">
                        <h4 className="text-sm font-semibold text-gray-300 mb-4">Generated Documentation</h4>
                        <div className="prose prose-invert max-w-none">
                          <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
                            {taskStatus.result.documentation || 'No documentation generated'}
                          </pre>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                          <FileText className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                          <p className="text-gray-400">No documentation available</p>
                        </div>
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
              </div> */}
            </div>

            {/* Preview Panel (Fixed or Hidden) */}
            <div className="flex-none hidden xl:block border-l border-[#1F1F1F]">
              <PreviewPanel taskStatus={taskStatus} />
            </div>
          </div>

          {/* Bottom: Logs (Fixed height) */}
          <div className="h-72 flex-none">
            <ActivityPanel logs={logs} />
          </div>
        </div>
      </div>
    </div>
  );
}