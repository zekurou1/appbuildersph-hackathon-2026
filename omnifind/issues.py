"""Deterministic recovery copy; never render raw parser errors as instructions."""

def issue_copy(state, error):
    states = {
        "stale": "The original changed. Refresh its folder to update search evidence.",
        "missing": "The original is missing. Restore it if needed, then refresh to reconcile this folder.",
        "unavailable": "The original is unavailable or excluded. Check local availability and folder access, then refresh.",
        "unsupported": "This format is not supported. Use digital PDF, TXT, MD or readable English PNG/JPEG.",
        "pending": "This file has not finished indexing. Refresh its folder to continue.",
    }
    if state in states:
        return states[state]
    errors = {
        "ocr-runtime-unavailable": "Windows OCR components are unavailable. Check local setup, then refresh.",
        "ocr-english-unavailable": "Windows English OCR is unavailable. Install the English OCR language component through Windows settings, then refresh.",
        "ocr-recognition-failed": "Windows could not recognize this image. Check OCR setup or try a clearer supported image, then refresh.",
        "ocr-no-readable-text": "No readable English text was recognized. Try a clearer text-bearing image; visual scene search is not supported.",
        "ocr-image-too-large": "This image exceeds four million pixels or a 6000-pixel edge. Make a smaller copy outside OmniFind, then refresh.",
        "image-unreadable": "This image could not be decoded. Check the original in a trusted viewer or use a valid PNG/JPEG copy.",
        "image-format-mismatch": "The image format does not match its extension. Use a correctly exported PNG/JPEG copy.",
        "animated-image-unsupported": "Animated images are not supported. Export a single still image, then refresh.",
        "no-digital-text": "No digital text was found. Scanned PDF text recognition is not supported yet.",
        "encrypted-pdf": "Encrypted PDFs are not supported. If authorized, provide an unlocked copy outside OmniFind.",
        "file-too-large": "This file exceeds the 20 MiB input limit. Use a smaller copy, then refresh.",
        "too-many-pages": "This PDF exceeds 200 pages. Use a shorter copy, then refresh.",
        "text-too-large": "Extracted text exceeds the input limit. Use a shorter file, then refresh.",
        "extraction-timeout": "Reading this file exceeded the time limit. Try a simpler copy, then refresh.",
        "scope-or-placeholder": "Links and cloud-only placeholders are excluded. Use an available local original in a selected folder.",
    }
    return errors.get(error, "This file could not be indexed. Check its format, local availability and setup, then refresh. Other indexed files remain searchable.")
