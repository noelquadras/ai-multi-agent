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
    HelpCircle,
    ChevronRight,
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
    name?: string;
    eventType?: string;
}

interface ChatPanelProps {
    taskId?: string;
    onSendMessage?: (message: string) => void;
    events?: TaskEvent[];
    isLoading?: boolean;
    className?: string;
    initialPrompt?: string;
    initialTimestamp?: string;
}

/* =========================
   EVENT CONFIG MAP
========================= */

type EventConfig = {
    role: ChatMessage["role"];
    icon: React.ReactNode;
    color: string;
    content: (event: any) => string;
    agent?: (event: any) => string | undefined;
};

const EVENT_CONFIG: Record<string, EventConfig> = {
    agent_start: {
        role: "assistant",
        icon: <Sparkles className="w-3 h-3 text-blue-400" />,
        color: "text-blue-400",
        content: () => "started working",
        agent: (e) => e.agent,
    },
    agent_end: {
        role: "assistant",
        icon: <CheckCircle className="w-3 h-3 text-green-400" />,
        color: "text-green-400",
        content: () => "completed task",
        agent: (e) => e.agent,
    },
    tool_call: {
        role: "assistant",
        icon: <Wrench className="w-3 h-3 text-purple-400" />,
        color: "text-purple-400",
        content: (e) => e.args?.task ? `${e.args.task}` : `${e.args?.agent} - ${e.args?.objective}`,
        agent: (e) => e.name,
    },
    tool_error: {
        role: "assistant",
        icon: <AlertCircle className="w-3 h-3 text-red-400" />,
        color: "text-red-400",
        content: (e) => `⚠️ ${e.tool}: ${e.error}`,
        agent: (e) => e.agent,
    },
    system_error: {
        role: "system",
        icon: <AlertCircle className="w-3 h-3 text-red-500" />,
        color: "text-red-500",
        content: (e) => `Error: ${e.error}`,
    },
    code_output: {
        role: "assistant",
        icon: <FileCode className="w-3 h-3 text-emerald-400" />,
        color: "text-emerald-400",
        content: (e) => `Generated file: ${e.filename || "solution.py"}`,
        agent: (e) => e.agent,
    },
    review_output: {
        role: "assistant",
        icon: <FileText className="w-3 h-3 text-yellow-400" />,
        color: "text-yellow-400",
        content: (e) => `Generated review: ${e.filename || "review.md"}`,
        agent: (e) => e.agent,
    },
    spec_output: {
        role: "assistant",
        icon: <FileText className="w-3 h-3 text-emerald-400" />,
        color: "text-emerald-400",
        content: (e) => `Generated spec: ${e.filename || "spec.md"}`,
        agent: (e) => e.agent,
    },
    decision_output: {
        role: "assistant",
        icon: <CheckCircle className="w-3 h-3 text-purple-400" />,
        color: "text-purple-400",
        content: (e) => `Decision: ${e.decision}`,
        agent: (e) => e.agent,
    },
    doc_output: {
        role: "assistant",
        icon: <FileText className="w-3 h-3 text-blue-400" />,
        color: "text-blue-400",
        content: (e) => e.documentation?.length > 300 ? e.documentation.slice(0, 300) + "\n..." : e.documentation,
        agent: (e) => e.agent,
    },
    test_output: {
        role: "assistant",
        icon: <TestTube className="w-3 h-3 text-cyan-400" />,
        color: "text-cyan-400",
        content: (e) => `Test results:\n${e.results}`,
        agent: (e) => e.agent,
    },
    cli_output: {
        role: "assistant",
        icon: <Terminal className="w-3 h-3 text-green-400" />,
        color: "text-green-400",
        content: (e) => e.message,
        agent: () => "CLI",
    },
    task_completed: {
        role: "system",
        icon: <CheckCircle className="w-3 h-3 text-green-500" />,
        color: "text-green-500",
        content: () => "✅ Task completed successfully!",
    },
    task_paused: {
        role: "system",
        icon: <Pause className="w-3 h-3 text-yellow-500" />,
        color: "text-yellow-500",
        content: (e) => `⏸️ ${e.message}`,
    },
    task_resumed: {
        role: "system",
        icon: <Play className="w-3 h-3 text-green-500" />,
        color: "text-green-500",
        content: (e) => `▶️ ${e.message}`,
    },
    human_approval: {
        role: "user",
        icon: <CheckCircle className="w-3 h-3 text-green-500" />,
        color: "text-green-500",
        content: (e) => e.message,
    },
    task_cancelled: {
        role: "system",
        icon: <StopCircle className="w-3 h-3 text-orange-500" />,
        color: "text-orange-500",
        content: (e) => `🛑 ${e.message || "Task cancelled by user"}`,
    },
    human_message: {
        role: "user",
        icon: <User className="w-3 h-3 text-blue-400" />,
        color: "text-blue-400",
        content: (e) => e.message,
    },
    conversation: {
        role: "assistant",
        icon: <MessageSquare className="w-3 h-3 text-violet-400" />,
        color: "text-violet-400",
        content: (e) => e.message,
        agent: () => "Supervisor",
    },
    clarification: {
        role: "assistant",
        icon: <HelpCircle className="w-3 h-3 text-amber-400" />,
        color: "text-amber-400",
        content: (e) => `❓ ${e.message}`,
        agent: () => "Supervisor",
    },
};

