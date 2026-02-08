"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { History, ChevronRight, Clock, Loader2, X, Trash2 } from "lucide-react";

interface TaskHistoryItem {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  model: string;
  created_at: string;
  prompt: string;
}

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function HistorySidebar({ isOpen, onClose }: HistorySidebarProps) {
  const router = useRouter();
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
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
  }, [isOpen]);

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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-80 bg-background border-l border-border shadow-2xl z-50 transform transition-transform duration-300 ease-in-out">
      <Card className="h-full border-none rounded-none bg-transparent flex flex-col">
        <CardHeader className="flex flex-row items-center justify-between pb-4 pt-5 px-5 border-b border-border space-y-0">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-purple-500" />
            <CardTitle className="text-sm font-bold tracking-wider">
              HISTORY
            </CardTitle>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8">
            <X className="w-4 h-4" />
          </Button>
        </CardHeader>

        <CardContent className="p-0 flex-1 min-h-0">
          <ScrollArea className="h-full">
            <div className="p-4 space-y-3">
              {loading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : history.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  No history found
                </div>
              ) : (
                history.map((item) => (
                  <div
                    key={item.task_id}
                    onClick={() => {
                      router.push(`/workspace?taskId=${item.task_id}`);
                      onClose();
                    }}
                    className="w-full flex flex-col gap-2 p-3 rounded-lg border border-border bg-card hover:bg-muted/50 transition-colors text-left group cursor-pointer relative"
                  >
                    <div className="flex items-center justify-between w-full">
                      <Badge
                        variant="outline"
                        className={`text-[10px] uppercase ${getStatusColor(
                          item.status
                        )}`}
                      >
                        {item.status}
                      </Badge>
                      <div className="flex items-center gap-2">
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

                    <p className="text-sm font-medium line-clamp-2 leading-snug pr-2">
                      {item.prompt || "No prompt description"}
                    </p>

                    <div className="flex items-center justify-between w-full mt-1">
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
        </CardContent>
      </Card>
    </div>
  );
}
