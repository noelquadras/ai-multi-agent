"use client";

import { useEffect, useRef, useState, useMemo, KeyboardEvent } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Send,
    Bot,
    User,
    Sparkles,
    Loader2,
    MessageSquare,
    Copy,
    Check,
    CornerDownLeft,
    Wrench,
    FileCode,
    FileText,
    TestTube,
    Terminal,
    AlertCircle,
    CheckCircle,
    XCircle,
    Pause,
    Play,
    StopCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { TaskEvent } from "@/components/workspace/ActivityPanel";

/* =========================
   TYPES
========================= */

export interface ChatMessage {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: string;
    agent?: string;
    status?: "sending" | "streaming" | "complete" | "error";
    icon?: React.ReactNode;
    color?: string;
}

interface ChatPanelProps {
    taskId?: string;
    onSendMessage?: (message: string) => void;
    events?: TaskEvent[];
    isLoading?: boolean;
    className?: string;
}

/* =========================
   EVENT → CHAT MESSAGE
========================= */

function eventToChatMessage(event: TaskEvent, index: number): ChatMessage | null {
    const base = {
        id: `evt_${index}_${event.timestamp}`,
        timestamp: event.timestamp,
        status: "complete" as const,
    };

    switch (event.type) {
        case "agent_start":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `started working`,
                icon: <Sparkles className="w-3 h-3 text-blue-400" />,
                color: "text-blue-400",
            };

        case "agent_end":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `completed task`,
                icon: <CheckCircle className="w-3 h-3 text-green-400" />,
                color: "text-green-400",
            };

        case "tool_start":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `Using tool: ${event.tool}`,
                icon: <Wrench className="w-3 h-3 text-purple-400" />,
                color: "text-purple-400",
            };

        case "tool_error":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `⚠️ ${event.tool}: ${event.error}`,
                icon: <AlertCircle className="w-3 h-3 text-red-400" />,
                color: "text-red-400",
            };

        case "system_error":
            return {
                ...base,
                role: "system",
                content: `Error: ${event.error}`,
                icon: <AlertCircle className="w-3 h-3 text-red-500" />,
                color: "text-red-500",
            };

        case "code_output":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `Generated code output:\n\`\`\`\n${event.code.length > 200 ? event.code.slice(0, 200) + "\n..." : event.code}\n\`\`\``,
                icon: <FileCode className="w-3 h-3 text-emerald-400" />,
                color: "text-emerald-400",
            };

        case "review_output":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: event.review,
                icon: <FileText className="w-3 h-3 text-yellow-400" />,
                color: "text-yellow-400",
            };

        case "decision_output":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `Decision: ${event.decision}`,
                icon: <CheckCircle className="w-3 h-3 text-purple-400" />,
                color: "text-purple-400",
            };

        case "doc_output":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: event.documentation.length > 300
                    ? event.documentation.slice(0, 300) + "\n..."
                    : event.documentation,
                icon: <FileText className="w-3 h-3 text-blue-400" />,
                color: "text-blue-400",
            };

        case "test_output":
            return {
                ...base,
                role: "assistant",
                agent: event.agent,
                content: `Test results:\n${event.results}`,
                icon: <TestTube className="w-3 h-3 text-cyan-400" />,
                color: "text-cyan-400",
            };

        case "cli_output":
            return {
                ...base,
                role: "assistant",
                agent: "CLI",
                content: event.message,
                icon: <Terminal className="w-3 h-3 text-green-400" />,
                color: "text-green-400",
            };

        case "task_completed":
            return {
                ...base,
                role: "system",
                content: "✅ Task completed successfully!",
                icon: <CheckCircle className="w-3 h-3 text-green-500" />,
                color: "text-green-500",
            };

        case "task_paused":
            return {
                ...base,
                role: "system",
                content: `⏸️ ${event.message}`,
                icon: <Pause className="w-3 h-3 text-yellow-500" />,
                color: "text-yellow-500",
            };

        case "task_resumed":
            return {
                ...base,
                role: "system",
                content: `▶️ ${event.message}`,
                icon: <Play className="w-3 h-3 text-green-500" />,
                color: "text-green-500",
            };

        case "human_approval":
            return {
                ...base,
                role: "user",
                content: event.message,
                icon: event.approved
                    ? <CheckCircle className="w-3 h-3 text-green-500" />
                    : <XCircle className="w-3 h-3 text-red-500" />,
                color: event.approved ? "text-green-500" : "text-red-500",
            };

        case "task_cancelled":
            return {
                ...base,
                role: "system",
                content: `🛑 ${event.message || "Task cancelled by user"}`,
                icon: <StopCircle className="w-3 h-3 text-orange-500" />,
                color: "text-orange-500",
            };

        case "log":
            // Skip generic log messages to reduce noise — they're visible in the Activity panel
            return null;

        default:
            return null;
    }
}

