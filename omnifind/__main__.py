import argparse
import json
import os
import re
import sqlite3
from pathlib import Path

from .core import Index


def main():
    parser = argparse.ArgumentParser(description="OmniFind Local retrieval core (no GUI yet)")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OmniFindLocal" / "index.sqlite")
    parser.add_argument("--model", type=Path, default=Path("models/minilm"))
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add-folder")
    add.add_argument("path", type=Path)
    refresh = sub.add_parser("refresh")
    refresh.add_argument("root_id", type=int)
    remove = sub.add_parser("remove-folder")
    remove.add_argument("root_id", type=int)
    sub.add_parser("status")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--mode", choices=["filename", "lexical", "semantic", "hybrid"], default="hybrid")
    search.add_argument("--type", dest="suffix")
    search.add_argument("--folder", dest="root_id", type=int)
    search.add_argument("--show-weak", action="store_true", help="Reveal candidates below the experimental threshold")
    args = parser.parse_args()
    index = None
    try:
        embedder = None
        if args.command == "refresh" or (args.command == "search" and args.mode in {"semantic", "hybrid"}):
            from .model import LocalEmbedder
            embedder = LocalEmbedder(args.model)
        index = Index(args.db, embedder)
        if args.command == "add-folder":
            result = {"root_id": index.add_root(args.path), "next": "Run refresh with this root ID"}
        elif args.command == "refresh":
            result = index.refresh(args.root_id)
        elif args.command == "remove-folder":
            index.remove_root(args.root_id)
            result = {"removed": args.root_id, "original_files_preserved": True}
        elif args.command == "status":
            result = {"folders": index.roots(), "coverage": index.coverage(), "storage": "plaintext-local-index"}
        else:
            result = index.search_response(args.query, args.mode, args.root_id, args.suffix, show_weak=args.show_weak)
            result["notice"] = "Verify source evidence. Weak-match thresholds are experimental, not confidence."
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, ImportError, RuntimeError, sqlite3.Error) as error:
        # Avoid leaking private paths/content/tracebacks in diagnostics.
        code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z-]{1,80}", str(error)) else "local-runtime-or-file-error"
        parser.exit(2, f"OmniFind: {code}. Check assets/folder access; lexical search is available without the model.\n")
    finally:
        if index:
            index.close()


if __name__ == "__main__":
    main()
