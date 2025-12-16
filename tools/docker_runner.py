import subprocess
import threading
import queue

def run_code_in_docker(code: str, output_queue: queue.Queue, image="python:3.12-slim", timeout=10):
    """
    Run the provided Python code inside a temporary Docker container.
    Streams stdout/stderr line by line to the queue.
    """
    cmd = [
        "docker", "run", "--rm", "--network=none",
        "-i", image, "python", "-u", "-"
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    # Feed the code
    proc.stdin.write(code)
    proc.stdin.close()

    # Read stdout/stderr in separate threads
    def _reader(stream, is_err=False):
        for line in iter(stream.readline, ""):
            output_queue.put((line.rstrip("\n"), is_err))
        stream.close()

    t_out = threading.Thread(target=_reader, args=(proc.stdout, False), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, True), daemon=True)
    t_out.start()
    t_err.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        output_queue.put(("[Docker Timeout] Process killed.", True))
