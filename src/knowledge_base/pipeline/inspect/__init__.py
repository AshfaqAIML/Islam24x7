"""PDF inspection and classification.

Uses lightweight PyMuPDF heuristics to classify a source as ``TEXT_PDF``,
``SCANNED_PDF``, ``MIXED_PDF`` or ``INVALID_PDF`` and writes inspection
reports under ``data/processed/inspections/``.
"""