"""Evaluate a frozen synthetic holdout without modifying retrieval or calibration."""
import argparse
import hashlib
import json
import os
import platform
import socket
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path
from textwrap import wrap

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def content_hash(path):
    # Git's Windows checkout line-ending conversion must not alter the freeze identity.
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_freeze():
    freeze = json.loads((PROJECT / "fixtures/holdout-v1.freeze.json").read_text(encoding="utf-8"))
    for name, expected in freeze["files"].items():
        if content_hash(PROJECT / name) != expected:
            raise ValueError("frozen-input-or-implementation-changed")
    return freeze


def labeled_queries(data):
    documents = {doc["id"]: doc for doc in data["documents"]}
    if len(documents) != len(data["documents"]):
        raise ValueError("duplicate-document-id")
    queries = [{"query": query, "targets": [doc["id"]], "kind": "identifier" if i else "paraphrase"}
               for doc in data["documents"] for i, query in enumerate(doc["queries"])] + data["extra_queries"]
    development = json.loads((PROJECT / "fixtures/development.json").read_text(encoding="utf-8"))
    old_queries = {query.casefold() for doc in development["documents"] for query in doc["queries"]}
    old_queries.update(query.casefold() for query in development["absent_queries"])
    seen = set()
    for query in queries:
        text = query["query"].casefold()
        if text in seen or text in old_queries:
            raise ValueError("holdout-query-overlap")
        seen.add(text)
        if not query["targets"] or len(query["targets"]) != len(set(query["targets"])):
            raise ValueError("invalid-relevance-labels")
        for target in query["targets"]:
            doc = documents[target]
            if query.get("folder", doc["folder"]) != doc["folder"]:
                raise ValueError("target-excluded-by-filter")
            if query.get("suffix", Path(doc["file"]).suffix.lstrip(".")) != Path(doc["file"]).suffix.lstrip("."):
                raise ValueError("target-excluded-by-filter")
    for absent in data["absent_queries"]:
        if absent.casefold() in old_queries or absent.casefold() in seen:
            raise ValueError("absent-query-overlap")
        seen.add(absent.casefold())
    if len(queries) != 50 or len(data["absent_queries"]) != 20:
        raise ValueError("unexpected-holdout-size")
    return queries


