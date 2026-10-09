"""Bounded, killable digital-text extraction worker; no OCR claim."""
import json
import sys
from pathlib import Path

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
MAX_TEXT_CHARS = 2_000_000
SUPPORTED = {".pdf", ".txt", ".md"}


def extract(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file-too-large")
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("encrypted-pdf")
        if len(reader.pages) > MAX_PAGES:
            raise ValueError("too-many-pages")
        sections = []
        length = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            length += len(text)
            if length > MAX_TEXT_CHARS:
                raise ValueError("text-too-large")
            if text.strip():
                sections.append({"text": text, "page": number})
    else:
        text = path.read_text(encoding="utf-8-sig")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError("text-too-large")
        sections = [{"text": text, "page": None}] if text.strip() else []
    if not sections:
        raise ValueError("no-digital-text")
    return sections


if __name__ == "__main__":
    try:
        from omnifind.core import ordinary_path, ScopeError
        root = ordinary_path(sys.argv[2])
        source = ordinary_path(sys.argv[1])
        if not source.is_relative_to(root):
            raise ScopeError("outside-selected-folder")
        print(json.dumps({"sections": extract(source)}))
    except Exception as error:
        # Do not print paths, content or parser tracebacks.
        code = str(error) if isinstance(error, ValueError) else "extraction-failed"
        print(json.dumps({"error": code}))
        sys.exit(1)
