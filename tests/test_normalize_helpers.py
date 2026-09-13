"""Unit tests for normalize-stage config resolution and book-language mapping.

``resolve_config`` decides which normalization profile each book gets (SQL
search config + digit/letter folding); ``book_language`` maps stored language
strings onto the ``Language`` enum. Neither path was directly tested before.
"""

from __future__ import annotations

import uuid

from knowledge_base.database.enums import Language
from knowledge_base.database.models.books import Book
from knowledge_base.pipeline.normalize.processor import book_language, resolve_config


class TestResolveConfig:
    def test_explicit_conservative_wins_regardless_of_language(self) -> None:
        name, config = resolve_config("conservative", Language.ARABIC)
        assert name == "conservative"
        assert config.normalize_digits is False

    def test_explicit_search_wins_regardless_of_language(self) -> None:
        name, config = resolve_config("search", Language.URDU)
        assert name == "search"
        assert config.normalize_digits is True  # search profile folds digits

    def test_auto_arabic_uses_search_config(self) -> None:
        name, config = resolve_config("auto", Language.ARABIC)
        assert name == "search"
        assert config.arabic_normalization == "hamza_alef"
        assert config.normalize_digits is True

    def test_auto_urdu_uses_digit_folding_only(self) -> None:
        name, config = resolve_config("auto", Language.URDU)
        assert name == "urdu"
        assert config.normalize_digits is True
        assert config.arabic_normalization == "none"

    def test_auto_english_falls_back_conservative(self) -> None:
        name, config = resolve_config("auto", Language.ENGLISH)
        assert name == "conservative"
        assert config.normalize_digits is False


class TestBookLanguage:
    def test_matches_names_and_codes(self) -> None:
        assert book_language(_book("ar")) is Language.ARABIC
        assert book_language(_book("arabic")) is Language.ARABIC
        assert book_language(_book("urdu")) is Language.URDU
        assert book_language(_book("ur")) is Language.URDU
        assert book_language(_book("english")) is Language.ENGLISH
        assert book_language(_book("EN")) is Language.ENGLISH

    def test_unknown_falls_back_other(self) -> None:
        assert book_language(_book("french")) is Language.OTHER
        assert book_language(_book("")) is Language.OTHER
        assert book_language(_book(None)) is Language.OTHER

    def test_case_and_whitespace_tolerant(self) -> None:
        assert book_language(_book("  Urdu  ")) is Language.URDU


def _book(language: str | None, title: str = "B") -> Book:
    return Book(title=title, source_file_id=uuid.uuid4(), language=language)
