"""Local-only CPU embedding adapter. Downloads live in a separate setup command."""
import hashlib
import json
import os
from pathlib import Path


class LocalEmbedder:
    def __init__(self, directory: Path):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        directory = directory.resolve(strict=True)
        manifest = json.loads((directory / "asset-manifest.json").read_text(encoding="utf-8"))
        for name, entry in manifest["files"].items():
            path = (directory / name).resolve(strict=True)
            if not path.is_relative_to(directory):
                raise ValueError("Invalid model asset path")
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                    raise ValueError("Model asset checksum mismatch")
        if manifest["model_id"] != "sentence-transformers/all-MiniLM-L6-v2":
            raise ValueError("unsupported-model-pooling")
        from transformers import AutoModel, AutoTokenizer
        self.model = AutoModel.from_pretrained(str(directory), local_files_only=True,
                                               trust_remote_code=False, use_safetensors=True).to("cpu").eval()
        self.tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True,
                                                       trust_remote_code=False, use_fast=True)
        self.identity = f'{manifest["model_id"]}@{manifest["revision"]}:mean-normalized-v1'
        self.dimensions = self.model.config.hidden_size

    def encode(self, texts):
        import numpy as np
        import torch
        batches = []
        for start in range(0, len(texts), 16):
            encoded = self.tokenizer(texts[start:start + 16], padding=True, truncation=False,
                                     return_tensors="pt")
            if encoded["input_ids"].shape[1] > 256:
                raise ValueError("model-token-limit-shorten-query")
            with torch.inference_mode():
                tokens = self.model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).expand(tokens.size()).float()
                pooled = (tokens * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                batches.append(torch.nn.functional.normalize(pooled, p=2, dim=1).numpy())
        vectors = np.concatenate(batches) if batches else np.empty((0, self.dimensions))
        vectors = np.asarray(vectors, dtype="<f4")
        if vectors.shape != (len(texts), self.dimensions) or not np.isfinite(vectors).all():
            raise ValueError("Invalid embedding output")
        return vectors

    def chunks(self, text, tokens=160, overlap=30):
        """Exact source slices, bounded by this model's tokenizer (no silent truncation)."""
        offsets = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                 truncation=False)["offset_mapping"]
        for start in range(0, len(offsets), tokens - overlap):
            end = min(start + tokens, len(offsets))
            a, b = offsets[start][0], offsets[end - 1][1]
            yield text[a:b], a, b
            if end == len(offsets):
                break
