"""Explicit network-only setup; never called from inference."""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
BGE_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model-id", choices=[MODEL_ID, "BAAI/bge-small-en-v1.5"], default=MODEL_ID)
    parser.add_argument("--revision", help="Explicit asset revision; defaults to tested model commit")
    args = parser.parse_args()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    revision = HfApi().model_info(args.model_id, revision=args.revision or (REVISION if args.model_id == MODEL_ID else BGE_REVISION)).sha
    snapshot_download(
        args.model_id, revision=revision, local_dir=destination,
        allow_patterns=["config.json", "tokenizer*.json", "special_tokens_map.json", "vocab.txt",
                        "model.safetensors", "sentence_bert_config.json", "modules.json", "1_Pooling/*", "README.md", "LICENSE"],
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
    manifest = {"model_id": args.model_id, "revision": revision,
                "license": "Apache-2.0 per model card" if args.model_id == MODEL_ID else "MIT per model card", "files": files,
                "total_bytes": sum(f["bytes"] for f in files.values())}
    (destination / "asset-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"revision": revision, "total_bytes": manifest["total_bytes"]}))


if __name__ == "__main__":
    main()
