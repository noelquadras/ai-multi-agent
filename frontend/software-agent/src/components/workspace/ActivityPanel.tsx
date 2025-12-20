'use client';

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Terminal, Vote, History, RefreshCw, AlertCircle, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";

interface ActivityPanelProps {
  logs?: string[];
  taskStatus?: {
    status: string;
    progress?: number;
  };
  onRefresh?: () => void;
}

export function ActivityPanel({ logs = [], taskStatus, onRefresh }: ActivityPanelProps) {
  const [activeTab, setActiveTab] = useState<'logs' | 'votes' | 'history'>('logs');
  const [filteredLogs, setFilteredLogs] = useState<string[]>([]);

  useEffect(() => {
    // Filter and categorize logs
    const formattedLogs = logs.map(log => {
      // Remove timestamps from log formatting
      return log.replace(/^\[\d{2}:\d{2}:\d{2}\] /, '');
    });
    setFilteredLogs(formattedLogs);
  }, [logs]);

  const parseAgentFromLog = (log: string) => {
    if (log.includes('[Manager]') || log.includes('Manager:')) return { name: 'Manager', color: 'text-pink-500' };
    if (log.includes('[Planner]') || log.includes('Planner:')) return { name: 'Planner', color: 'text-green-500' };
    if (log.includes('[Coder]') || log.includes('Coder:')) return { name: 'Coder', color: 'text-blue-400' };
    if (log.includes('[Debugger]') || log.includes('Debugger:')) return { name: 'Debugger', color: 'text-yellow-500' };
    if (log.includes('[Tester]') || log.includes('Tester:')) return { name: 'Tester', color: 'text-purple-400' };
    if (log.includes('[Reviewer]') || log.includes('Reviewer:')) return { name: 'Reviewer', color: 'text-orange-500' };
    if (log.includes('[Refiner]') || log.includes('Refiner:')) return { name: 'Refiner', color: 'text-teal-500' };
    if (log.includes('[ERROR]') || log.toLowerCase().includes('error')) return { name: 'System', color: 'text-red-500' };
    return { name: 'System', color: 'text-zinc-500' };
  };

  const getStatusIcon = () => {
    if (!taskStatus) return <Loader2 className="w-3 h-3 animate-spin" />;
    
    switch (taskStatus.status) {
      case 'running':
        return <Loader2 className="w-3 h-3 animate-spin text-blue-500" />;
      case 'completed':
        return <CheckCircle className="w-3 h-3 text-green-500" />;
      case 'failed':
        return <XCircle className="w-3 h-3 text-red-500" />;
      default:
        return <AlertCircle className="w-3 h-3 text-yellow-500" />;
    }
  };

  const getStatusText = () => {
    if (!taskStatus) return 'Loading...';
    
    switch (taskStatus.status) {
      case 'pending':
        return 'Task pending';
      case 'running':
        return `Running (${taskStatus.progress || 0}%)`;
      case 'completed':
        return 'Task completed';
      case 'failed':
        return 'Task failed';
      default:
        return taskStatus.status;
    }
  };

  const getLogEntries = () => {
    if (activeTab !== 'logs') {
      return [
        { timestamp: "14:20:01", agent: "System", color: "text-zinc-500", message: "Voting system will activate after code generation." },
        { timestamp: "14:20:02", agent: "System", color: "text-zinc-500", message: "No voting history available yet." },
      ];
    }

    if (filteredLogs.length === 0) {
      return [
        { timestamp: "--:--:--", agent: "System", color: "text-zinc-500", message: "Waiting for agent logs..." },
      ];
    }

    return filteredLogs.map((log, index) => {
      const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const agentInfo = parseAgentFromLog(log);
      const message = log.replace(/\[.*?\]\s*/, '').replace(/^[A-Za-z]+:\s*/, '');
      
      return {
        timestamp,
        agent: agentInfo.name,
        color: agentInfo.color,
        message
      };
    }).slice(-20); // Show last 20 logs
  };

  return (
    <Card className="h-full border-none rounded-none border-t border-[#1F1F1F] bg-[#050505]">
      <CardHeader className="py-0 px-0 border-b border-[#1F1F1F] flex flex-row items-center justify-between h-10 bg-[#0A0A0A]">
        <div className="flex h-full">
          <button 
            onClick={() => setActiveTab('logs')}
            className={`flex items-center gap-2 px-4 h-full text-[11px] font-bold uppercase tracking-wider transition-colors ${
              activeTab === 'logs' 
                ? 'text-zinc-100 bg-[#050505] border-t-2 border-purple-500' 
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Terminal className="w-3 h-3" /> Agent Logs
            {taskStatus?.status === 'running' && (
              <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse ml-1" />
            )}
          </button>
          <button 
            onClick={() => setActiveTab('votes')}
            className={`flex items-center gap-2 px-4 h-full text-[11px] font-bold uppercase tracking-wider transition-colors ${
              activeTab === 'votes' 
                ? 'text-zinc-100 bg-[#050505] border-t-2 border-purple-500' 
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Vote className="w-3 h-3" /> Voting Results
          </button>
          <button 
            onClick={() => setActiveTab('history')}
            className={`flex items-center gap-2 px-4 h-full text-[11px] font-bold uppercase tracking-wider transition-colors ${
              activeTab === 'history' 
                ? 'text-zinc-100 bg-[#050505] border-t-2 border-purple-500' 
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <History className="w-3 h-3" /> Replacement History
          </button>
        </div>
        
        <div className="flex items-center gap-3 px-4">
          <div className="flex items-center gap-2">
            {getStatusIcon()}
            <span className="text-[11px] text-zinc-400">
              {getStatusText()}
            </span>
          </div>
          
          <Button
            variant="ghost"
            size="sm"
            onClick={onRefresh}
            className="h-7 w-7 p-0 hover:bg-white/5"
            title="Refresh Logs"
          >
            <RefreshCw className="w-3 h-3 text-zinc-500" />
          </Button>
          
          <Badge variant="outline" className="border-zinc-800 text-zinc-500 text-[10px] px-2 py-0.5">
            {filteredLogs.length} logs
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-full px-4 py-3">
          <div className="space-y-1.5 font-mono text-[11px] leading-relaxed">
            {getLogEntries().map((log, index) => (
              <LogEntry
                key={index}
                timestamp={log.timestamp}
                agent={log.agent}
                color={log.color}
                message={log.message}
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function LogEntry({ timestamp, agent, color, message }: { timestamp: string, agent: string, color: string, message: string }) {
  return (
    <div className="flex items-start gap-3 hover:bg-white/5 py-0.5 px-2 rounded -mx-2 transition-colors">
      <span className="text-zinc-600">[{timestamp}]</span>
      <span className={`font-bold ${color}`}>{agent}:</span>
      <span className={color === "text-red-500" ? "text-red-400" : "text-zinc-400"}>{message}</span>
    </div>
  );
}