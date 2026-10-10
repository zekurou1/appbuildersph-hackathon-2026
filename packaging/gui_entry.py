import os
import sys

# Windowed bootloaders have no console streams. Dependencies may still write progress.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == '--probe-report':
        from omnifind.package_probe import run
        run(sys.argv[2])
    else:
        from omnifind.gui import main
        main()