def summarize(observations):
    import numpy as np
    return {"queries": len(observations),
            "top1": statistics.mean(item["top1"] for item in observations),
            "hit_rate_at_5": statistics.mean(item["hit"] for item in observations),
            "recall_at_5": statistics.mean(item["recall"] for item in observations),
            "mrr_at_5": statistics.mean(item["rr"] for item in observations),
            "warm_median_seconds": statistics.median(t for item in observations for t in item["seconds"]),
            "warm_p95_seconds": float(np.percentile([t for item in observations for t in item["seconds"]], 95)),
            "timed_calls": sum(len(item["seconds"]) for item in observations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=PROJECT / "models/minilm")
    parser.add_argument("--output", type=Path, default=PROJECT / "reports/runtime/holdout")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("repeats must be between 1 and 10")
    freeze = verify_freeze()
    data = json.loads((PROJECT / "fixtures/holdout-v1.json").read_text(encoding="utf-8"))
    queries = labeled_queries(data)
    attempts = []
    def deny(*arguments, **keywords):
        attempts.append("connect")
        raise RuntimeError("Network blocked during holdout evaluation")
    socket.socket.connect = deny
    socket.create_connection = deny

    import psutil
    from reportlab.pdfgen import canvas
    from omnifind.core import Index
    from omnifind.model import LocalEmbedder
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    root_paths = {name: run / "corpus" / name for name in {doc["folder"] for doc in data["documents"]}}
    for root in root_paths.values():
        root.mkdir(parents=True)
    doc_paths = {}
    for document in data["documents"]:
        if Path(document["file"]).name != document["file"]:
            raise ValueError("fixture-basename-required")
        path = root_paths[document["folder"]] / document["file"]
        if path in doc_paths.values():
            raise ValueError("duplicate-document-path")
        doc_paths[document["id"]] = path
        if path.suffix == ".pdf":
            pdf = canvas.Canvas(str(path))
            text = pdf.beginText(50, 780)
            for line in wrap(document["text"], 85):
                text.textLine(line)
            pdf.drawText(text)
            pdf.save()
        else:
            path.write_text(document["text"], encoding="utf-8")
    path_ids = {str(path): identifier for identifier, path in doc_paths.items()}
    stop = threading.Event()
    samples = {"peak_process_tree_rss_bytes": 0, "samples": 0}
    host_process = psutil.Process()
    def sample():
        while not stop.is_set():
            processes = [host_process]
            try:
                processes += host_process.children(recursive=True)
            except psutil.Error:
                pass
            total = 0
            for process in processes:
                try:
                    total += process.memory_info().rss
                except psutil.Error:
                    pass
            samples["peak_process_tree_rss_bytes"] = max(samples["peak_process_tree_rss_bytes"], total)
            samples["samples"] += 1
            stop.wait(.02)
    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    index = None
    try:
        started = time.perf_counter()
        model = LocalEmbedder(args.model)
        load_seconds = time.perf_counter() - started
        index = Index(run / "data/index.sqlite", model)
        roots = {name: index.add_root(path) for name, path in sorted(root_paths.items())}
        started = time.perf_counter()
        for root_id in roots.values():
            index.refresh(root_id)
        indexing_seconds = time.perf_counter() - started
        coverage = index.coverage()
        assert coverage["searchable"] == len(doc_paths), coverage
        chunks = index.db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        pages = index.db.execute("SELECT count(*) FROM (SELECT DISTINCT file_id,page FROM chunks WHERE page IS NOT NULL)").fetchone()[0]
        started = time.perf_counter()
        index.search_response(queries[0]["query"], limit=5)
        first_hybrid_seconds = time.perf_counter() - started
        observations = {}
        for method in ["filename", "lexical", "semantic", "hybrid", "hybrid-gated"]:
            records = []
            for item in queries:
                options = {"root_id": roots.get(item.get("folder")), "suffix": item.get("suffix"), "limit": 5}
                times = []
                previous = None
                for repeat in range(args.repeats):
                    started = time.perf_counter()
                    response = index.search_response(item["query"], "hybrid", **options) if method == "hybrid-gated" else {
                        "status": "raw-candidates", "results": index.search(item["query"], method, **options)}
                    times.append(time.perf_counter() - started)
                    names = [path_ids[result["path"]] for result in response["results"]]
                    if len(names) != len(set(names)) or (previous is not None and previous != names):
                        raise AssertionError("duplicate-or-unstable-results")
                    previous = names
                    for result in response["results"]:
                        assert str(index.source_path(result["file_id"], result["revision"])) == result["path"]
                        assert result["text"]
                targets = set(item["targets"])
                ranks = [position + 1 for position, name in enumerate(names) if name in targets]
                records.append({**item, "returned": names, "status": response["status"], "seconds": times,
                                "top1": bool(names and names[0] in targets), "hit": bool(ranks),
                                "recall": len(set(names) & targets) / len(targets), "rr": 1 / min(ranks) if ranks else 0})
            observations[method] = records
            print(f"Completed {method}", flush=True)
        absent = []
        for query in data["absent_queries"]:
            response = index.search_response(query, limit=5)
            absent.append({"query": query, "status": response["status"],
                           "returned": [path_ids[result["path"]] for result in response["results"]],
                           "accepted": bool(response["results"])})
        verify_freeze()
        policy = json.loads((PROJECT / "config/retrieval-policy.json").read_text(encoding="utf-8"))
        report = {"dataset": data["dataset"], "held_out_from_development_tuning": True,
                  "independent_or_blinded_validation": False, "freeze": freeze, "model": model.identity,
                  "policy": policy["models"][model.identity],
                  "device": {"os": platform.platform(), "python": platform.python_version(),
                             "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
                             "logical_cpus": os.cpu_count(), "ram_bytes": psutil.virtual_memory().total,
                             "sqlite": sqlite3.sqlite_version, "backend": "CPU", "model_threads": min(4, os.cpu_count() or 1)},
                  "corpus": {"files": len(doc_paths), "bytes": sum(path.stat().st_size for path in doc_paths.values()),
                             "pdf_pages": pages, "chunks": chunks, "selected_roots": len(roots),
                             "index_bytes": index.path.stat().st_size},
                  "model_load_seconds": load_seconds, "indexing_seconds": indexing_seconds,
                  "first_hybrid_request_seconds": first_hybrid_seconds,
                  "warmup": "One hybrid-policy request before timed baseline calls; same process and OS cache",
                  "coverage": coverage, "metrics": {method: summarize(records) for method, records in observations.items()},
                  "by_kind": {method: {kind: summarize([item for item in records if item["kind"] == kind])
                                       for kind in sorted({item["kind"] for item in records})}
                              for method, records in observations.items()},
                  "observations": observations, "absent_observations": absent,
                  "absent_queries": len(absent), "absent_rejected": sum(not item["accepted"] for item in absent),
                  "python_socket_connect_attempts": len(attempts),
                  "memory": {**samples, "sampling_interval_seconds": .02,
                             "definition": "Sampled sum of evaluator and descendant RSS; shared pages can be counted twice, short peaks may be missed"},
                  "limitations": ["Author-created synthetic labels, not independent users or blinded validation",
                                  "Twenty short documents, not a scale benchmark", "No language/OCR validation",
                                  "Python socket guard is not an OS egress audit", "No machine-cold cache or clean-install measurement",
                                  "No policy/model/ranking changes permitted during this holdout run"]}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key not in {"observations", "absent_observations", "freeze", "by_kind"}}, indent=2))
    finally:
        if index:
            index.close()
        stop.set()
        monitor.join(2)


if __name__ == "__main__":
    main()
