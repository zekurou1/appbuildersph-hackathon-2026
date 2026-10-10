"""Frozen console entry and contained-worker dispatch; never accepts document commands."""
import runpy
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.argv.pop(1)
        if len(sys.argv) < 2 or sys.argv[1] not in {"omnifind.extract", "omnifind.thumbnail"}:
            raise SystemExit(2)
        runpy.run_module("omnifind.worker_bootstrap", run_name="__main__")
    else:
        runpy.run_module("omnifind.__main__", run_name="__main__")
