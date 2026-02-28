"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { useTheme } from "@/hooks/useTheme";
import {
  Loader2,
  Trash2,
  History,
  Clock,
  Bot,
  CheckCircle2,
  Circle,
  AlertCircle,
  Code,
  FileCheck,
  Users,
  Wrench,
  Terminal,
  FileText,
  Bug,
  Sun,
  Moon,
  LogIn,
  Wifi,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { UserMenu } from "@/components/auth/UserMenu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";

/* =========================
   TYPES
========================= */

interface TaskHistoryItem {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  model: string;
  created_at: string;
  prompt: string;
}

export interface SidebarAgent {
  id: string;
  name: string;
  role: string;
  status: "idle" | "thinking" | "approved" | "error";
  message?: string;
}

/* =========================
   HELPERS
========================= */

const roleIcons: Record<string, React.ReactNode> = {
  Developer: <Code className="w-4 h-4" />,
  "QA Engineer": <FileCheck className="w-4 h-4" />,
  Auditor: <Users className="w-4 h-4" />,
  Refactoring: <Wrench className="w-4 h-4" />,
  "CLI Testing": <Terminal className="w-4 h-4" />,
  Documentation: <FileText className="w-4 h-4" />,
  "Terminal Analysis": <Bug className="w-4 h-4" />,
  Planner: <Users className="w-4 h-4" />,
  Manager: <Users className="w-4 h-4" />,
  Architect: <Code className="w-4 h-4" />,
};

function getRelativeTime(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return `${Math.floor(diffDays / 7)}w ago`;
}

function getStatusIcon(status: SidebarAgent["status"]) {
  switch (status) {
    case "thinking":
      return <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />;
    case "approved":
      return <CheckCircle2 className="w-3 h-3 text-green-500" />;
    case "error":
      return <AlertCircle className="w-3 h-3 text-red-500" />;
    default:
      return <Circle className="w-2.5 h-2.5 text-zinc-600" />;
  }
}

/* =========================
   COMPONENT
========================= */

interface HistorySidebarProps {
  agents?: SidebarAgent[];
  apiStatus?: "checking" | "online" | "offline";
}

export function HistorySidebar({ agents, apiStatus }: HistorySidebarProps) {
  const router = useRouter();
  const { open, setOpen, isMobile } = useSidebar();
  const { data: session, status: sessionStatus } = useSession();
  const { toggleTheme } = useTheme();
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  const activeCount =
    agents?.filter((a) => a.status === "thinking").length ?? 0;

  useEffect(() => {
    if (open) {
      setLoading(true);
      fetch("http://localhost:8000/api/history")
        .then((res) => res.json())
        .then((data) => {
          setHistory(data);
          setLoading(false);
        })
        .catch((err) => {
          console.error("Failed to load history:", err);
          setLoading(false);
        });
    }
  }, [open]);

  const handleDelete = async (e: React.MouseEvent, taskId: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this task?")) return;

    try {
      const res = await fetch(`http://localhost:8000/api/task/${taskId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setHistory((prev) => prev.filter((item) => item.task_id !== taskId));
      } else {
        console.error("Failed to delete task");
      }
    } catch (error) {
      console.error("Error deleting task:", error);
    }
  };

  return (
    <Sidebar side="left" variant="sidebar" collapsible="offcanvas">
      {/* ── Header ── */}
      <SidebarHeader className="border-b border-border px-3 py-3">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="Home">
              <Link href="/">
                <div className="w-8 h-8 bg-gradient-to-br from-purple-600 to-blue-600 rounded-lg flex items-center justify-center shrink-0">
                  <Bot className="text-white w-4 h-4" />
                </div>
                <div className="flex flex-col gap-0.5 leading-none">
                  <span className="font-semibold text-sm">Multi-Agent AI</span>
                  <span className="text-[10px] text-muted-foreground">
                    Software Team
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      {/* ── Agents Section ── */}
      <SidebarContent>
        {agents && agents.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
              <span className="flex items-center gap-2">
                Agents
                {activeCount > 0 && (
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    <span className="text-green-500">{activeCount}</span>
                  </span>
                )}
              </span>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {agents.map((agent) => (
                  <SidebarMenuItem key={agent.id}>
                    <SidebarMenuButton
                      tooltip={`${agent.name} — ${agent.status}`}
                      className={cn(
                        "h-auto py-2",
                        agent.status === "thinking" &&
                        "bg-purple-500/5 border border-purple-500/20"
                      )}
                    >
                      {/* Role Icon */}
                      <div
                        className={cn(
                          "w-7 h-7 rounded-md flex items-center justify-center shrink-0 border",
                          agent.status === "thinking"
                            ? "bg-purple-500/10 border-purple-500/30 text-purple-500"
                            : "bg-muted border-border text-muted-foreground"
                        )}
                      >
                        {roleIcons[agent.role] || (
                          <Bot className="w-4 h-4" />
                        )}
                      </div>

                      {/* Name + Status */}
                      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                        <span
                          className={cn(
                            "text-xs font-medium truncate",
                            agent.status === "thinking"
                              ? "text-foreground"
                              : "text-muted-foreground"
                          )}
                        >
                          {agent.name}
                        </span>
                        <span className="flex items-center gap-1">
                          {getStatusIcon(agent.status)}
                          <span
                            className={cn(
                              "text-[9px] uppercase font-bold tracking-wider",
                              agent.status === "thinking" && "text-blue-500",
                              agent.status === "approved" && "text-green-500",
                              agent.status === "error" && "text-red-500",
                              agent.status === "idle" && "text-zinc-500"
                            )}
                          >
                            {agent.status}
                          </span>
                        </span>
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* ── History ── */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
            <History className="w-3 h-3 mr-1" />
            History
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <ScrollArea className="max-h-[280px]">
              <SidebarMenu>
                {loading ? (
                  <div className="flex justify-center py-4">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  </div>
                ) : history.length === 0 ? (
                  <div className="text-center py-4 text-muted-foreground text-[11px] group-data-[collapsible=icon]:hidden">
                    No history yet
                  </div>
                ) : (
                  history.map((item) => (
                    <SidebarMenuItem key={item.task_id}>
                      <SidebarMenuButton
                        tooltip={item.prompt || "Task"}
                        className="h-auto py-1.5"
                        onClick={() => {
                          router.push(`/workspace?taskId=${item.task_id}`);
                          if (isMobile) setOpen(false);
                        }}
                      >
                        {/* Status dot */}
                        <div
                          className={cn(
                            "w-2 h-2 rounded-full shrink-0",
                            item.status === "running" && "bg-blue-500 animate-pulse",
                            item.status === "completed" && "bg-green-500",
                            item.status === "paused" && "bg-yellow-500",
                            item.status === "failed" && "bg-red-500",
                            item.status === "pending" && "bg-zinc-500"
                          )}
                        />
                        {/* Prompt + time */}
                        <div className="flex flex-col gap-0 min-w-0 flex-1">
                          <span className="text-xs font-medium truncate leading-tight">
                            {item.prompt || "Untitled task"}
                          </span>
                          <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                            <Clock className="w-2.5 h-2.5" />
                            {getRelativeTime(item.created_at)}
                          </span>
                        </div>
                      </SidebarMenuButton>
                      <SidebarMenuAction
                        showOnHover
                        onClick={(e) => handleDelete(e as React.MouseEvent, item.task_id)}
                        className="text-muted-foreground hover:text-red-500"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </SidebarMenuAction>
                    </SidebarMenuItem>
                  ))
                )}
              </SidebarMenu>
            </ScrollArea>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* ── Footer: API Status + Theme + Auth ── */}
      <SidebarFooter className="border-t border-border">
        <SidebarMenu>
          {/* API Status */}
          {apiStatus && (
            <SidebarMenuItem>
              <SidebarMenuButton
                tooltip={`API ${apiStatus}`}
                className="h-8 cursor-default"
              >
                {apiStatus === "online" ? (
                  <Wifi className="w-4 h-4 text-green-500 shrink-0" />
                ) : apiStatus === "offline" ? (
                  <WifiOff className="w-4 h-4 text-red-500 shrink-0" />
                ) : (
                  <Loader2 className="w-4 h-4 text-yellow-500 animate-spin shrink-0" />
                )}
                <span
                  className={cn(
                    "text-xs font-medium",
                    apiStatus === "online" && "text-green-500",
                    apiStatus === "offline" && "text-red-500",
                    apiStatus === "checking" && "text-yellow-500"
                  )}
                >
                  {apiStatus === "online"
                    ? "API Online"
                    : apiStatus === "offline"
                      ? "API Offline"
                      : "Checking..."}
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}

          {/* Theme Toggle */}
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="Toggle theme"
              onClick={toggleTheme}
              className="h-8"
            >
              <Sun className="w-4 h-4 dark:hidden shrink-0" />
              <Moon className="w-4 h-4 hidden dark:block shrink-0" />
              <span className="text-xs">
                <span className="dark:hidden">Light Mode</span>
                <span className="hidden dark:inline">Dark Mode</span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>

          <SidebarSeparator />

          {/* User / Auth */}
          <SidebarMenuItem>
            {sessionStatus === "authenticated" ? (
              <div className="px-2 py-1 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:justify-center">
                <UserMenu />
              </div>
            ) : sessionStatus === "unauthenticated" ? (
              <SidebarMenuButton
                tooltip="Sign In"
                onClick={() => router.push("/auth/signin")}
                className="h-8"
              >
                <LogIn className="w-4 h-4 shrink-0" />
                <span className="text-xs">Sign In</span>
              </SidebarMenuButton>
            ) : null}
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