const THOUGHT_EVENT_TYPES = new Set(["tool_call", "agent_start", "agent_end"]);

function eventToChatMessage(event: TaskEvent, index: number): ChatMessage | null {
    if (event.type === "log") return null;

    const config = EVENT_CONFIG[event.type];
    if (!config) return null;

    // Special handling for human_approval icon/color
    if (event.type === "human_approval") {
        return {
            id: `evt_${index}_${event.timestamp}`,
            timestamp: event.timestamp,
            status: "complete",
            role: config.role,
            content: config.content(event),
            icon: event.approved
                ? <CheckCircle className="w-3 h-3 text-green-500" />
                : <XCircle className="w-3 h-3 text-red-500" />,
            color: event.approved ? "text-green-500" : "text-red-500",
            eventType: event.type,
        };
    }

    return {
        id: `evt_${index}_${event.timestamp}`,
        timestamp: event.timestamp,
        status: "complete",
        role: config.role,
        content: config.content(event),
        icon: config.icon,
        color: config.color,
        agent: config.agent?.(event),
        eventType: event.type,
    };
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

function ThoughtBubble({ message }: { message: ChatMessage }) {
    const [expanded, setExpanded] = useState(false);

    const label =
        message.eventType === "tool_call"
            ? "Tool Call"
            : message.eventType === "agent_start"
                ? "Agent Started"
                : message.eventType === "agent_end"
                    ? "Agent Completed"
                    : "Thought";

    return (
        <div className="px-4 py-0.5">
            <button
                onClick={() => setExpanded((v) => !v)}
                className="group/thought flex items-center gap-2 w-full text-left py-1.5 px-3 rounded-lg hover:bg-muted/40 transition-colors"
            >
                <ChevronRight
                    className={cn(
                        "w-3 h-3 text-muted-foreground/50 transition-transform duration-200 shrink-0",
                        expanded && "rotate-90"
                    )}
                />
                {message.icon}
                <span className="text-[11px] text-muted-foreground/60 font-medium">
                    {label}
                </span>
                {message.agent && (
                    <Badge
                        variant="outline"
                        className="text-[9px] px-1.5 py-0 border-border/50 text-muted-foreground/50"
                    >
                        {message.agent}
                    </Badge>
                )}
                <span className="text-[10px] text-muted-foreground/30 ml-auto">
                    {formatTime(message.timestamp)}
                </span>
            </button>

            {expanded && (
                <div className="ml-8 mt-1 mb-1 px-3 py-2 rounded-lg bg-muted/20 border border-border/30">
                    <p className="whitespace-pre-wrap break-words text-[11px] text-muted-foreground/70 leading-relaxed">
                        {message.content}
                    </p>
                </div>
            )}
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
                    <p className="whitespace-pre-wrap break-words text-xs">{message.content}</p>

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
    initialPrompt,
    initialTimestamp,
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
        // Filter out userMessages that are already represented in eventMessages (echoed by backend via SSE)
        const filteredUserMessages = userMessages.filter(um => 
            !eventMessages.some(em => em.role === "user" && em.content === um.content)
        );

        const all = [...eventMessages, ...filteredUserMessages];

        if (initialPrompt) {
            // Only add the initial prompt explicitly if it hasn't already been emitted as a human_message event
            const hasInitialPromptInEvents = eventMessages.some(em => em.role === "user" && em.content === initialPrompt);
            if (!hasInitialPromptInEvents) {
                all.push({
                    id: "initial_prompt",
                    role: "user",
                    content: initialPrompt,
                    timestamp: initialTimestamp || new Date().toISOString(),
                    status: "complete",
                });
            }
        }

        all.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
        return all;
    }, [eventMessages, userMessages, initialPrompt, initialTimestamp]);

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
                        {messages.map((msg) =>
                            msg.eventType && THOUGHT_EVENT_TYPES.has(msg.eventType) ? (
                                <ThoughtBubble key={msg.id} message={msg} />
                            ) : (
                                <MessageBubble key={msg.id} message={msg} />
                            )
                        )}

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
