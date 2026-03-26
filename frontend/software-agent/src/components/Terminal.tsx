"use client";

import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import { WebLinksAddon } from "xterm-addon-web-links";
import "xterm/css/xterm.css";

interface TerminalProps {
    className?: string;
}

export function Terminal({ className }: TerminalProps) {
    const terminalRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const xtermRef = useRef<XTerm | null>(null);
    const fitAddonRef = useRef<FitAddon | null>(null);

    useEffect(() => {
        if (!terminalRef.current) return;

        let isMounted = true;

        // Initialize xterm.js
        const term = new XTerm({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: "Menlo, Monaco, 'Courier New', monospace",
            theme: {
                background: "#1a1b26",
                foreground: "#a9b1d6",
                cursor: "#f7768e",
                selectionBackground: "#33467c",
            },
            convertEol: true, // Important for windows PTY
        });

        const fitAddon = new FitAddon();
        const webLinksAddon = new WebLinksAddon();

        term.loadAddon(fitAddon);
        term.loadAddon(webLinksAddon);

        // Defer terminal open to avoid rapid mount/unmount issues with xterm.js (RenderService bug)
        const initTimeout = setTimeout(() => {
            if (!isMounted || !terminalRef.current) return;

            try {
                term.open(terminalRef.current);
            } catch (e) {
                console.error("Error opening terminal:", e);
                return;
            }

            // Use a small delay for fit to ensure dimensions are calculated by browser
            initialFitTimeout = setTimeout(() => {
                if (isMounted && terminalRef.current && terminalRef.current.offsetParent !== null) {
                    try {
                        fitAddon.fit();
                    } catch (e) {
                        console.warn("Initial terminal fit failed:", e);
                    }
                }
            }, 100);
        }, 10);

        let initialFitTimeout: ReturnType<typeof setTimeout>;

        xtermRef.current = term;
        fitAddonRef.current = fitAddon;

        // WebSocket connection
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const host = window.location.hostname || "localhost";
        const wsUrl = `${protocol}://${host}:8000/ws/terminal/client_${Math.random().toString(36).substring(7)}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            if (!isMounted) return;
            term.write("\x1b[32m\r\nConnected to terminal session...\r\n\x1b[0m");
            const { cols, rows } = term;
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(`RESIZE:${cols}:${rows}`);
            }
        };

        ws.onmessage = (event) => {
            if (!isMounted) return;
            term.write(event.data);
        };

        ws.onclose = () => {
            if (!isMounted) return;
            term.write("\r\n\x1b[31mConnection closed.\x1b[0m");
        };

        ws.onerror = (error) => {
            if (!isMounted) return;
            // Only log actual errors, not closures during teardown
            if (ws.readyState === WebSocket.OPEN) {
                console.error("WebSocket error:", error);
                term.write("\r\n\x1b[31mConnection error.\x1b[0m");
            }
        };

        // Terminal -> WebSocket
        term.onData((data) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(data);
            }
        });

        // Handle resize with proper debouncing/RAF
        let resizeTask: number | null = null;
        const resizeObserver = new ResizeObserver(() => {
            if (!isMounted || !terminalRef.current || terminalRef.current.offsetParent === null) return;

            if (resizeTask) cancelAnimationFrame(resizeTask);
            resizeTask = requestAnimationFrame(() => {
                if (!isMounted || !terminalRef.current) return;
                try {
                    fitAddon.fit();
                    const { cols, rows } = term;
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(`RESIZE:${cols}:${rows}`);
                    }
                } catch (e) {
                    // Silently ignore
                }
            });
        });

        resizeObserver.observe(terminalRef.current);

        // Cleanup
        return () => {
            isMounted = false;
            if (resizeTask) cancelAnimationFrame(resizeTask);
            if (typeof initialFitTimeout !== "undefined") clearTimeout(initialFitTimeout);
            clearTimeout(initTimeout);
            resizeObserver.disconnect();

            if (wsRef.current) {
                const socket = wsRef.current;
                // De-attach handlers before closing to avoid "closed before established" console logs in some browsers
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

            try {
                term.dispose();
            } catch (e) {
                // Ignore
            }
        };
    }, []);

    return (
        <div
            ref={terminalRef}
            className={`w-full h-full bg-[#1a1b26] p-2 rounded-md overflow-hidden ${className}`}
        />
    );
}
