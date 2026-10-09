"""Bounded original-image thumbnail, executed only in the parser Job Object."""
import base64
import hashlib
import io
import json
import sys

from .core import ordinary_path
from .extract import MAX_FILE_BYTES
from .ocr import image_header


def thumbnail(path, root, expected_digest):
    path, root = ordinary_path(path), ordinary_path(root)
    if not path.is_relative_to(root):
        raise ValueError("outside-selected-folder")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file-too-large")
    def verify():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected_digest:
                raise ValueError("source-changed-refresh-required")
    verify()
    image_header(path)
    from PIL import Image
    with Image.open(path) as original:
        original.thumbnail((640, 360))
        image = original.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="PNG")
    verify()
    return {"png": base64.b64encode(output.getvalue()).decode("ascii"), "width": image.width, "height": image.height}


if __name__ == "__main__":
    try:
        print(json.dumps(thumbnail(*sys.argv[1:4])))
    except Exception as error:
        print(json.dumps({"error": str(error) if isinstance(error, ValueError) else "thumbnail-failed"}))
        sys.exit(1)
