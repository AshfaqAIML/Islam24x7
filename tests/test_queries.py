"""Tests for search query parsing and normalization (``search.queries``).

These builders were previously only exercised indirectly through the search
engine; here we test the parsing contracts directly.
"""

from __future__ import annotations

from knowledge_base.database.enums import Language
from knowledge_base.search.queries import (
    build_websearch,
    normalize_query_text,
    parse_query,
    sniff_language,
)


class TestParseQuery:
    def test_empty_string(self) -> None:
        parsed = parse_query("   ")
        assert parsed.is_empty()

    def test_plain_terms(self) -> None:
        parsed = parse_query("patience and perseverance")
        assert parsed.terms == ("patience", "and", "perseverance")
        assert parsed.phrases == ()

    def test_quoted_phrase(self) -> None:
        parsed = parse_query('say "the truth" now')
        assert parsed.phrases == ("the truth",)
        assert parsed.terms == ("say", "now")

    def test_phrase_only(self) -> None:
        parsed = parse_query('"the straight path"')
        assert parsed.terms == ()
        assert parsed.phrases == ("the straight path",)

    def test_empty_quotes_are_skipped(self) -> None:
        parsed = parse_query('plain "" and words')
        assert parsed.phrases == ()
        assert parsed.terms == ("plain", "and", "words")

    def test_only_stray_quotes_give_empty(self) -> None:
        parsed = parse_query('"" ""')
        assert parsed.is_empty()


class TestSniffLanguage:
    def test_arabic(self) -> None:
        assert sniff_language("السلام") is Language.ARABIC

    def test_urdu_characters(self) -> None:
        assert sniff_language("ٹھیک") is Language.URDU

    def test_english(self) -> None:
        assert sniff_language("patience") is Language.ENGLISH

    def test_extended_arabic_block(self) -> None:
        assert sniff_language("\u0775 test") is Language.ARABIC


class TestBuildWebsearch:
    def test_empty_query_gives_empty(self) -> None:
        assert build_websearch("  ") == ""

    def test_any_terms_use_or(self) -> None:
        expr = build_websearch("sabr virtue")
        assert "sabr" in expr and "virtue" in expr and " OR " in expr

    def test_all_terms_use_space(self) -> None:
        expr = build_websearch("sabr virtue", all_terms=True)
        assert " OR " not in expr
        assert "sabr" in expr and "virtue" in expr

    def test_phrase_preserved_with_quotes(self) -> None:
        expr = build_websearch('fasting "in the month"')
        assert '"' in expr
        assert "fasting" in expr

    def test_arabic_norm_keeps_letters(self) -> None:
        expr = build_websearch("الصبر", all_terms=True)
        assert expr  # non-empty after normalization


class TestNormalizeQueryText:
    def test_case_preserved_for_english(self) -> None:
        # Matching runs through PostgreSQL's `simple` config, which folds case;
        # the builder itself is case-preserving.
        assert normalize_query_text("Patience") == "Patience"

    def test_arabic_hamza_folded(self) -> None:
        assert normalize_query_text("أحمد", Language.ARABIC) == "احمد"
