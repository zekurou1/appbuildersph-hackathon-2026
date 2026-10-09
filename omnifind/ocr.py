"""Installed Windows English OCR; no downloads or remote fallback."""
import asyncio
import platform
from pathlib import Path

MAX_IMAGE_PIXELS = 4_000_000
MAX_IMAGE_EDGE = 6000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def image_header(path):
    from PIL import Image
    try:
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("image-format-unsupported")
            expected = "PNG" if Path(path).suffix.lower() == ".png" else "JPEG"
            if image.format != expected:
                raise ValueError("image-format-mismatch")
            if image.width * image.height > MAX_IMAGE_PIXELS or max(image.size) > MAX_IMAGE_EDGE:
                raise ValueError("ocr-image-too-large")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("animated-image-unsupported")
            return image.size
    except ValueError:
        raise
    except Exception:
        raise ValueError("image-unreadable") from None


async def _recognize(path):
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage import StorageFile
        from winrt.windows.graphics.imaging import BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode
    except (ImportError, OSError):
        raise ValueError("ocr-runtime-unavailable") from None
    engine = OcrEngine.try_create_from_language(Language("en-US"))
    if engine is None:
        raise ValueError("ocr-english-unavailable")
    stream = bitmap = None
    try:
        source = await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
        stream = await source.open_read_async()
        decoder = await BitmapDecoder.create_async(stream)
        width, height = decoder.pixel_width, decoder.pixel_height
        if width * height > MAX_IMAGE_PIXELS or max(width, height) > min(MAX_IMAGE_EDGE, OcrEngine.max_image_dimension):
            raise ValueError("ocr-image-too-large")
        bitmap = await decoder.get_software_bitmap_converted_async(BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED)
        result = await engine.recognize_async(bitmap)
        text = "\n".join(line.text for line in result.lines)
        if not text.strip():
            raise ValueError("ocr-no-readable-text")
        return text
    finally:
        if bitmap:
            bitmap.close()
        if stream:
            stream.close()


def recognize(path):
    image_header(path)
    try:
        return asyncio.run(_recognize(path))
    except ValueError:
        raise
    except Exception:
        raise ValueError("ocr-recognition-failed") from None


def runtime_info():
    from importlib.metadata import version
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    return {"engine": "Windows.Media.Ocr", "language": "en-US", "os": platform.platform(),
            "binding_version": version("winrt-Windows.Media.Ocr"),
            "english_available": OcrEngine.try_create_from_language(Language("en-US")) is not None,
            "model_assets": "Installed Windows OCR language components; OS-managed, not a separately pinned weight file",
            "max_image_pixels": MAX_IMAGE_PIXELS, "max_image_edge": MAX_IMAGE_EDGE}
