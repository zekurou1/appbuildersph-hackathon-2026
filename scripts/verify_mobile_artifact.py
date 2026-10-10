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
    ocr = json.loads(archive.read('assets/ocr-manifest.json'))
    assert hashlib.sha256(archive.read('assets/eng.traineddata')).hexdigest() == ocr['sha256'] == '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
    for name in ['TESSDATA-LICENSE.txt', 'TESSERACT4ANDROID-LICENSE.txt', 'TESSERACT-LICENSE.txt', 'LEPTONICA-LICENSE.txt', 'LIBPNG-LICENSE.txt', 'LIBJPEG-NOTICE.txt']:
        assert archive.getinfo('assets/' + name).file_size > 0
    for architecture in ['arm64-v8a', 'armeabi-v7a', 'x86_64']:
        assert archive.getinfo(f'lib/{architecture}/libtesseract.so').file_size > 0
tests = list(Path('mobile/build/app/outputs/androidTest-results/connected').rglob('TEST-*.xml'))
assert tests, 'Native test results are missing'
native = [ET.parse(test).getroot().attrib for test in tests]
passed = sum(int(suite['tests']) for suite in native)
assert passed == 14 and all(int(suite['failures']) == 0 and int(suite['errors']) == 0 and int(suite.get('skipped', 0)) == 0 for suite in native)
with apk.open('rb') as stream:
    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
report = {'apk_bytes': apk.stat().st_size, 'apk_sha256': sha, 'signing': 'debug-signed pilot release build',
    'no_internet_permission': True, 'automatic_telemetry_provider_removed': True,
    'backup_disabled': True, 'bundled_assets_hashes_verified': True, 'model': provenance, 'ocr': ocr,
    'native_instrumented_tests': {'passed': passed, 'emulator': 'Android 17 API 37 x86_64',
        'checks': ['Four English tokenizer fixtures and normalized ONNX embedding cosine > .999 against desktop', 'SQLite index opening and selected-root listing',
            'Native two-page PDF extraction and semantic preference for the relevant page', 'Blank and malformed PDF issue codes',
            'PDF page-count rejection', 'Cancellation removes temporary PDF bytes', 'TXT/MD source-line compatibility', 'SQLite migrations preserve original text passages and PDF pages',
            'PNG OCR words, exact code, pixel regions and semantic passage preference', 'Upright JPEG OCR', 'Blank/malformed image issue codes', 'Pre-OCR pixel bound', 'Canceled OCR returns no partial evidence']},
    'limits': ['APK manifest inspection is not a complete OS egress audit', 'PDF text search requires Android 15+; older OS guard and physical devices remain unexercised',
        'No physical-phone, independent user, TalkBack, battery or mobile holdout validation']}
Path('docs/mobile-artifact-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps({key: report[key] for key in ['apk_bytes', 'apk_sha256', 'no_internet_permission', 'backup_disabled']}))
