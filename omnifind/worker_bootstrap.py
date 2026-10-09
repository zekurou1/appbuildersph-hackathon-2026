"""Wait for the supervisor's containment handshake before importing the parser."""
import runpy
import sys


if __name__ == "__main__":
    if sys.stdin.buffer.readline(16) != b"start\n":
        sys.exit(2)
    # Module is selected by application code, never by document contents.
    module = sys.argv.pop(1)
    runpy.run_module(module, run_name="__main__")
