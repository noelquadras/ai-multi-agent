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

        term.open(terminalRef.current);
        fitAddon.fit();

        xtermRef.current = term;
        fitAddonRef.current = fitAddon;

        // WebSocket connection
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const wsUrl = `${protocol}://localhost:8000/ws/terminal/client_${Math.random().toString(36).substring(7)}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            term.write("\x1b[32m\r\nConnected to terminal session...\r\n\x1b[0m");
            // Send initial resize to sync backend
            const { cols, rows } = term;
            ws.send(`RESIZE:${cols}:${rows}`);
        };

        ws.onmessage = (event) => {
            term.write(event.data);
        };

        ws.onclose = () => {
            term.write("\r\n\x1b[31mConnection closed.\x1b[0m");
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            term.write("\r\n\x1b[31mConnection error.\x1b[0m");
        };

        // Terminal -> WebSocket
        term.onData((data) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(data);
            }
        });

        // Handle resize
        const resizeObserver = new ResizeObserver(() => {
            fitAddon.fit();
            const { cols, rows } = term;
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(`RESIZE:${cols}:${rows}`);
            }
        });

        resizeObserver.observe(terminalRef.current);

        // Cleanup
        return () => {
            resizeObserver.disconnect();
            ws.close();
            term.dispose();
        };
    }, []);

    return (
        <div
            ref={terminalRef}
            className={`w-full h-full min-h-[400px] bg-[#1a1b26] p-2 rounded-md overflow-hidden ${className}`}
        />
    );
}
