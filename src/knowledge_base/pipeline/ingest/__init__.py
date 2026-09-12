"""Ingestion of source material.

Registers files under ``data/raw/``, computes their SHA-256 source ids,
moves files that fail registration into ``data/quarantine/``, and records
licensing/edition metadata. Consumed by :mod:`knowledge_base.pipeline.inspect`.
"""