/* =========================
   HELPERS
========================= */

function formatTime(timestamp: string): string {
    return new Date(timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
    });
}

function generateId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/* =========================
   SUB COMPONENTS
========================= */

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <button
            onClick={handleCopy}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-white/10"
            title="Copy message"
        >
            {copied ? (
                <Check className="w-3 h-3 text-green-400" />
            ) : (
                <Copy className="w-3 h-3 text-muted-foreground" />
            )}
        </button>
    );
}

function TypingIndicator() {
    return (
        <div className="flex items-center gap-3 px-4 py-3">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center shrink-0">
                <Bot className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-card border border-border">
                <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
        </div>
    );
}

function MessageBubble({ message }: { message: ChatMessage }) {
    const isUser = message.role === "user";
    const isSystem = message.role === "system";

    if (isSystem) {
        return (
            <div className="flex justify-center py-2">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/50 border border-border/50">
                    {message.icon || <Sparkles className="w-3 h-3 text-yellow-500" />}
                    <span className="text-[11px] text-muted-foreground">
                        {message.content}
                    </span>
                </div>
            </div>
        );
    }

    return (
        <div
            className={cn(
                "group flex items-end gap-2.5 px-4 py-1.5",
                isUser ? "flex-row-reverse" : "flex-row"
            )}
        >
            {/* Avatar */}
            <div
                className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center shrink-0 shadow-md",
                    isUser
                        ? "bg-gradient-to-br from-blue-500 to-cyan-500"
                        : "bg-gradient-to-br from-purple-500 to-indigo-600"
                )}
            >
                {isUser ? (
                    <User className="w-3.5 h-3.5 text-white" />
                ) : (
                    <Bot className="w-3.5 h-3.5 text-white" />
                )}
            </div>

            {/* Content */}
            <div
                className={cn("flex flex-col gap-1 max-w-[80%]", isUser && "items-end")}
            >
                {/* Agent label + icon */}
                {!isUser && message.agent && (
                    <div className="flex items-center gap-1.5 px-1">
                        {message.icon}
                        <Badge
                            variant="outline"
                            className="text-[9px] px-1.5 py-0 border-purple-500/30 text-purple-400"
                        >
                            {message.agent}
                        </Badge>
                    </div>
                )}

                {/* Bubble */}
                <div
                    className={cn(
                        "relative px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed transition-all",
                        isUser
                            ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-br-md shadow-lg shadow-blue-500/10"
                            : "bg-card border border-border text-foreground rounded-bl-md shadow-sm"
                    )}
                >
                    {/* Message content – respects newlines */}
                    <p className="whitespace-pre-wrap break-words">{message.content}</p>

                    {/* Status indicator for streaming */}
                    {message.status === "streaming" && (
                        <span className="inline-block w-1.5 h-4 bg-purple-400/80 animate-pulse ml-0.5 rounded-sm" />
                    )}
                </div>

                {/* Footer: time + copy */}
                <div
                    className={cn(
                        "flex items-center gap-2 px-1",
                        isUser ? "flex-row-reverse" : "flex-row"
                    )}
                >
                    <span className="text-[10px] text-muted-foreground/60">
                        {formatTime(message.timestamp)}
                    </span>
                    <CopyButton text={message.content} />
                </div>
            </div>
        </div>
    );
}

/* =========================
   MAIN COMPONENT
========================= */

