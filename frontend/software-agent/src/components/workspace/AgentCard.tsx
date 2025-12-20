import { Bot, CheckCircle2, Circle, Clock, AlertCircle, Loader2, AlertTriangle, Code, FileCheck, Bug, Users, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";

interface AgentCardProps {
    name: string;
    role: string;
    status: "Active" | "Idle" | "Thinking" | "Approved" | "Waiting" | "Error";
    confidence: number;
    errors: number;
    statusMessage: string;
    isWorking?: boolean;
    taskProgress?: number;
}

const roleIcons: Record<string, React.ReactNode> = {
  'Planner': <Users className="w-4 h-4" />,
  'Coder': <Code className="w-4 h-4" />,
  'Tester': <FileCheck className="w-4 h-4" />,
  'Debugger': <Bug className="w-4 h-4" />,
  'Reviewer': <AlertTriangle className="w-4 h-4" />,
  'Refiner': <Wrench className="w-4 h-4" />,
  'Manager': <Users className="w-4 h-4" />,
};

export function AgentCard({ name, role, status, confidence, errors, statusMessage, isWorking, taskProgress }: AgentCardProps) {
    const isThinking = status === "Thinking";

    const getStatusIcon = () => {
        switch (status) {
            case "Approved":
                return <CheckCircle2 className="w-3 h-3 text-green-500" />;
            case "Thinking":
                return <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />;
            case "Active":
                return <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />;
            case "Error":
                return <AlertCircle className="w-3 h-3 text-red-500" />;
            case "Waiting":
                return <Clock className="w-3 h-3 text-yellow-500" />;
            default:
                return <Circle className="w-2 h-2 text-zinc-600" />;
        }
    };

    const getStatusColor = () => {
        switch (status) {
            case "Approved":
                return "text-green-500";
            case "Thinking":
                return "text-blue-500";
            case "Active":
                return "text-green-500";
            case "Error":
                return "text-red-500";
            case "Waiting":
                return "text-yellow-500";
            default:
                return "text-zinc-600";
        }
    };

    const getConfidenceColor = (confidence: number) => {
        if (confidence > 90) return "bg-green-500";
        if (confidence > 80) return "bg-blue-500";
        if (confidence > 70) return "bg-yellow-500";
        return "bg-red-500";
    };

    return (
        <div className={cn(
            "w-full rounded-xl border p-4 transition-all duration-200",
            isWorking
                ? "bg-[#110C1D] border-purple-500/30 shadow-[0_0_15px_rgba(168,85,247,0.1)]"
                : "bg-[#0A0A0A] border-[#1F1F1F] opacity-80 hover:opacity-100"
        )}>
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                    <div className={cn(
                        "w-10 h-10 rounded-lg flex items-center justify-center border",
                        isWorking ? "bg-purple-900/20 border-purple-500/30 text-purple-400" : "bg-zinc-900 border-zinc-800 text-zinc-600"
                    )}>
                        {roleIcons[role] || <Bot className="w-5 h-5" />}
                    </div>
                    <div>
                        <h3 className={cn("font-bold text-sm", isWorking ? "text-white" : "text-zinc-400")}>{name}</h3>
                        <div className="flex items-center gap-1.5">
                            {getStatusIcon()}
                            <span className={cn(
                                "text-[10px] uppercase font-bold tracking-wider",
                                getStatusColor()
                            )}>
                                {status}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Error Badge */}
                <div className={cn(
                    "px-2 py-1 rounded text-[10px] font-mono flex items-center gap-1 border",
                    errors > 0 
                        ? "bg-red-900/20 border-red-800/50 text-red-400" 
                        : "bg-zinc-900 border-zinc-800 text-zinc-500"
                )}>
                    {errors} ERR
                </div>
            </div>

            {/* Confidence Bar */}
            <div className="space-y-1.5 mb-3">
                <div className="flex justify-between text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                    <span>Confidence</span>
                    <span className={cn(
                        confidence > 90 ? "text-green-500" :
                            confidence > 80 ? "text-blue-500" :
                            confidence > 70 ? "text-yellow-500" : "text-red-500"
                    )}>{confidence}%</span>
                </div>
                <div className="h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
                    <div
                        className={cn("h-full rounded-full transition-all duration-300", getConfidenceColor(confidence))}
                        style={{ width: `${confidence}%` }}
                    />
                </div>
            </div>

            {/* Task Progress (if provided) */}
            {taskProgress !== undefined && isWorking && (
                <div className="space-y-1.5 mb-3">
                    <div className="flex justify-between text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                        <span>Progress</span>
                        <span className="text-blue-500">{taskProgress}%</span>
                    </div>
                    <div className="h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
                        <div
                            className="h-full rounded-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-300"
                            style={{ width: `${taskProgress}%` }}
                        />
                    </div>
                </div>
            )}

            {/* Footer Message */}
            <div className="text-[11px] text-zinc-500 truncate font-medium">
                {statusMessage}
            </div>
        </div>
    );
}