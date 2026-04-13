import os
import asyncio
import threading
import time
import re
from typing import Dict, Optional, List


import sys

# Try importing pywinpty (Windows) or ptyprocess (Linux)
PtyProcess = None
if sys.platform == 'win32':
    try:
        from winpty import PtyProcess
    except ImportError:
        pass
else:
    try:
        from ptyprocess import PtyProcess
    except ImportError:
        pass


class TerminalSession:
    def __init__(self, process, loop=None):
        self.process = process
        self.loop = loop or asyncio.get_running_loop()

        # Support multiple listeners for multicasting (WebSocket + run_command)
        self.listeners: List[asyncio.Queue] = []
        self.control_listeners: List[asyncio.Queue] = []

        # --- Command-level event listeners (structured output for frontend) ---
        # Each queue receives dicts like:
        #   {"type": "command_start", "command": "python main.py"}
        #   {"type": "command_output", "command": "python main.py", "output": "...", "exit_code": 0}
        self.command_event_listeners: List[asyncio.Queue] = []

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
                    # On Linux/ptyprocess, data is bytes. On Windows/winpty, it might be str or bytes depending on version.
                    if isinstance(data, bytes):
                        data = data.decode('utf-8', errors='replace')

                    # 1. Send raw data to control listeners (commands need exact output)
                    for q in list(self.control_listeners):
                        self.loop.call_soon_threadsafe(q.put_nowait, data)

                    # 2. Send sanitized data to display listeners (WebSockets)
                    clean_data = self._sanitize_output(data)
                    if clean_data:
                        for q in list(self.listeners):
                            self.loop.call_soon_threadsafe(q.put_nowait, clean_data)
                else:
                    time.sleep(0.01)
            except Exception as e:
                if self.active:
                    print(f"PTY Read Error: {e}")
                self.active = False
                break

    def _sanitize_output(self, data: str) -> str:
        """
        Filters out the internal agent command machinery for display.
        Hides the exit-code marker logic appended to every run_command invocation.
        """
        # Remove the echo of the appended exit logic from the command line (PowerShell)
        data = re.sub(r';\s*Write-Host\s+"__AGENT_DONE__.*', '', data)
        # Remove the echo of the appended exit logic from the command line (Bash)
        data = re.sub(r';\s*echo\s+"__AGENT_DONE__.*', '', data)

        # Remove the execution output of the marker itself
        data = re.sub(r'__AGENT_DONE___RUN_\w+\s+(-?\d+)?\r?\n?', '', data)

        return data

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Strip ANSI escape sequences from text."""
        return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)

    async def read_stream(self):
        """Streaming generator for raw PTY WebSockets."""
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

    async def read_command_events(self):
        """
        Streaming generator for structured command events.

        Yields dicts:
          {"type": "command_start", "command": "..."}
          {"type": "command_output", "command": "...", "output": "...", "exit_code": 0}
        """
        q = asyncio.Queue()
        self.command_event_listeners.append(q)
        try:
            while self.active:
                try:
                    event = await q.get()
                    yield event
                except asyncio.CancelledError:
                    break
        finally:
            if q in self.command_event_listeners:
                self.command_event_listeners.remove(q)

    def _emit_command_event(self, event: dict):
        """Push a structured command event to all command-event listeners."""
        for q in list(self.command_event_listeners):
            self.loop.call_soon_threadsafe(q.put_nowait, event)

    def write(self, data: str):
        if self.active:
            if sys.platform != "win32" and isinstance(data, str):
                self.process.write(data.encode('utf-8'))
            else:
                self.process.write(data)

    async def run_command(self, command: str, timeout: Optional[float] = 20.0):
        """
        Executes a command and returns the output (cleaned) and exit code.
        Also emits structured command events for any frontend command-event listeners.
        """
        if self.busy:
            raise RuntimeError("Terminal is busy")

        self.busy = True
        output_buffer = ""
        marker = "__AGENT_DONE__"
        run_id = f"RUN_{int(time.time())}"

        # Extract the user-facing command (strip internal cd prefixes for display)
        display_command = command
        cd_match = re.match(r'^cd\s+"[^"]+"\s*;\s*(.+)$', command)
        if cd_match:
            display_command = cd_match.group(1)

        # Notify listeners that a command has started
        self._emit_command_event({
            "type": "command_start",
            "command": display_command,
        })

        # Use a specialized listener for this command to capture its specific output
        control_queue = asyncio.Queue()
        self.control_listeners.append(control_queue)

        try:
            # Inline the exit code extraction logic
            if sys.platform == 'win32':
                exit_logic = f'Write-Host "{marker}_{run_id} $(if ($?) {{ 0 }} else {{ if ($LASTEXITCODE) {{ $LASTEXITCODE }} else {{ 1 }} }})"'
                full_command = f'{command}; {exit_logic}'
            else:
                exit_logic = f'echo "{marker}_{run_id} $?"'
                full_command = f'{command}; {exit_logic}'

            self.write(full_command + "\r\n")

            start_time = time.time()

            while True:
                if timeout is not None and time.time() - start_time > timeout:
                    output_buffer += "\n[TIMEOUT]"
                    try:
                        self.write("\x03")  # Ctrl+C
                    except Exception:
                        pass
                    break

                try:
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

        # Strip the command echo from the return value
        clean_output = clean_output.replace(full_command, "")

        # Also strip ANSI escape codes for the structured event
        plain_output = self._strip_ansi(clean_output).strip()

        # Notify listeners with the structured result
        self._emit_command_event({
            "type": "command_output",
            "command": display_command,
            "output": plain_output,
            "exit_code": exit_code,
        })

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
        except Exception:
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
                del self.sessions[session_id]

        if PtyProcess is None:
            raise RuntimeError("PTY implementation not installed. Please install 'pywinpty' (Windows) or 'ptyprocess' (Linux).")

        if sys.platform == "win32":
            shell = "powershell.exe"
            proc = PtyProcess.spawn(
                shell.split(),
                cwd=os.path.abspath(cwd),
                dimensions=(80, 24)
            )
        else:
            shell = "/bin/bash"
            # ptyprocess.spawn needs the executable and arguments separately
            proc = PtyProcess.spawn(
                [shell],
                cwd=os.path.abspath(cwd),
                dimensions=(24, 80) # ptyprocess uses (rows, cols)
            )

        loop_to_use = self.main_loop
        if not loop_to_use:
            try:
                loop_to_use = asyncio.get_running_loop()
            except RuntimeError:
                pass

        session = TerminalSession(proc, loop=loop_to_use)
        self.sessions[session_id] = session
        return session

    def close_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].close()
            del self.sessions[session_id]


# Singleton instance
manager = TerminalManager()
