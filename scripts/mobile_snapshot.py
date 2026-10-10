"""Inspect the explicitly named Android emulator's current UI for synthetic tests."""
import json
import os
import sys
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

adb = Path(os.environ['LOCALAPPDATA']) / 'Android/sdk/platform-tools/adb.exe'
prefix = [str(adb), '-s', 'emulator-5554']
with Path('reports/runtime/mobile-screen.png').open('wb') as stream:
    subprocess.run(prefix + ['exec-out', 'screencap', '-p'], stdout=stream, check=True)
if '--screen-only' in sys.argv:
    print('Captured current emulator screen; accessibility tree not requested.')
    raise SystemExit(0)
remote = f'/sdcard/omnifind-ui-{uuid.uuid4().hex}.xml'
result = subprocess.run(prefix + ['shell', 'uiautomator', 'dump', remote], capture_output=True, timeout=30)
if result.returncode or b'UI hierchary dumped' not in result.stdout:
    raise RuntimeError('UI snapshot unavailable; no old snapshot was reused')
output = Path('reports/runtime/mobile-ui.xml')
subprocess.run(prefix + ['pull', remote, str(output)], check=True, capture_output=True)
nodes = [{'text': n.get('text'), 'description': n.get('content-desc'), 'bounds': n.get('bounds'),
          'class': n.get('class'), 'clickable': n.get('clickable')}
         for n in ET.parse(output).iter('node') if n.get('text') or n.get('content-desc') or n.get('class') == 'android.widget.EditText']
print(json.dumps(nodes, ensure_ascii=True))
