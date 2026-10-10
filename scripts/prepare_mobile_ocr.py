"""Prepare the pinned public English OCR asset and dependency notices at build time."""
import hashlib
import json
import urllib.request
from pathlib import Path

REVISION = '87416418657359cb625c412a48b6e1d6d41c29bd'
SHA256 = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
assets = Path('mobile/android/app/src/main/assets')
assets.mkdir(parents=True, exist_ok=True)
base = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}'
path = assets / 'eng.traineddata'
if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
    with urllib.request.urlopen(base + '/eng.traineddata', timeout=60) as response:
        data = response.read(5_000_001)
    assert len(data) <= 5_000_000 and hashlib.sha256(data).hexdigest() == SHA256
    path.write_bytes(data)
for name, url in {
    'TESSDATA-LICENSE.txt': base + '/LICENSE',
    'TESSERACT4ANDROID-LICENSE.txt': 'https://raw.githubusercontent.com/adaptech-cz/Tesseract4Android/4.9.0/LICENSE',
    'TESSERACT-LICENSE.txt': 'https://raw.githubusercontent.com/adaptech-cz/Tesseract4Android/4.9.0/tesseract4android/src/main/cpp/tesseract/src/LICENSE',
    'LEPTONICA-LICENSE.txt': 'https://raw.githubusercontent.com/adaptech-cz/Tesseract4Android/4.9.0/tesseract4android/src/main/cpp/leptonica/src/leptonica-license.txt',
    'LIBPNG-LICENSE.txt': 'https://raw.githubusercontent.com/adaptech-cz/Tesseract4Android/4.9.0/tesseract4android/src/main/cpp/libpng/src/LICENSE',
    'LIBJPEG-NOTICE.txt': 'https://raw.githubusercontent.com/adaptech-cz/Tesseract4Android/4.9.0/tesseract4android/src/main/cpp/libjpeg/src/README',
}.items():
    with urllib.request.urlopen(url, timeout=60) as response:
        (assets / name).write_bytes(response.read(100_000))
manifest = {
    'engine': 'Tesseract4Android 4.9.0 standard / Tesseract 5.5.1',
    'dependency': 'cz.adaptech.tesseract4android:tesseract4android:4.9.0',
    'aar_sha256': 'bce5d6413a1a5ae3d7240033fbbc851ba3217d0a08d9769400e17a077f42cb2a',
    'repository': 'https://github.com/tesseract-ocr/tessdata_fast',
    'revision': REVISION, 'language': 'eng',
    'file': 'eng.traineddata', 'sha256': SHA256, 'bytes': path.stat().st_size,
    'download_location': 'build machine only; no app download path',
}
(assets / 'ocr-manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest))
