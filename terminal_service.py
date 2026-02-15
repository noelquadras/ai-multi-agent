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
import re

class TerminalSession:
    def __init__(self, process, loop=None):
        self.process = process
        self.loop = loop or asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.active = True
        self.busy = False
        
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

    async def run_command(self, command: str, timeout: float = 20.0):
        if self.busy:
            raise RuntimeError("Terminal is busy")
        
        self.busy = True
        output_buffer = ""
        marker = "__AGENT_DONE__"
        
        try:
            # Inline the exit code extraction logic to avoid defining a function that gets echoed
            # We use cls to clear previous output, helping to ensure a clean state
            # Logic: Write marker followed by exit code (0 if success, else LASTEXITCODE or 1)
            exit_logic = f'Write-Host "{marker} $(if ($?) {{ 0 }} else {{ if ($LASTEXITCODE) {{ $LASTEXITCODE }} else {{ 1 }} }})"'
            
            # Combine commands: Clear Screen -> Run Command -> Write Exit Code
            full_command = f'cls; {command}; {exit_logic}'
            
            self.process.write(full_command + "\r\n")
            
            start_time = time.time()
            
            while True:
                # Check timeout
                if time.time() - start_time > timeout:
                    output_buffer += "\n[TIMEOUT]"
                    try:
                        self.process.write("\x03") # Ctrl+C
                    except:
                        pass
                    break
                
                try:
                    # Non-blocking get from queue with short timeout
                    chunk = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    output_buffer += chunk
                    
                    # Check for marker
                    if marker in output_buffer:
                        # We found the marker. But we should wait until we have the exit code too.
                        if re.search(f"{marker}\\s*-?\\d+", output_buffer):
                            break
                            
                except asyncio.TimeoutError:
                    continue
        except Exception:
             # If something crashes in the loop (unlikely)
             pass
        finally:
            self.busy = False
            
        # Parse output and exit code
        exit_code = -1
        clean_output = output_buffer
        
        # Extract exit code
        # We look for the last occurrence of marker + number
        matches = list(re.finditer(f"{marker}\\s*(-?\\d+)", output_buffer))
        if matches:
            last_match = matches[-1]
            try:
                exit_code = int(last_match.group(1))
            except ValueError:
                pass
            
            # The output up to the marker is the clean output
            # But wait, input echo also contains the marker string!
            # Input echo: ... command; __agent_done ...
            # The definition of __agent_done is hidden if we used function?
            # No, input echo of `__agent_done` command is just `__agent_done`.
            # True output is `__AGENT_DONE__ 0`.
            # So `__agent_done` input echo does NOT match `__AGENT_DONE__ \d+`.
            # Excellent.
            
            clean_output = output_buffer[:last_match.start()]
            
        return {
            "output": clean_output.strip(),
            "exit_code": exit_code
        }

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
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        self.main_loop = loop

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
        
        # Determine which loop to use
        # If we have a stored main_loop, use it. Otherwise try get_running_loop.
        # But TerminalSession calls get_running_loop() in __init__.
        # We need to temporarily set the thread's loop or pass loop to TerminalSession?
        # Better to update TerminalSession to accept loop argument.
        
        loop_to_use = self.main_loop
        if not loop_to_use:
            try:
                loop_to_use = asyncio.get_running_loop()
            except RuntimeError:
                pass
                
        # We need to update TerminalSession to accept loop
        session = TerminalSession(proc, loop=loop_to_use)
        self.sessions[session_id] = session
        return session

    def close_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].close()
            del self.sessions[session_id]

# Singleton instance
manager = TerminalManager()
