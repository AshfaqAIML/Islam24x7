"""Arabic normalization for search.

Uzbek/quranic Orthography uses Unicode variants that defeat verbatim token
matching: the definitive article can be written with alef-wasla U+0671, long
vowels with superscript alef U+0670, hamza-carrying alefs (U+0622/0623/0625)
and alef-maksura U+0649. Diacritics (U+064B-U+065F) further fragment tokens.

``normalize_arabic_search`` maps those variants to their plain forms, drops the
superscript alef (U+0670, a vowel marker — the plain spelling uses no letter
for that vowel) and strips diacritics so that a user query typed without
diacritics (e.g. ``الرحمن``) matches stored text written with full Qur'anic
orthography (``ٱلرَّحْمَٰنِ``). The same function is applied on both the
indexing side (``ayahs.search_vector_norm``) and the query side so both sides
agree.
"""

from __future__ import annotations

import re
import unicodedata

_COMBINING_MARKS_RE = re.compile(
    "["
    "\u0640"  # tatweel
    "\u064b-\u065f"  # Qur'anic pointing (fathatan..small waw)
    "\u0670"  # superscript alef (carries the long vowel, not a letter)
    "]"
)

_TRANSLATION = str.maketrans(
    {
        "\u0671": "\u0627",  # alef wasla   -> alef
        "\u0649": "\u064a",  # alef maksura -> ya
        "\u0622": "\u0627",  # alef madda   -> alef
        "\u0623": "\u0627",  # alef hamza above -> alef
        "\u0625": "\u0627",  # alef hamza below -> alef
    }
)


def normalize_arabic_search(text: str) -> str:
    """Return ``text`` with diacritics stripped and variant letters normalized."""
    if not text:
        return text
    decomposed = _COMBINING_MARKS_RE.sub("", text)
    # NFC folds basic combining marks still present after the regex (safety).
    folded = unicodedata.normalize("NFC", decomposed)
    return folded.translate(_TRANSLATION)