export function ChatPanel({
    taskId,
    onSendMessage,
    events,
    isLoading = false,
    className,
}: ChatPanelProps) {
    const [userMessages, setUserMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [isSending, setIsSending] = useState(false);

    const scrollRef = useRef<HTMLDivElement | null>(null);
    const inputRef = useRef<HTMLTextAreaElement | null>(null);
    const stickToBottomRef = useRef(true);

    /* ---- Convert TaskEvents → ChatMessages ---- */
    const eventMessages = useMemo(() => {
        if (!events) return [];
        return events
            .map((evt, i) => eventToChatMessage(evt, i))
            .filter((msg): msg is ChatMessage => msg !== null);
    }, [events]);

    /* ---- Merge event messages with user-typed messages, sorted by time ---- */
    const messages = useMemo(() => {
        const all = [...eventMessages, ...userMessages];
        all.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
        return all;
    }, [eventMessages, userMessages]);

    /* ---- Auto-scroll ---- */
    useEffect(() => {
        if (!scrollRef.current || !stickToBottomRef.current) return;
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages]);

    const handleScroll = () => {
        if (!scrollRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
        stickToBottomRef.current = scrollHeight - scrollTop - clientHeight < 40;
    };

    /* ---- Auto-resize textarea ---- */
    const handleInputChange = (value: string) => {
        setInput(value);
        if (inputRef.current) {
            inputRef.current.style.height = "auto";
            inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
        }
    };

    /* ---- Send handler ---- */
    const handleSend = async () => {
        const trimmed = input.trim();
        if (!trimmed || isSending) return;

        const userMessage: ChatMessage = {
            id: generateId(),
            role: "user",
            content: trimmed,
            timestamp: new Date().toISOString(),
            status: "complete",
        };

        setUserMessages((prev) => [...prev, userMessage]);

        setInput("");
        if (inputRef.current) {
            inputRef.current.style.height = "auto";
        }

        if (onSendMessage) {
            setIsSending(true);
            try {
                await onSendMessage(trimmed);
            } finally {
                setIsSending(false);
            }
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    /* =========================
       RENDER
    ========================= */

    return (
        <div
            className={cn(
                "flex flex-col h-full bg-background overflow-hidden",
                className
            )}
        >
            {/* ---- Header ---- */}
            <div className="h-10 px-4 flex items-center justify-between border-b border-border bg-card shrink-0">
                <div className="flex items-center gap-2 text-muted-foreground text-xs font-bold">
                    <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                    CHAT
                </div>

                <Badge
                    variant="outline"
                    className="border-border text-muted-foreground text-[10px]"
                >
                    {messages.length} messages
                </Badge>
            </div>

            {/* ---- Messages Area ---- */}
            <div className="flex-1 overflow-hidden">
                <ScrollArea className="h-full">
                    <div
                        ref={scrollRef}
                        onScroll={handleScroll}
                        className="h-full overflow-y-auto py-4 space-y-1"
                    >
                        {/* Empty state */}
                        {messages.length === 0 && (
                            <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-4 text-center px-6">
                                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/20 flex items-center justify-center">
                                    <Sparkles className="w-7 h-7 text-purple-400" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-foreground mb-1">
                                        Start a conversation
                                    </p>
                                    <p className="text-xs text-muted-foreground leading-relaxed max-w-[240px]">
                                        Send a message to interact with your AI agents. They&apos;ll
                                        help you build, review, and refine code.
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* Message list */}
                        {messages.map((msg) => (
                            <MessageBubble key={msg.id} message={msg} />
                        ))}

                        {/* Typing indicator */}
                        {(isLoading || isSending) && <TypingIndicator />}
                    </div>
                </ScrollArea>
            </div>

            {/* ---- Input Area ---- */}
            <div className="shrink-0 border-t border-border bg-card/80 backdrop-blur-sm p-3">
                <div className="flex items-end gap-2 bg-background border border-border rounded-xl px-3 py-2 focus-within:border-purple-500/50 focus-within:ring-1 focus-within:ring-purple-500/20 transition-all">
                    <textarea
                        ref={inputRef}
                        value={input}
                        onChange={(e) => handleInputChange(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Type a message..."
                        rows={1}
                        disabled={isSending}
                        className={cn(
                            "flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50",
                            "resize-none outline-none min-h-[24px] max-h-[120px] py-0.5",
                            "disabled:opacity-50"
                        )}
                    />

                    <div className="flex items-center gap-1 shrink-0">
                        {/* Keyboard hint */}
                        <div className="hidden sm:flex items-center gap-1 text-[10px] text-muted-foreground/40 mr-1">
                            <CornerDownLeft className="w-3 h-3" />
                            <span>Enter</span>
                        </div>

                        <Button
                            size="icon"
                            variant="ghost"
                            onClick={handleSend}
                            disabled={!input.trim() || isSending}
                            className={cn(
                                "h-7 w-7 rounded-lg transition-all",
                                input.trim()
                                    ? "bg-gradient-to-r from-purple-600 to-blue-600 text-white hover:from-purple-500 hover:to-blue-500 shadow-md shadow-purple-500/20"
                                    : "text-muted-foreground"
                            )}
                        >
                            {isSending ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                                <Send className="w-3.5 h-3.5" />
                            )}
                        </Button>
                    </div>
                </div>

                {/* Shift+Enter hint */}
                <p className="text-[10px] text-muted-foreground/30 mt-1.5 px-1">
                    <kbd className="px-1 py-0.5 rounded bg-muted/50 text-[9px] font-mono">
                        Shift + Enter
                    </kbd>{" "}
                    for new line
                </p>
            </div>
        </div>
    );
}
