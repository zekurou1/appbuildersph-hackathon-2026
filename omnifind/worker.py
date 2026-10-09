"""Bounded extraction supervision. Windows-first, no unrestricted fallback."""
import os
import subprocess
import sys
import threading
import time

MEMORY_BYTES = 256 * 1024 * 1024
OUTPUT_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 20


def run_worker(module, arguments, checkpoint=None, timeout=TIMEOUT_SECONDS,
               memory_bytes=MEMORY_BYTES, output_bytes=OUTPUT_BYTES):
    if os.name != "nt":
        raise ValueError("extraction-containment-unsupported-platform")
    from .windows_job import WindowsJob
    job = WindowsJob(memory_bytes)
    process = None
    readers = []
    output = bytearray()
    overflow = threading.Event()
    read_error = threading.Event()

    def drain(stream, retain):
        try:
            while block := stream.read(4096):
                if retain:
                    if len(output) + len(block) > output_bytes:
                        overflow.set()
                    elif not overflow.is_set():
                        output.extend(block)
                # stderr is discarded, never accumulated or logged.
        except OSError:
            read_error.set()

    try:
        if checkpoint:
            checkpoint()
        process = subprocess.Popen([sys.executable, "-m", "omnifind.worker_bootstrap", module, *map(str, arguments)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        job.assign(process.pid)
        for stream, retain in [(process.stdout, True), (process.stderr, False)]:
            thread = threading.Thread(target=drain, args=(stream, retain), daemon=True)
            thread.start()
            readers.append(thread)
        process.stdin.write(b"start\n")
        process.stdin.close()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if checkpoint:
                checkpoint()
            if overflow.is_set():
                raise ValueError("extraction-output-too-large")
            if time.monotonic() >= deadline:
                raise ValueError("extraction-timeout")
            time.sleep(.02)
        for thread in readers:
            thread.join(2)
        if overflow.is_set():
            raise ValueError("extraction-output-too-large")
        if read_error.is_set() or any(thread.is_alive() for thread in readers):
            raise ValueError("extraction-output-failed")
        if checkpoint:
            checkpoint()
        return process.returncode, output.decode("utf-8")
    finally:
        job.terminate()
        if process:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for thread in readers:
                thread.join(2)
            for stream in [process.stdin, process.stdout, process.stderr]:
                stream.close()
        job.close()
