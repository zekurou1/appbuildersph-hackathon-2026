"""Synthetic fault probe only; never selected by application indexing."""
import os
import subprocess
import sys
import time
from pathlib import Path

mode, marker = sys.argv[1:]
Path(marker).write_text(str(os.getpid()))
if mode == "sleep":
    time.sleep(60)
elif mode == "memory":
    try:
        bytearray(512 * 1024 * 1024)
    except MemoryError:
        print("memory-denied")
        sys.exit(3)
    raise RuntimeError("Memory ceiling was not enforced")
elif mode == "output":
    sys.stdout.buffer.write(b"x" * (1024 * 1024))
elif mode == "spawn":
    try:
        subprocess.run([sys.executable, "-c", "raise SystemExit(0)"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        print("spawn-denied")
    else:
        print("spawn-allowed")
