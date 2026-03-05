"use client";

import { useEffect, useRef, useState, useCallback } from "react";

/**
 * A single command execution record.
 */
export interface TerminalCommandRecord {
    id: string;
    command: string;
    status: "running" | "success" | "error" | "timeout";
    output?: string;
    exitCode?: number;
    startedAt: number; // timestamp
    finishedAt?: number;
}

/**
 * Connects to the `/ws/terminal-commands/{clientId}` WebSocket and
 * accumulates structured command events into state.
 *
 * Returns the list of command records and a `clear` function.
 */
export function useTerminalCommands() {
    const [commands, setCommands] = useState<TerminalCommandRecord[]>([]);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isMountedRef = useRef(true);

    const connect = useCallback(() => {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const host = window.location.hostname || "localhost";
        const clientId = `cmd_${Math.random().toString(36).substring(2, 9)}`;
        const wsUrl = `${protocol}://${host}:8000/ws/terminal-commands/${clientId}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "command_start") {
                    const record: TerminalCommandRecord = {
                        id: `cmd_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
                        command: data.command,
                        status: "running",
                        startedAt: Date.now(),
                    };
                    setCommands((prev) => [...prev, record]);
                }

                if (data.type === "command_output") {
                    setCommands((prev) => {
                        // Find the last running command that matches
                        const idx = [...prev]
                            .reverse()
                            .findIndex(
                                (c) => c.status === "running" && c.command === data.command
                            );

                        if (idx === -1) return prev;

                        const realIdx = prev.length - 1 - idx;
                        const updated = [...prev];
                        updated[realIdx] = {
                            ...updated[realIdx],
                            status:
                                data.exit_code === 0
                                    ? "success"
                                    : data.output?.includes("[TIMEOUT]")
                                        ? "timeout"
                                        : "error",
                            output: data.output,
                            exitCode: data.exit_code,
                            finishedAt: Date.now(),
                        };
                        return updated;
                    });
                }
            } catch {
                // Ignore malformed messages
            }
        };

        ws.onclose = () => {
            if (isMountedRef.current) {
                // Auto-reconnect after 3 seconds
                reconnectTimeout.current = setTimeout(() => {
                    connect();
                }, 3000);
            }
        };

        ws.onerror = () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        };
    }, []); // Remove connect from here

    useEffect(() => {
        connect();

        return () => {
            isMountedRef.current = false;
            if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
            if (wsRef.current) {
                const socket = wsRef.current;
                socket.onopen = null;
                socket.onmessage = null;
                socket.onclose = null;
                socket.onerror = null;

                if (socket.readyState === WebSocket.CONNECTING) {
                    socket.onopen = () => {
                        try {
                            socket.close();
                        } catch (e) { }
                    };
                } else if (socket.readyState === WebSocket.OPEN) {
                    try {
                        socket.close();
                    } catch (e) {
                        // Ignore
                    }
                }
                wsRef.current = null;
            }
        };
    }, [connect]);

    const clear = useCallback(() => setCommands([]), []);

    return { commands, clear };
}
