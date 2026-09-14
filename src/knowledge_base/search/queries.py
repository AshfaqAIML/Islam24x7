"""Search query parsing and normalization.

A user query is decomposed into ``terms`` (single keywords) and ``phrases``
(double-quoted exact phrases). Keywords are normalized using the same
language-appropriate rules the indexing pipeline applied to the stored text
(with ``resolve_config``/``normalize_text``), then reassembled into a
``websearch_to_tsquery``-compatible string so PostgreSQL handles phrase,
AND/OR and exclusion syntax in one step — always with the ``simple`` text
search configuration, because every stored vector also carries a verbatim
``simple`` component and the stored text is already normalized.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from knowledge_base.database.enums import Language
from knowledge_base.normalization import normalize_text
from knowledge_base.pipeline.normalize.processor import resolve_config
from knowledge_base.search.arabic import normalize_arabic_search

_QUOTED = re.compile(r'"([^"]+)"')


@dataclass(frozen=True)
class ParsedQuery:
    """A parsed query: keyword terms plus exact-phrase quotes."""

    terms: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.terms and not self.phrases


def parse_query(text: str) -> ParsedQuery:
    """Split ``text`` into keyword terms and double-quoted phrases."""
    text = text.strip()
    if not text:
        return ParsedQuery()
    phrases = tuple(m.group(1).strip() for m in _QUOTED.finditer(text) if m.group(1).strip())
    remainder = _QUOTED.sub(" ", text)
    terms = tuple(t for t in remainder.split() if t and not set(t).issubset('" '))
    return ParsedQuery(terms=terms, phrases=phrases)


_URDU_LETTERS = frozenset("ٹڈڑںہےئ")


def sniff_language(text: str) -> Language:
    """Guess whether a query is Arabic, Urdu, or Latin-script text."""
    if re.search(r"[\u0600-\u06FF\u0750-\u077F]", text):
        if any(ch in text for ch in _URDU_LETTERS):
            return Language.URDU
        return Language.ARABIC
    return Language.ENGLISH


def normalize_query_text(text: str, language: Language | None = None) -> str:
    """Normalize query text with the same rules the index applied to content."""
    if language is None:
        language = sniff_language(text)
    _, config = resolve_config("auto", language)
    normalized = normalize_text(text, config).normalized
    if language is Language.ARABIC:
        normalized = normalize_arabic_search(normalized)
    return normalized


def build_websearch(query: str, *, all_terms: bool = False) -> str:
    """Turn ``query`` into a websearch expression (empty if nothing to match).

    * double-quoted runs become exact phrases (``"..."``),
    * other words become keywords joined by ``OR`` (default, any-term) or by
      spaces (``all_terms``, every keyword required),
    * phrases and keywords are ANDed together.
    """
    parsed = parse_query(query)
    if parsed.is_empty():
        return ""
    parts: list[str] = []
    if parsed.phrases:
        parts.extend(f'"{normalize_query_text(p)}"' for p in parsed.phrases)
    terms = [t for t in (normalize_query_text(t) for t in parsed.terms) if t]
    if terms:
        parts.append(" ".join(terms) if all_terms else " OR ".join(terms))
    return " ".join(parts)


__all__ = [
    "ParsedQuery",
    "build_websearch",
    "normalize_query_text",
    "parse_query",
    "sniff_language",
]
