"""Validation and provenance audit.

Structural, content, and provenance checks run after indexing: page/order
integrity, garbled-text detection, Quran/hadith cross-checks, orphaned chunk
detection. Failures move sources to ``data/quarantine/``.
"""