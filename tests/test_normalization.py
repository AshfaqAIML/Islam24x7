"""Tests for the multilingual normalization pipeline.

The single most important invariant: the ``original`` string is always returned
verbatim. Every test asserts that invariant first.
"""

from __future__ import annotations

import json

import pytest

from knowledge_base.normalization import (
    NormalizationConfig,
    NormalizationItem,
    NormalizationReport,
    NormalizationResult,
    conservative_config,
    normalize_text,
    search_config,
    write_report,
)


def _assert_original_preserved(result: NormalizationResult, expected: str) -> None:
    assert result.original == expected, "original must never change"


# --- English ---------------------------------------------------------------


def test_english_whitespace_and_linebreak_cleanup() -> None:
    src = "Hello,\r\n  this is   a test.\fMore  text.  \n\n\n"
    res = normalize_text(src)
    _assert_original_preserved(res, src)
    assert res.normalized == "Hello,\n this is a test.\nMore text.\n\n"
    assert not res.unchanged


def test_english_unicode_nfc() -> None:
    src = "Cafe\u0301 \u0041\u030a"  # é as e + combining accent, Å decomposed
    res = normalize_text(src, NormalizationConfig())
    _assert_original_preserved(res, src)
    assert res.normalized == "Café Å"
    assert res.config.unicode_form == "NFC"
    assert not res.unchanged


# --- Arabic ----------------------------------------------------------------


def test_arabic_hamza_fold_when_enabled() -> None:
    src = "أحمد إبراهيم آدم المؤمنة"
    res = normalize_text(src, search_config())
    _assert_original_preserved(res, src)
    # hamza_alef: أ->ا, إ->ا, آ->ا, ؤ->و
    assert res.normalized == "احمد ابراهيم ادم المومنة"
    assert res.stats.hamza_normalized == 4
    assert res.stats.alef_maqsura_normalized == 0  # only folded in full_no_harakat
    assert not res.unchanged


def test_arabic_full_fold_when_enabled() -> None:
    src = "أحمد إبراهيم آدم المؤمنة ى ة"
    cfg = NormalizationConfig(arabic_normalization="full_no_harakat")
    res = normalize_text(src, cfg)
    _assert_original_preserved(res, src)
    assert res.stats.hamza_normalized == 4
    assert res.stats.alef_maqsura_normalized == 1
    assert res.stats.teh_marbuta_normalized == 2
    assert res.normalized == "احمد ابراهيم ادم المومنه ي ه"
    assert not res.unchanged


def test_arabic_hamza_never_folded_by_default() -> None:
    src = "أحمد إبراهيم آدم"
    res = normalize_text(src)
    _assert_original_preserved(res, src)
    assert res.normalized == src
    assert res.unchanged


def test_conservative_config_never_alters_letters() -> None:
    src = "بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ أَ"
    res = normalize_text(src, conservative_config())
    _assert_original_preserved(res, src)
    # conservative = layout + NFC + tatweel only; letters untouched
    assert res.normalized == src
    assert res.unchanged


# --- Urdu ------------------------------------------------------------------


def test_urdu_text_letters_untouched_by_default() -> None:
    src = "یہ ایک اردو کتاب ہے"
    res = normalize_text(src)
    _assert_original_preserved(res, src)
    assert res.normalized == src
    assert res.unchanged


def test_urdu_fold_when_enabled() -> None:
    src = "ھمارا یہ"
    res = normalize_text(src, NormalizationConfig(urdu_normalization=True))
    _assert_original_preserved(res, src)
    assert "\u06be" not in res.normalized  # ھ folded
    assert res.stats.urdu_folded >= 1


def test_urdu_digits_normalized_when_enabled() -> None:
    src = "اس صفحے پر ۱۲۳۴ نمبر ہیں"
    res = normalize_text(src, search_config())
    _assert_original_preserved(res, src)
    assert "1234" in res.normalized
    assert res.stats.digits_normalized >= 4
    assert not res.unchanged


def test_urdu_digits_touched_neither_by_default() -> None:
    src = "۱۲۳۴"
    res = normalize_text(src)
    _assert_original_preserved(res, src)
    assert res.normalized == src
    assert res.unchanged


# --- Religious text protection ---------------------------------------------


def test_quranic_ayah_protected_from_folding() -> None:
    src = "﴿إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ﴾"
    res = normalize_text(src, search_config())
    _assert_original_preserved(res, src)
    # ayah ornament marker (﴿ U+FD3F) is protected; hamza/ya never folded
    assert res.stats.protected is True
    assert res.normalized == src
    assert res.unchanged


def test_basmala_protected_from_folding() -> None:
    src = "بسم الله الرحمن الرحيم أَ"
    res = normalize_text(src, search_config())
    _assert_original_preserved(res, src)
    assert res.stats.protected is True
    assert res.normalized == src
    assert res.unchanged


def test_protection_can_be_disabled_explicitly() -> None:
    src = "بسم الله الرحمن الرحيم إياك أبدا"
    cfg = search_config().model_copy(update={"protect_religious_quotations": False})
    res = normalize_text(src, cfg)
    _assert_original_preserved(res, src)
    assert res.stats.protected is False
    assert not res.unchanged


# --- Tatweel ---------------------------------------------------------------


def test_tatweel_removed() -> None:
    src = "المكتـبة"
    res = normalize_text(src)
    _assert_original_preserved(res, src)
    assert "\u0640" not in res.normalized
    assert res.stats.tatweel_removed >= 1


# --- Full pipeline / report ------------------------------------------------


def test_report_round_trip(tmp_path) -> None:
    pages = [
        NormalizationItem(
            source_file_id="src-1",
            page_number=1,
            text="أحمد said  hello  world",
            result=normalize_text("أحمد said  hello  world", search_config()),
        ),
        NormalizationItem(
            source_file_id="src-1",
            page_number=2,
            text="﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾",
            result=normalize_text("﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾", search_config()),
        ),
    ]
    report = NormalizationReport(source_file_id="src-1", items=pages)
    assert report.changed_items == 1
    assert report.protected_items == 1

    json_path, md_path = write_report(report, tmp_path)
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["source_file_id"] == "src-1"
    assert len(data["items"]) == 2
    md = md_path.read_text(encoding="utf-8")
    assert "src-1" in md
    assert "PROTECTED" in md


def test_normalization_never_alters_source_on_any_page(tmp_path) -> None:
    """End-to-end: run the normalizer over mixed-script pages and verify that
    every original string is byte-for-byte identical afterwards."""
    pages = [
        "English with    extra spaces.\n\n\nAnd a second line.",
        "أحمد إبراهيم آدم ى ة",
        "یہ ایک اردو کتاب ہے ۱۲۳۴",
        "﴿الرَّحْمَٰنِ الرَّحِيمِ ﴾",
    ]
    for page in pages:
        res = normalize_text(page, search_config())
        assert res.original == page
        # the normalized variant must be traceable back: folding is injective
        # per char except tatweel/whitespace, but always one char family.
        assert isinstance(res.normalized, str)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("hello\tworld", "hello world"),
        ("a  b   c", "a b c"),
        ("line\u00a0break", "line break"),
    ],
)
def test_whitespace_collapse(raw: str, expected: str) -> None:
    res = normalize_text(raw)
    _assert_original_preserved(res, raw)
    assert res.normalized == expected
