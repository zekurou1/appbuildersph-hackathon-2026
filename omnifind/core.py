"""Small-corpus retrieval core; desktop worker orchestration lives in gui.py."""
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path

from .extract import MAX_FILE_BYTES, SUPPORTED
from .locking import writer_lease
from .worker import run_worker


class ScopeError(ValueError):
    pass


class WorkCancelled(RuntimeError):
    pass


def is_identifier_query(query):
    """Recognize a standalone code, never ordinary prose or a plain number."""
    query = query.strip()
    return (2 <= len(query) <= 128 and re.fullmatch(r"\w+(?:[-.]\w+)*", query) is not None
            and any(char.isalpha() for char in query) and any(char.isdecimal() for char in query))


def ordinary_path(path):
    """Reject links, junctions and offline/recall placeholders, including ancestors."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        info = part.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or attributes & (0x400 | 0x1000 | 0x40000 | 0x400000):
            raise ScopeError("link-or-cloud-placeholder")
    return path.resolve(strict=True)


class Index:
    def __init__(self, database, embedder=None):
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS roots(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS files(
                id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
                path TEXT UNIQUE NOT NULL, suffix TEXT NOT NULL, size INTEGER, mtime INTEGER,
                digest TEXT, status TEXT NOT NULL, error TEXT);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                text TEXT NOT NULL, page INTEGER, line_start INTEGER, line_end INTEGER,
                vector BLOB, model TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(filename, content);
            CREATE TRIGGER IF NOT EXISTS chunk_delete AFTER DELETE ON chunks BEGIN
                DELETE FROM chunk_fts WHERE rowid=old.id;
            END;
        """)
        # SQLite core secure_delete alone does not erase old FTS index segments.
        # Rebuild existing segments once when upgrading this privacy setting.
        if sqlite3.sqlite_version_info < (3, 42, 0):
            self.db.close()
            raise ValueError("sqlite-upgrade-required")
        secure_fts = self.db.execute("SELECT v FROM chunk_fts_config WHERE k='secure-delete'").fetchone()
        if not secure_fts or secure_fts[0] != 1:
            self.db.execute("INSERT INTO chunk_fts(chunk_fts,rank) VALUES('secure-delete',1)")
            self.db.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")
        version = self.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()
        if version and version[0] != "1":
            raise ValueError("unsupported-index-schema")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema','1')")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('privacy-epoch','0')")
        self.db.commit()

    def close(self):
        self.db.close()

    def roots(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM roots ORDER BY id")]

    def add_root(self, path):
        with writer_lease(self.path):
            return self._add_root(path)

    def _add_root(self, path):
        path = ordinary_path(path)
        if not path.is_dir():
            raise ScopeError("folder-required")
        if path.is_relative_to(self.path.parent):
            raise ScopeError("index-data-folder-excluded")
        for root in self.roots():
            existing = Path(root["path"])
            if path == existing:
                return root["id"]
            if path.is_relative_to(existing) or existing.is_relative_to(path):
                raise ScopeError("overlapping-roots")
        with self.db:
            cursor = self.db.execute("INSERT INTO roots(path) VALUES (?)", (str(path),))
        return cursor.lastrowid

    def _root(self, root_id):
        row = self.db.execute("SELECT * FROM roots WHERE id=?", (root_id,)).fetchone()
        if not row:
            raise ScopeError("folder-not-authorized")
        return ordinary_path(row["path"])

    def authorize(self, root_id, path):
        root = self._root(root_id)
        path = ordinary_path(path)
        if not path.is_relative_to(root) or path.is_relative_to(self.path.parent):
            raise ScopeError("outside-selected-folder")
        return path

    def remove_root(self, root_id):
        # One transaction removes scope and all text/vector/FTS derivatives.
        with self.db:
            self.db.execute("DELETE FROM roots WHERE id=?", (root_id,))
            self._revoke_epoch()

    def _revoke_epoch(self):
        self.db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='privacy-epoch'")

    def clear(self):
        """Forget all selected folders and derived records, retaining originals/assets."""
        with writer_lease(self.path):
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                self.db.execute("DELETE FROM roots")
                self._revoke_epoch()
                # Recreate FTS, including shadow tables; DELETE alone retains old segments.
                self.db.execute("DROP TABLE chunk_fts")
                self.db.execute("CREATE VIRTUAL TABLE chunk_fts USING fts5(filename, content)")
                self.db.execute("INSERT INTO chunk_fts(chunk_fts,rank) VALUES('secure-delete',1)")
            # Logical deletion is already durable if compaction fails (e.g. low disk).
            try:
                self.db.execute("VACUUM")
            except sqlite3.Error:
                return {"cleared": True, "compacted": False, "original_files_preserved": True}
        return {"cleared": True, "compacted": True, "original_files_preserved": True}

    def _record_error(self, root_id, path, status, error):
        with self.db:
            if not self.db.execute("SELECT 1 FROM roots WHERE id=?", (root_id,)).fetchone():
                raise ScopeError("folder-not-authorized")
            self.db.execute("""INSERT INTO files(root_id,path,suffix,status,error) VALUES (?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET status=excluded.status,error=excluded.error""",
                (root_id, str(path), path.suffix.lower(), status, error))

    def refresh(self, root_id, cancel=None, progress=None):
        with writer_lease(self.path):
            return self._refresh(root_id, cancel, progress)

    def _refresh(self, root_id, cancel=None, progress=None):
        if not self.embedder:
            raise ValueError("local-model-required-for-indexing")
        root = self._root(root_id)
        identities = self.db.execute("SELECT DISTINCT model FROM chunks").fetchall()
        if any(row[0] != self.embedder.identity for row in identities):
            raise ValueError("model-mismatch-create-new-index")
        seen = set()
        traversal_errors = []
        processed = 0
        def checkpoint():
            if cancel and cancel.is_set():
                raise WorkCancelled("operation-cancelled")
        checkpoint()
        for directory, subdirs, names in os.walk(root, followlinks=False,
                                                onerror=lambda error: traversal_errors.append("folder-unreadable")):
            retained = []
            for name in subdirs:
                try:
                    self.authorize(root_id, Path(directory) / name)
                    retained.append(name)
                except (ScopeError, OSError):
                    pass
            subdirs[:] = retained
            for name in names:
                checkpoint()
                path = Path(directory) / name
                if path.is_relative_to(self.path.parent):
                    continue
                seen.add(str(path))
                processed += 1
                if progress:
                    progress({"processed": processed, "coverage": self.coverage(root_id)})
                try:
                    path = self.authorize(root_id, path)
                    if path.suffix.lower() not in SUPPORTED:
                        self._record_error(root_id, path, "unsupported", "unsupported-format")
                        continue
                    before = path.stat()
                    if before.st_size > MAX_FILE_BYTES:
                        raise ValueError("file-too-large")
                    with path.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    current = self.db.execute("SELECT * FROM files WHERE path=?", (str(path),)).fetchone()
                    if current and current["status"] == "searchable" and current["digest"] == digest:
                        identities = self.db.execute("SELECT DISTINCT model FROM chunks WHERE file_id=?",
                                                     (current["id"],)).fetchall()
                        if len(identities) == 1 and identities[0][0] == self.embedder.identity:
                            with self.db:
                                self.db.execute("UPDATE files SET size=?,mtime=? WHERE id=?",
                                                (before.st_size, before.st_mtime_ns, current["id"]))
                            continue
                    def extraction_checkpoint():
                        checkpoint()
                        self.authorize(root_id, path)
                    returncode, output = run_worker("omnifind.extract", [path, root], extraction_checkpoint)
                    if returncode:
                        try:
                            error = json.loads(output).get("error", "extraction-failed")
                        except (ValueError, AttributeError):
                            error = "extraction-resource-or-worker-failure"
                        raise ValueError(error)
                    payload = json.loads(output)
                    checkpoint()
                    self.authorize(root_id, path)
                    chunks = []
                    for section in payload["sections"]:
                        text = section["text"]
                        for excerpt, start, end in self.embedder.chunks(text):
                            chunks.append((excerpt, section["page"], text.count("\n", 0, start) + 1,
                                           text.count("\n", 0, end) + 1))
                    if not chunks:
                        raise ValueError("no-digital-text")
                    checkpoint()
                    vectors = self.embedder.encode([chunk[0] for chunk in chunks])
                    checkpoint()
                    self.authorize(root_id, path)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                        raise ValueError("file-changed-during-indexing")
                    # Replacement is atomic; no chunks from unfinished revisions are searchable.
                    with self.db:
                        self.db.execute("BEGIN IMMEDIATE")
                        self.authorize(root_id, path)
                        self.db.execute("""INSERT INTO files(root_id,path,suffix,size,mtime,digest,status,error)
                            VALUES (?,?,?,?,?,?,'searchable',NULL) ON CONFLICT(path) DO UPDATE SET
                            size=excluded.size,mtime=excluded.mtime,digest=excluded.digest,status='searchable',error=NULL""",
                            (root_id, str(path), path.suffix.lower(), after.st_size, after.st_mtime_ns, digest))
                        file_id = self.db.execute("SELECT id FROM files WHERE path=?", (str(path),)).fetchone()[0]
                        self.db.execute("DELETE FROM chunks WHERE file_id=?", (file_id,))
                        for chunk, vector in zip(chunks, vectors, strict=True):
                            cursor = self.db.execute("""INSERT INTO chunks(file_id,text,page,line_start,line_end,vector,model)
                                VALUES (?,?,?,?,?,?,?)""", (file_id, *chunk, vector.tobytes(), self.embedder.identity))
                            self.db.execute("INSERT INTO chunk_fts(rowid,filename,content) VALUES (?,?,?)",
                                            (cursor.lastrowid, path.name, chunk[0]))
                except WorkCancelled:
                    raise
                except ScopeError:
                    # Revocation terminates processing; unsafe files are visible as skipped.
                    self._root(root_id)
                    self._record_error(root_id, path, "failed", "scope-or-placeholder")
                except Exception as error:
                    code = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z-]+", str(error)) else "processing-failed"
                    self._record_error(root_id, path, "failed", code)
        if traversal_errors:
            raise OSError("folder-unreadable-refresh-incomplete")
        checkpoint()
        with self.db:
            for row in self.db.execute("SELECT id,path FROM files WHERE root_id=?", (root_id,)).fetchall():
                if row["path"] not in seen:
                    self.db.execute("DELETE FROM files WHERE id=?", (row["id"],))
        return self.coverage(root_id)

    def coverage(self, root_id=None):
        sql = "SELECT * FROM files"
        parameters = ()
        if root_id is not None:
            sql += " WHERE root_id=?"
            parameters = (root_id,)
        counts = {"searchable": 0, "failed": 0, "unsupported": 0, "pending": 0}
        for row in self.db.execute(sql, parameters):
            state = row["status"]
            if state == "searchable":
                try:
                    path = self.authorize(row["root_id"], row["path"])
                    info = path.stat()
                    if (info.st_size, info.st_mtime_ns) != (row["size"], row["mtime"]):
                        state = "stale"
                except FileNotFoundError:
                    state = "missing"
                except (OSError, ScopeError):
                    state = "unavailable"
            counts[state] = counts.get(state, 0) + 1
        counts["discovered"] = sum(counts.values())
        return counts

    def _eligible(self, root_id=None, suffix=None):
        sql = """SELECT c.*,f.path,f.root_id,f.suffix,f.size,f.mtime,f.digest FROM chunks c
            JOIN files f ON f.id=c.file_id JOIN roots r ON r.id=f.root_id WHERE f.status='searchable'"""
        parameters = []
        if root_id is not None:
            sql += " AND f.root_id=?"
            parameters.append(root_id)
        if suffix:
            sql += " AND f.suffix=?"
            parameters.append("." + suffix.lower().lstrip("."))
        rows = []
        for row in self.db.execute(sql, parameters):
            try:
                path = self.authorize(row["root_id"], row["path"])
                info = path.stat()
                if (info.st_size, info.st_mtime_ns) == (row["size"], row["mtime"]):
                    rows.append(row)
            except (OSError, ScopeError):
                pass
        return rows

    def search(self, query, mode="hybrid", root_id=None, suffix=None, limit=10):
        if mode not in {"filename", "lexical", "semantic", "hybrid"}:
            raise ValueError("unknown-search-mode")
        query = query.strip()
        if not query:
            return []
        if len(query) > 2000 or not 1 <= limit <= 100:
            raise ValueError("query-or-result-limit")
        rows = self._eligible(root_id, suffix)
        eligible = {row["id"]: row for row in rows}
        if not eligible:
            return []
        ranks = []
        semantic_scores = {}
        terms = [phrase or token for phrase, token in re.findall(r'"([^"\n]+)"|(\w+(?:[-.]\w+)*)', query, flags=re.UNICODE)]
        if len(terms) > 64:
            raise ValueError("too-many-query-terms")
        if mode == "filename":
            matches = [(row["id"], sum(term.casefold() in Path(row["path"]).name.casefold() for term in terms)) for row in rows]
            ranks.append([identifier for identifier, score in sorted(matches, key=lambda pair: (-pair[1], pair[0])) if score])
        if mode in {"lexical", "hybrid"} and terms:
            expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
            # No global LIMIT before intersecting eligible root/type/freshness candidates.
            matches = self.db.execute("SELECT rowid,bm25(chunk_fts) AS score FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY score,rowid", (expression,))
            ranks.append([row[0] for row in matches if row[0] in eligible])
        if mode in {"semantic", "hybrid"}:
            if not self.embedder:
                raise ValueError("semantic-model-unavailable-use-lexical-mode")
            if any(row["model"] != self.embedder.identity for row in rows):
                raise ValueError("model-mismatch-create-new-index")
            import numpy as np
            query_vector = (self.embedder.encode_query(query) if hasattr(self.embedder, "encode_query")
                            else self.embedder.encode([query])[0])
            scored = []
            # Blockwise scoring avoids duplicating the entire vector matrix.
            for start in range(0, len(rows), 1024):
                block = rows[start:start + 1024]
                vectors = np.stack([np.frombuffer(row["vector"], dtype="<f4") for row in block])
                scores = vectors @ query_vector
                for row, score in zip(block, scores, strict=True):
                    semantic_scores[row["id"]] = float(score)
                    scored.append((row["id"], float(score)))
            ranks.append([identifier for identifier, score in sorted(scored, key=lambda pair: (-pair[1], pair[0]))])
        fused = {}
        for ranking in ranks:
            # Rank distinct files first so a long file cannot consume the candidate budget.
            files_seen = set()
            file_rank = 0
            for identifier in ranking:
                file_id = eligible[identifier]["file_id"]
                if file_id in files_seen:
                    continue
                files_seen.add(file_id)
                file_rank += 1
                if file_rank > 50:
                    break
                fused[identifier] = fused.get(identifier, 0.0) + 1.0 / (60 + file_rank)
        # Combine contributions at file level; retain best actual evidence chunk.
        grouped = {}
        for identifier, score in fused.items():
            row = eligible[identifier]
            file_id = row["file_id"]
            group = grouped.setdefault(file_id, {"score": 0.0, "evidence_id": identifier, "evidence_score": -1.0})
            group["score"] += score
            if score > group["evidence_score"]:
                group["evidence_id"], group["evidence_score"] = identifier, score
        results = []
        for file_id, group in sorted(grouped.items(), key=lambda pair: (-pair[1]["score"], pair[0])):
            row = eligible[group["evidence_id"]]
            try:
                current = self.db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
                if not current or (current["size"], current["mtime"], current["path"]) != (row["size"], row["mtime"], row["path"]):
                    continue
                self.source_path(file_id, row["digest"])
            except (OSError, ScopeError):
                continue
            results.append({"file_id": file_id, "path": row["path"], "root_id": row["root_id"],
                            "revision": row["digest"],
                            "text": row["text"], "page": row["page"], "line_start": row["line_start"],
                            "line_end": row["line_end"], "rank_score": group["score"],
                            "similarity": semantic_scores.get(row["id"]),
                            "status": "verify-source", "mode": mode})
            if len(results) == limit:
                break
        return results

    def _exact_identifier_results(self, query, root_id, suffix, limit):
        if not 1 <= limit <= 100:
            raise ValueError("query-or-result-limit")
        pattern = re.compile(r"(?<!\w)(?<!\w[-.])" + re.escape(query.strip()) + r"(?!\w|[-.]\w)", re.IGNORECASE)
        results = []
        seen = set()
        rows = sorted(self._eligible(root_id, suffix), key=lambda row: (row["path"].casefold(), row["id"]))
        for row in rows:
            if row["file_id"] in seen or not pattern.search(row["text"]):
                continue
            try:
                path = self.source_path(row["file_id"], row["digest"])
                if str(path) != row["path"]:
                    continue
            except (OSError, ScopeError):
                continue
            seen.add(row["file_id"])
            results.append({"file_id": row["file_id"], "path": row["path"], "root_id": row["root_id"],
                            "revision": row["digest"], "text": row["text"], "page": row["page"],
                            "line_start": row["line_start"], "line_end": row["line_end"],
                            "rank_score": None, "similarity": None, "weak_match": False,
                            "status": "verify-source", "mode": "hybrid", "match_basis": "exact-identifier"})
            if len(results) == limit:
                break
        return results

    def search_response(self, query, mode="hybrid", root_id=None, suffix=None, limit=10,
                        show_weak=False, policy_path=None):
        """Experimental query-level abstention, separate from raw ranking evaluation."""
        if not query.strip():
            return {"status": "empty-query", "results": [], "weak_count": 0}
        if mode == "hybrid" and is_identifier_query(query):
            results = self._exact_identifier_results(query, root_id, suffix, limit)
            return {"status": "exact-identifier-matches" if results else "no-results", "results": results,
                    "weak_count": 0, "retrieval": "exact-identifier", "calibration": "not-applied-literal"}
        results = self.search(query, mode, root_id, suffix, limit)
        if not results:
            return {"status": "no-results", "results": [], "weak_count": 0}
        if mode in {"filename", "lexical"}:
            return {"status": "literal-candidates", "results": results, "weak_count": 0}
        policy_path = policy_path or Path(__file__).resolve().parents[1] / "config/retrieval-policy.json"
        try:
            policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
            threshold = float(policy["models"][self.embedder.identity]["minimum_similarity"])
            if not -1 <= threshold <= 1:
                raise ValueError("invalid-threshold")
        except (OSError, ValueError, KeyError, TypeError):
            return {"status": "uncalibrated-candidates", "results": results, "weak_count": 0}
        best = self.search(query, "semantic", root_id, suffix, 1)
        if not best:
            return {"status": "no-results", "results": [], "weak_count": 0}
        strong = best[0]["similarity"] >= threshold
        for result in results:
            result["weak_match"] = result["similarity"] < threshold
        return {"status": "matches" if strong else "no-strong-match",
                "results": results if strong or show_weak else [],
                "weak_count": sum(result["weak_match"] for result in results),
                "calibration": "experimental-development-only"}

    def source_path(self, file_id, expected_revision=None):
        row = self.db.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        if not row:
            raise ScopeError("file-not-indexed")
        if expected_revision is not None and row["digest"] != expected_revision:
            raise ScopeError("source-changed-refresh-required")
        path = self.authorize(row["root_id"], row["path"])
        info = path.stat()
        if row["status"] != "searchable" or (info.st_size, info.st_mtime_ns) != (row["size"], row["mtime"]):
            raise ScopeError("source-changed-refresh-required")
        return path
