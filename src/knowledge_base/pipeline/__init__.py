"""Ingestion pipeline: source to validated, traceable knowledge base.

Stages run in sequence — each is idempotent and resumable and writes only
derived artifacts; the raw source is never modified:

    ingest → inspect → extract → ocr → metadata → structure → normalization
    → chunk → index → embed → validate

Normalization is implemented in :mod:`knowledge_base.normalization` (not yet
moved under ``pipeline/normalize``).
"""