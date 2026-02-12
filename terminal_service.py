import os
import asyncio
import threading
import time
from typing import Dict, Optional

# Try importing pywinpty
try:
    from winpty import PtyProcess
except ImportError:
    PtyProcess = None

class TerminalSession:
    def __init__(self, process):
        self.process = process
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.active = True
        
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()
        
    def _reader(self):
        while self.active:
            try:
                # This blocks until data is available
                data = self.process.read(4096)
                if data:
                    self.loop.call_soon_threadsafe(self.queue.put_nowait, data)
                else:
                    time.sleep(0.01)
            except Exception as e:
                if self.active:
                    print(f"PTY Read Error: {e}")
                self.active = False
                break

    async def read_stream(self):
        while self.active:
            try:
                data = await self.queue.get()
                yield data
            except asyncio.CancelledError:
                break

    def write(self, data: str):
        if self.active:
            self.process.write(data)

    def resize(self, cols: int, rows: int):
        if self.active:
            self.process.setwinsize(rows, cols)
            
    def close(self):
        self.active = False
        try:
            self.process.close()
        except:
            pass

class TerminalManager:
    def __init__(self):
        self.sessions: Dict[str, TerminalSession] = {}

    def get_or_create_session(self, session_id: str, cwd: str = ".") -> TerminalSession:
        if session_id in self.sessions:
            if self.sessions[session_id].active:
                return self.sessions[session_id]
            else:
                # Cleanup dead session
                del self.sessions[session_id]
            
        if PtyProcess is None:
            raise RuntimeError("pywinpty is not installed. Please install it with 'pip install pywinpty'.")

        # Spawn PowerShell
        # Note: winpty requires the executable path usually, or command name if in PATH
        shell = "powershell.exe"
        
        # Ensure cwd exists
        if not os.path.exists(cwd):
            cwd = os.getcwd()
            
        proc = PtyProcess.spawn(
            shell.split(),
            cwd=os.path.abspath(cwd),
            dimensions=(80, 24)
        )
        
        session = TerminalSession(proc)
        self.sessions[session_id] = session
        return session

    def close_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].close()
            del self.sessions[session_id]

# Singleton instance
manager = TerminalManager()
