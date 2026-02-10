"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, X, Trash2, History, ChevronRight, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  useSidebar,
} from "@/components/ui/sidebar";

interface TaskHistoryItem {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  model: string;
  created_at: string;
  prompt: string;
}

export function HistorySidebar() {
  const router = useRouter();
  const { open, setOpen, isMobile } = useSidebar();
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Fetch history when sidebar is opened or component mounts (if already open)
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

  const getStatusColor = (status: TaskHistoryItem["status"]) => {
    switch (status) {
      case "running":
        return "text-blue-500 bg-blue-500/10 border-blue-500/20";
      case "completed":
        return "text-green-500 bg-green-500/10 border-green-500/20";
      case "paused":
        return "text-yellow-500 bg-yellow-500/10 border-yellow-500/20";
      case "failed":
        return "text-red-500 bg-red-500/10 border-red-500/20";
      default:
        return "text-muted-foreground bg-muted border-border";
    }
  };

  return (
    <Sidebar side="left" variant="inset" collapsible="icon">
      <SidebarHeader className="border-b border-border p-4 bg-background pl-0">
        <div className="flex items-center justify-between pl-4">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-purple-500" />
            <span className="text-sm font-bold tracking-wider group-data-[collapsible=icon]:hidden">
              HISTORY
            </span>
          </div>
          {/* Close button for mobile or if we want explicit close */}
          {(isMobile || open) && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setOpen(false)}
              className="h-6 w-6 md:hidden"
            >
              <X className="w-4 h-4" />
            </Button>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        <ScrollArea className="h-full">
          <div className="p-2 space-y-2 group-data-[collapsible=icon]:p-0">
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : history.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm group-data-[collapsible=icon]:hidden">
                No history found
              </div>
            ) : (
              history.map((item) => (
                <div
                  key={item.task_id}
                  onClick={() => {
                    router.push(`/workspace?taskId=${item.task_id}`);
                    if (isMobile) setOpen(false);
                  }}
                  className="w-full flex flex-col gap-2 p-3 rounded-lg border border-border bg-card hover:bg-muted/50 transition-colors text-left group cursor-pointer relative overflow-hidden group-data-[collapsible=icon]:p-2 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:justify-center"
                  title={item.prompt} // Tooltip for collapsed state
                >
                  <div className="flex items-center justify-between w-full">
                    {/* Status Badge */}
                    <Badge
                      variant="outline"
                      className={`text-[10px] uppercase ${getStatusColor(
                        item.status
                      )} group-data-[collapsible=icon]:w-2 group-data-[collapsible=icon]:h-2 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:rounded-full group-data-[collapsible=icon]:text-transparent`}
                    >
                      {item.status}
                    </Badge>

                    {/* Meta info - Hidden when collapsed */}
                    <div className="flex items-center gap-2 group-data-[collapsible=icon]:hidden">
                      <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-red-500 hover:bg-red-500/10"
                        onClick={(e) => handleDelete(e, item.task_id)}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>

                  {/* Prompt Text - Hidden when collapsed */}
                  <p className="text-sm font-medium line-clamp-2 leading-snug pr-2 group-data-[collapsible=icon]:hidden">
                    {item.prompt || "No prompt description"}
                  </p>

                  {/* Footer - Hidden when collapsed */}
                  <div className="flex items-center justify-between w-full mt-1 group-data-[collapsible=icon]:hidden">
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {item.model}
                    </span>
                    <ChevronRight className="w-3 h-3 text-muted-foreground group-hover:text-purple-500 transition-colors" />
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </SidebarContent>
    </Sidebar>
  );
}
