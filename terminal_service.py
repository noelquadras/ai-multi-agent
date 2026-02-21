import os
import asyncio
import threading
import time
import re
from typing import Dict, Optional, List

# Try importing pywinpty
try:
    from winpty import PtyProcess
except ImportError:
    PtyProcess = None

class TerminalSession:
    def __init__(self, process, loop=None):
        self.process = process
        self.loop = loop or asyncio.get_running_loop()
        
        # Support multiple listeners for multicasting (WebSocket + run_command)
        self.listeners: List[asyncio.Queue] = []
        self.control_listeners: List[asyncio.Queue] = []
        
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
                    # 1. Send raw data to control listeners (commands need exact output)
                    for q in list(self.control_listeners):
                        self.loop.call_soon_threadsafe(q.put_nowait, data)
                    
                    # 2. Send sanitized data to display listeners (WebSockets)
                    # We strip out the agent's hidden commands/markers to keep it clean
                    clean_data = self._sanitize_output(data)
                    if clean_data:
                        for q in list(self.listeners):
                            self.loop.call_soon_threadsafe(q.put_nowait, clean_data)
                else:
                    time.sleep(0.01)
            except Exception as e:
                # Handle EOF or error
                if self.active:
                    print(f"PTY Read Error: {e}")
                self.active = False
                break

    def _sanitize_output(self, data: str) -> str:
        """
        Filters out the internal agent command machinery only for the display.
        This handles the user requirement to show 'only the one-line main exact command'
        and 'real background outputs', hiding the complex implementation details.
        """
        # Remove the echo of the appended exit logic from the command line
        # Matches: ; Write-Host "__AGENT_DONE__... up to end of line
        data = re.sub(r';\s*Write-Host\s+"__AGENT_DONE__.*', '', data)
        
        # Remove the execution output of the marker itself
        # Matches: __AGENT_DONE__RUN_xxx <exit_code> and potential trailing newlines
        # We use strict matching to avoid accidental deletions
        data = re.sub(r'__AGENT_DONE__RUN_\w+\s+(-?\d+)?\r?\n?', '', data)
        
        return data

    async def read_stream(self):
        """Streaming generator for WebSockets."""
        q = asyncio.Queue()
        self.listeners.append(q)
        try:
            while self.active:
                try:
                    data = await q.get()
                    yield data
                except asyncio.CancelledError:
                    break
        finally:
            if q in self.listeners:
                self.listeners.remove(q)

    def write(self, data: str):
        if self.active:
            self.process.write(data)

    async def run_command(self, command: str, timeout: float = 20.0):
        """
        Executes a command and returns the output (cleaned) and exit code.
        """
        if self.busy:
            raise RuntimeError("Terminal is busy")
        
        self.busy = True
        output_buffer = ""
        marker = "__AGENT_DONE__"
        run_id = f"RUN_{int(time.time())}"
        
        # We use a specialized listener for this command to capture its specific output
        control_queue = asyncio.Queue()
        self.control_listeners.append(control_queue)
        
        try:
            # Inline the exit code extraction logic
            # Logic: Write marker followed by exit code (0 if success, else LASTEXITCODE or 1)
            exit_logic = f'Write-Host "{marker}_{run_id} $(if ($?) {{ 0 }} else {{ if ($LASTEXITCODE) {{ $LASTEXITCODE }} else {{ 1 }} }})"'
            
            # Combine commands: Command -> Write Exit Code
            full_command = f'{command}; {exit_logic}'
            
            self.process.write(full_command + "\r\n")
            
            start_time = time.time()
            
            while True:
                if time.time() - start_time > timeout:
                    output_buffer += "\n[TIMEOUT]"
                    try:
                        self.process.write("\x03") # Ctrl+C
                    except:
                        pass
                    break
                
                try:
                    # Non-blocking get from queue with short timeout
                    chunk = await asyncio.wait_for(control_queue.get(), timeout=0.1)
                    output_buffer += chunk
                    
                    # Check for completion marker in the accumulated buffer
                    if re.search(f"{marker}_{run_id}\\s*(-?\\d+)", output_buffer):
                        break
                            
                except asyncio.TimeoutError:
                    continue
                    
        except Exception:
             pass
        finally:
            self.busy = False
            if control_queue in self.control_listeners:
                self.control_listeners.remove(control_queue)
            
        # Parse output and exit code from the captured buffer
        exit_code = -1
        clean_output = output_buffer
        
        # Extract exit code
        matches = list(re.finditer(f"{marker}_{run_id}\\s*(-?\\d+)", output_buffer))
        if matches:
            last_match = matches[-1]
            try:
                exit_code = int(last_match.group(1))
            except ValueError:
                pass
            
            clean_output = output_buffer[:last_match.start()]

        # Also strip the command echo from the RETURN value (for the programmatic caller)
        # The display listener already got it stripped via _sanitize_output.
        # We try to remove the specific full_command string if present at start.
        clean_output = clean_output.replace(full_command, "")
        
        # We also might want to remove the standard echo of 'command' if user requested "outputs only".
        # But 'executor.py' expects the output. 
        # Typically clean_output here includes the echo of the command.
        # 'executor.py' filters extensively, so we leave it relatively raw but minus the injection.
            
        return {
            "output": clean_output.strip(),
            "exit_code": exit_code
        }

    def resize(self, cols: int, rows: int):
        if self.active and hasattr(self.process, 'setwinsize'):
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
