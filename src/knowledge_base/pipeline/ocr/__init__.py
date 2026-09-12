"""OCR for scanned Islamic material.

Runs EasyOCR (default ``ar`` + ``en``, configurable to include ``ur``) on
pages with no usable text layer, and provides a documented Tesseract
alternative. Low-confidence results are flagged for review.
"""