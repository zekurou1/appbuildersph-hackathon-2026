"""Inspect built APK privacy configuration, bundled hashes and native test results."""
import hashlib
import json
import os
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

apk = Path('mobile/build/app/outputs/flutter-apk/app-release.apk')
aapt = Path(os.environ['LOCALAPPDATA']) / 'Android/sdk/build-tools/36.0.0/aapt.exe'
permissions = subprocess.check_output([str(aapt), 'dump', 'permissions', str(apk)], text=True)
manifest = subprocess.check_output([str(aapt), 'dump', 'xmltree', str(apk), 'AndroidManifest.xml'], text=True)
assert 'android.permission.INTERNET' not in permissions
assert 'android.permission.ACCESS_NETWORK_STATE' not in permissions
assert 'TelemetryInitializer' not in manifest
assert 'android:allowBackup' in manifest and 'android:allowBackup(0x01010280)=(type 0x12)0x0' in manifest
with zipfile.ZipFile(apk) as archive:
    provenance = json.loads(archive.read('assets/model-manifest.json'))
    for name, entry in provenance['files'].items():
        assert hashlib.sha256(archive.read('assets/' + name)).hexdigest() == entry['sha256']
    for name in ['MINILM-LICENSE.txt', 'ONNX-RUNTIME-LICENSE.txt']:
        assert archive.getinfo('assets/' + name).file_size > 0
tests = list(Path('mobile/build/app/outputs/androidTest-results/connected').rglob('TEST-*.xml'))
assert len(tests) == 1
native = ET.parse(tests[0]).getroot().attrib
assert int(native['tests']) == 2 and int(native['failures']) == 0 and int(native['errors']) == 0
with apk.open('rb') as stream:
    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
report = {'apk_bytes': apk.stat().st_size, 'apk_sha256': sha, 'signing': 'debug-signed pilot release build',
    'no_internet_permission': True, 'automatic_telemetry_provider_removed': True,
    'backup_disabled': True, 'bundled_assets_hashes_verified': True, 'model': provenance,
    'native_instrumented_tests': {'passed': 2, 'emulator': 'Android 17 API 37 x86_64',
        'checks': ['Four English tokenizer fixtures and normalized ONNX embedding cosine > .999 against desktop', 'SQLite index opening and selected-root listing']},
    'limits': ['APK manifest inspection is not a complete OS egress audit', 'Native test suite predates final UI-only refinements; builder-observed release flows are recorded separately',
        'No physical-phone, independent user, TalkBack, battery or mobile holdout validation']}
Path('docs/mobile-artifact-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps({key: report[key] for key in ['apk_bytes', 'apk_sha256', 'no_internet_permission', 'backup_disabled']}))
