"""Page-by-page text extraction from PDFs.

Uses PyMuPDF ``get_text("dict")`` with geometry-sorted reading order. Produces
an ``Extraction`` model per page (source id, page number, text, method,
status) written to ``data/processed/extracted/``.
"""