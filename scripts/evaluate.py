"""Real local model + manually labeled development set, with all four baselines."""
import argparse
import json
import socket
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omnifind.core import Index
from omnifind.model import LocalEmbedder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=Path("models/minilm"))
    parser.add_argument("--output", type=Path, default=Path("reports/runtime/evaluation"))
    args = parser.parse_args()
    attempts = []
    def deny(*args, **kwargs):
        attempts.append("connect")
        raise RuntimeError("Network blocked during development evaluation")
    socket.socket.connect = deny
    socket.create_connection = deny

    import numpy as np
    from reportlab.pdfgen import canvas
    from textwrap import wrap
    data = json.loads(Path("fixtures/development.json").read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    corpus = run / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    for document in data["documents"]:
        path = corpus / document["file"]
        if path.suffix == ".pdf":
            pdf = canvas.Canvas(str(path))
            text = pdf.beginText(50, 780)
            for line in wrap(document["text"], 90):
                text.textLine(line)
            pdf.drawText(text)
            pdf.save()
        else:
            path.write_text(document["text"], encoding="utf-8")
    started = time.perf_counter()
    model = LocalEmbedder(args.model)
    load_seconds = time.perf_counter() - started
    index = Index(run / "data" / "index.sqlite", model)
    try:
        root_id = index.add_root(corpus)
        started = time.perf_counter()
        coverage = index.refresh(root_id)
        indexing_seconds = time.perf_counter() - started
        assert coverage["searchable"] == len(data["documents"]), coverage
        queries = [(query, document["file"]) for document in data["documents"] for query in document["queries"]]
        metrics = {}
        for mode in ["filename", "lexical", "semantic", "hybrid"]:
            observations = []
            for query, target in queries:
                started = time.perf_counter()
                results = index.search(query, mode, limit=5)
                elapsed = time.perf_counter() - started
                names = [Path(result["path"]).name for result in results]
                rank = names.index(target) + 1 if target in names else None
                observations.append({"target": target, "query": query, "rank": rank, "seconds": elapsed})
                assert len(names) == len(set(names))
                for result in results:
                    assert index.source_path(result["file_id"]).exists()
                    assert result["text"]
            metrics[mode] = {
                "queries": len(queries), "top1": sum(r["rank"] == 1 for r in observations) / len(queries),
                "hit_rate_at_5": sum(r["rank"] is not None for r in observations) / len(queries),
                "mrr_at_5": sum(1 / r["rank"] if r["rank"] else 0 for r in observations) / len(queries),
                "p95_seconds": float(np.percentile([r["seconds"] for r in observations], 95)),
                "observations": observations,
            }
        # Record absence behavior without turning similarity into calibrated confidence.
        absent = [{"query": query, "candidates_returned": len(index.search(query, "hybrid", limit=5))}
                  for query in data["absent_queries"]]
        # Fresh post-setup file and query; then restart and root removal.
        fresh = corpus / "fresh.txt"
        fresh.write_text("Library card LIB-551 expires on January 31. Renew it at the circulation desk.", encoding="utf-8")
        index.refresh(root_id)
        assert Path(index.search("LIB-551", "hybrid")[0]["path"]).name == "fresh.txt"
        index.close()
        index = Index(run / "data" / "index.sqlite", model)
        assert Path(index.search("LIB-551", "hybrid")[0]["path"]).name == "fresh.txt"
        index.remove_root(root_id)
        assert not index.search("LIB-551", "hybrid")
        assert fresh.exists()
        report = {"dataset": "synthetic-development-v1", "held_out": False,
                  "model": model.identity, "files": len(data["documents"]), "queries": len(queries),
                  "model_load_seconds": load_seconds, "indexing_seconds": indexing_seconds,
                  "coverage": coverage, "metrics": metrics, "absent_target_observations": absent,
                  "fresh_file_restart_removal": "passed", "python_socket_connect_attempts": len(attempts),
                  "limitations": ["Development data, not a frozen holdout", "No model comparison yet",
                                  "No calibrated no-match threshold; all results require verification",
                                  "Python-process guard only, not an OS/network audit", "Ten-file corpus is not a scale benchmark"]}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        compact = {**report, "metrics": {mode: {key: value for key, value in values.items() if key != "observations"}
                                           for mode, values in metrics.items()}}
        print(json.dumps(compact, indent=2))
    finally:
        index.close()


if __name__ == "__main__":
    main()
