"""Download public, pinned mobile inference assets; never send source files."""
import hashlib
import json
import urllib.request
from pathlib import Path

REVISION = "10dbd2f06a8baf40ad285b037edda610c1b9a57c"
FILES = {
    "model.onnx": ("onnx/model.onnx", "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"),
    "vocab.txt": ("vocab.txt", "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3"),
}

def main():
    destination = Path("mobile/android/app/src/main/assets")
    destination.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name, (remote, expected) in FILES.items():
        path = destination / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            temporary = path.with_suffix(path.suffix + ".part")
            urllib.request.urlretrieve(
                f"https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/{REVISION}/{remote}", temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                temporary.unlink()
                raise RuntimeError("Public model asset checksum mismatch")
            temporary.replace(path)
        entries[name] = {"sha256": expected, "bytes": path.stat().st_size}
    (destination / "model-manifest.json").write_text(json.dumps({"model": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": REVISION, "license": "Apache-2.0", "files": entries}, indent=2))
    print(json.dumps(entries, indent=2))

if __name__ == "__main__":
    main()
