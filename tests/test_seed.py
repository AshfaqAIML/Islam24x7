"""Tests for verified Quran/hadith dataset seeding (idempotent, provenance-anchored)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import SourceFormat, SourceStatus
from knowledge_base.database.models.hadith import Collection, Hadith
from knowledge_base.database.models.quran import Ayah, Surah, Translation
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.pipeline.seed import (
    HadithDataset,
    QuranDataset,
    seed_hadith,
    seed_quran,
)
from knowledge_base.pipeline.seed.report import SeedConflictError

QURAN_FIXTURE = {
    "translator": "Fixture Translator",
    "language": "en",
    "surahs": [
        {
            "number": 1,
            "name_arabic": "الفاتحة",
            "name_en": "The Opening",
            "name_transliteration": "Al-Fatihah",
            "ayah_count": 2,
            "revelation_place": "meccan",
            "ayahs": [
                {
                    "number": 1,
                    "text": "بِسْمِ اللهِ الرَّحْمَنِ الرَّحِيمِ (fixture baj)",
                    "translation": "In the name of Allah (fixture).",
                    "juz": 1,
                    "page": 1,
                },
                {
                    "number": 2,
                    "text": "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ (fixture fixture)",
                    "translation": "All praise is for Allah (fixture).",
                    "juz": 1,
                    "page": 1,
                },
            ],
        },
        {
            "number": 2,
            "name_arabic": "البقرة",
            "name_en": "The Cow",
            "name_transliteration": "Al-Baqarah",
            "ayahs": [
                {
                    "number": 1,
                    "text": "الم (fixture fixture)",
                    "translation": "Alif Lam Mim (fixture).",
                }
            ],
        },
    ],
}

HADITH_FIXTURE = {
    "collection": "Fixture Collection",
    "title": "مجموعة تجريبية",
    "author": "Test Author",
    "hadiths": [
        {
            "number": 1,
            "text": "Actions are by intentions (fixture).",
            "text_arabic": "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ (fixture)",
            "book": "Book of Intentions",
            "chapter": "How intentions matter",
            "narrator": "Umar (fixture)",
            "grade": "Sahih (fixture)",
        },
        {
            "number": 2,
            "text": "Religion is sincere advice (fixture).",
            "text_arabic": "الدِّينُ النَّصِيحَةُ (fixture)",
        },
    ],
}


@pytest.fixture()
def sf(db: Session) -> SourceFile:
    source = SourceFile(
        sha256="22" * 32,
        file_path="fixtures/dataset.json",
        format=SourceFormat.JSON,
        status=SourceStatus.REGISTERED,
    )
    db.add(source)
    db.flush()
    return source


_TEST_URL = "postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test"


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import knowledge_base.config as _config

    _config._SINGLETON = None
    monkeypatch.setenv("KB_DATABASE_URL", _TEST_URL)
    monkeypatch.setenv("KB_TEST_DATABASE_URL", _TEST_URL)
    monkeypatch.setenv("KB_LOG_LEVEL", "ERROR")
    yield
    _config._SINGLETON = None


class TestQuran:
    def test_seed_creates_rows_with_provenance(self, sf: SourceFile, db: Session) -> None:
        report = seed_quran(db, sf, QuranDataset.model_validate(QURAN_FIXTURE))
        db.commit()

        assert report.created == 8  # 2 surahs + 3 ayahs + 3 translations
        surahs = db.scalars(select(Surah).order_by(Surah.number)).all()
        assert [s.number for s in surahs] == [1, 2]
        ayahs = db.scalars(select(Ayah).order_by(Ayah.number)).all()
        assert len(ayahs) == 3
        assert all(a.source_file_id == sf.id for a in ayahs)
        translations = db.scalars(select(Translation)).all()
        assert len(translations) == 3
        assert all(t.translator == "Fixture Translator" for t in translations)
        assert ayahs[0].text.startswith("بِسْمِ")

    def test_seed_is_idempotent(self, sf: SourceFile, db: Session) -> None:
        dataset = QuranDataset.model_validate(QURAN_FIXTURE)
        first = seed_quran(db, sf, dataset)
        db.commit()
        second = seed_quran(db, sf, dataset)
        db.commit()
        assert first.created == 8
        assert second.created == 0
        assert second.skipped >= 8
        assert db.scalar(select(Ayah.number).order_by(Ayah.number)) is not None
        assert db.scalar(select(Surah).where(Surah.number == 1)) is not None

    def test_conflicting_ayah_text_raises_and_rolls_back(self, sf: SourceFile, db: Session) -> None:
        seed_quran(db, sf, QuranDataset.model_validate(QURAN_FIXTURE))
        db.commit()

        conflicting = json.loads(json.dumps(QURAN_FIXTURE))
        conflicting["surahs"][0]["ayahs"][0]["text"] = "different text"

        with pytest.raises(SeedConflictError, match="refusing to overwrite"):
            seed_quran(db, sf, QuranDataset.model_validate(conflicting))

        ayah = db.scalar(select(Ayah).where(Ayah.number == 1))
        assert ayah is not None
        assert ayah.text != "different text"

    def test_payload_validation(self, sf: SourceFile, db: Session) -> None:
        import copy

        from pydantic import ValidationError

        bad = copy.deepcopy(QURAN_FIXTURE)
        bad["surahs"][0]["number"] = 999
        with pytest.raises(ValidationError):
            QuranDataset.model_validate(bad)

        with pytest.raises(ValidationError):
            QuranDataset.model_validate({"translator": ""})


class TestHadith:
    def test_seed_creates_collection_and_hadiths(self, sf: SourceFile, db: Session) -> None:
        report = seed_hadith(db, sf, HadithDataset.model_validate(HADITH_FIXTURE))
        db.commit()

        collection = db.scalar(select(Collection).where(Collection.name == "Fixture Collection"))
        assert collection is not None
        assert report.created == 5  # collection + book + chapter + 2 hadiths
        hadiths = db.scalars(select(Hadith).order_by(Hadith.number)).all()
        assert [h.number for h in hadiths] == [1, 2]
        assert all(h.source_file_id == sf.id for h in hadiths)
        assert hadiths[0].hadith_book is not None
        assert hadiths[0].hadith_chapter is not None

    def test_seed_is_idempotent(self, sf: SourceFile, db: Session) -> None:
        dataset = HadithDataset.model_validate(HADITH_FIXTURE)
        first = seed_hadith(db, sf, dataset)
        db.commit()
        second = seed_hadith(db, sf, dataset)
        db.commit()
        assert first.created == 5
        assert second.created == 0
        assert db.scalar(select(Collection)) is not None

    def test_conflicting_hadith_raises(self, sf: SourceFile, db: Session) -> None:
        seed_hadith(db, sf, HadithDataset.model_validate(HADITH_FIXTURE))
        db.commit()

        conflicting = json.loads(json.dumps(HADITH_FIXTURE))
        conflicting["hadiths"][0]["text"] = "changed text"

        with pytest.raises(SeedConflictError, match="refusing to overwrite"):
            seed_hadith(db, sf, HadithDataset.model_validate(conflicting))

        hadith = db.scalar(select(Hadith).where(Hadith.number == 1))
        assert hadith is not None
        assert hadith.text != "changed text"


class TestCli:
    def test_seed_quran_json_roundtrip(
        self, db_engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from knowledge_base.cli.kb import main

        path = tmp_path / "quran.json"
        path.write_text(json.dumps(QURAN_FIXTURE), encoding="utf-8")
        code = main(["--json", "seed-quran", "--file", str(path)])
        assert code == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["created"] == 8
        assert "source" in payload

    def test_seed_hadith_roundtrip(
        self, db_engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from knowledge_base.cli.kb import main

        path = tmp_path / "hadith.json"
        path.write_text(json.dumps(HADITH_FIXTURE), encoding="utf-8")
        code = main(["--json", "seed-hadith", "--file", str(path)])
        assert code == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["kind"] == "hadith"
        assert payload["created"] >= 3

    def test_seed_missing_file_exits_1(
        self, db_engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from knowledge_base.cli.kb import main

        code = main(["seed-quran", "--file", str(tmp_path / "nope.json")])
        assert code == 1
        assert "dataset not found" in capsys.readouterr().err

    def test_seed_invalid_dataset_exits_1(
        self, db_engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from knowledge_base.cli.kb import main

        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"translator": "", "surahs": []}), encoding="utf-8")
        code = main(["seed-quran", "--file", str(path)])
        assert code == 1
        assert "invalid quran dataset" in capsys.readouterr().err
