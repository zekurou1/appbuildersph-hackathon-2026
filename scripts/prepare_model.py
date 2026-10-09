"""Explicit network-only setup; never called from inference."""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    revision = HfApi().model_info(MODEL_ID).sha
    snapshot_download(
        MODEL_ID, revision=revision, local_dir=destination,
        allow_patterns=["*.json", "*.txt", "*.safetensors", "1_Pooling/*", "README.md"],
    )
    files = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file() and ".cache" not in path.parts and path.name != "asset-manifest.json":
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files[str(path.relative_to(destination))] = {
                "sha256": digest,
                "bytes": path.stat().st_size,
            }
    manifest = {"model_id": MODEL_ID, "revision": revision,
                "license": "Apache-2.0 per model card", "files": files,
                "total_bytes": sum(f["bytes"] for f in files.values())}
    (destination / "asset-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"revision": revision, "total_bytes": manifest["total_bytes"]}))


if __name__ == "__main__":
    main()
