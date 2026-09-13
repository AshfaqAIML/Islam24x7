"""Seed the Quran domain from a validated dataset."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.models.quran import Ayah, Surah, Translation
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.pipeline.seed.datasets import AyahPayload, QuranDataset
from knowledge_base.pipeline.seed.report import SeedConflictError, SeedReport


def seed_quran(session: Session, source_file: SourceFile, dataset: QuranDataset) -> SeedReport:
    """Load surahs, ayahs, and translations, ignoring already-seeded rows.

    Idempotency: natural keys are (surah number) and (surah, ayah number); a
    translation is keyed by (language, translator). Existing rows are skipped
    when their text matches; a mismatch raises ``SeedConflictError``.
    """
    report = SeedReport(kind="quran")
    source_file_id = source_file.id

    for surah_payload in dataset.surahs:
        surah = session.scalar(select(Surah).where(Surah.number == surah_payload.number))
        if surah is None:
            surah = Surah(
                number=surah_payload.number,
                name_arabic=surah_payload.name_arabic,
                name_en=surah_payload.name_en,
                name_transliteration=surah_payload.name_transliteration,
                ayah_count=surah_payload.ayah_count,
                revelation_place=surah_payload.revelation_place,
            )
            session.add(surah)
            session.flush()
            report.created += 1
        else:
            report.skipped += 1

        for ayah_payload in surah_payload.ayahs:
            _upsert_ayah(session, surah, source_file_id, ayah_payload, dataset, report)

    return report


def _upsert_ayah(
    session: Session,
    surah: Surah,
    source_file_id: UUID,
    ayah_payload: AyahPayload,
    dataset: QuranDataset,
    report: SeedReport,
) -> None:
    ayah = session.scalar(
        select(Ayah).where(Ayah.surah_id == surah.id, Ayah.number == ayah_payload.number)
    )
    if ayah is None:
        ayah = Ayah(
            surah_id=surah.id,
            source_file_id=source_file_id,
            number=ayah_payload.number,
            text=ayah_payload.text,
            page_number=ayah_payload.page,
            juz=ayah_payload.juz,
        )
        session.add(ayah)
        session.flush()
        report.created += 1
    elif ayah.text != ayah_payload.text:
        raise SeedConflictError(
            f"ayah {surah.number}:{ayah_payload.number} already exists with "
            "different text; refusing to overwrite"
        )
    else:
        report.skipped += 1

    if ayah_payload.translation:
        translation = session.scalar(
            select(Translation).where(
                Translation.ayah_id == ayah.id,
                Translation.language == dataset.language,
                Translation.translator == dataset.translator,
            )
        )
        if translation is None:
            session.add(
                Translation(
                    ayah_id=ayah.id,
                    source_file_id=source_file_id,
                    language=dataset.language,
                    translator=dataset.translator,
                    text=ayah_payload.translation,
                )
            )
            report.created += 1
        elif translation.text != ayah_payload.translation:
            raise SeedConflictError(
                f"translation {surah.number}:{ayah_payload.number} "
                f"({dataset.language}/{dataset.translator}) already exists with "
                "different text; refusing to overwrite"
            )
        else:
            report.skipped += 1
