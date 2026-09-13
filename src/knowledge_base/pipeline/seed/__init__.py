"""Verified dataset seeding (Quran and hadith).

Loads structurally-validated JSON datasets into the canonical tables with full
provenance: every row is anchored to a registered ``SourceFile``. Seeding is
idempotent — natural keys (surah+ayah number, collection+number) make re-runs
safe. Existing rows are never silently overwritten; conflicting text raises
``SeedConflictError`` and rolls the whole seed back.

Note: the loader stores the text provided by the dataset. It performs no
theological validation and never attempts to "correct" or reconstruct sacred
text (see the project's non-negotiable principles).
"""

from __future__ import annotations

from knowledge_base.pipeline.seed.datasets import HadithDataset, QuranDataset
from knowledge_base.pipeline.seed.hadith import seed_hadith
from knowledge_base.pipeline.seed.quran import seed_quran
from knowledge_base.pipeline.seed.report import SeedReport

__all__ = [
    "HadithDataset",
    "QuranDataset",
    "SeedReport",
    "seed_hadith",
    "seed_quran",
]
