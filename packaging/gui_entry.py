import os
import sys

# Windowed bootloaders have no console streams. Dependencies may still write progress.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == '--probe-report':
        import json
        import traceback
        from pathlib import Path
        report = Path(sys.argv[2])
        report.write_text(json.dumps({'stage': 'entry'}))
        try:
            from omnifind.package_probe import run
            run(report)
        except Exception:
            # An unattended diagnostic must not wait on a bootloader error dialog.
            report.write_text(json.dumps({'verified': False, 'error': traceback.format_exc()}))
            sys.exit(1)
    else:
        from omnifind.gui import main
        main()
