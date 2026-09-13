"""OCR engine backends.

The processor talks to a thin :class:`OcrEngine` interface so the pipeline
is engine-agnostic. Real engines are imported **lazily** — calling
:func:`build_engine` for an engine whose software is not installed raises a
helpful :class:`OcrEngineUnavailable` with install pointers (see
``docs/ocr-setup.md``).

Installed engines:

- Tesseract via ``pytesseract`` — supports Arabic, Urdu, English (needs the
  matching ``tessdata`` packs).
- EasyOCR — Arabic and Urdu models bundled with PyTorch.
- ``dummy`` — deterministic backend used by the test suite only.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from knowledge_base.pipeline.ocr.config import OcrConfig


class OcrEngineUnavailable(RuntimeError):
    """Raised when the requested OCR engine cannot be used on this machine."""


class OcrSnippet:
    """Raw output of one OCR pass over one page image.

    ``text`` is the engine's verbatim output — never normalized, padded, or
    corrected (religious text must not be silently altered). ``confidence``
    is a 0-100 float where the engine exposes word-level confidence.
    """

    def __init__(
        self,
        text: str,
        confidence: float | None,
        languages: Sequence[str],
    ) -> None:
        self.text = text
        self.confidence = confidence
        self.languages = tuple(languages)


class OcrEngine(Protocol):
    """Interface implemented by every backend."""

    name: str
    version: str

    def ocr_image(self, image_path: Path, languages: Sequence[str]) -> OcrSnippet:
        """Run OCR on a single rendered page image and return the snippet."""
        ...  # pragma: no cover

    def dispose(self) -> None:
        """Release any heavy in-process resources (models, buffers).

        Called periodically by the processor so long-running jobs do not
        accumulate memory. Implementations without such state do nothing.
        """
        ...  # pragma: no cover


def build_engine(name: str, config: OcrConfig) -> OcrEngine:
    """Return a backend for ``name``; ``name`` may be a fully qualified class
    path for custom engines (``pkg.module:ClassName``)."""
    if name == "dummy":
        return DummyEngine()
    if name == "tesseract":
        return TesseractEngine(config)
    if name == "easyocr":
        return EasyOcrEngine(config)
    if ":" in name:
        module_name, _, class_name = name.partition(":")
        return _load_custom(module_name, class_name)
    raise OcrEngineUnavailable(
        f"Unknown OCR engine {name!r}. Choose from 'tesseract', 'easyocr', or 'dummy'."
    )


def _load_custom(module_name: str, class_name: str) -> OcrEngine:
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise OcrEngineUnavailable(f"Cannot import engine module {module_name!r}: {exc}") from exc
    engine_class = getattr(module, class_name, None)
    if not isinstance(engine_class, type):
        raise OcrEngineUnavailable(f"{module_name}.{class_name} is not a class")
    return cast(OcrEngine, engine_class())


class DummyEngine:
    """Deterministic backend for tests.

    ``by_page`` maps rendered page numbers (derived from the image file name,
    e.g. ``0003.png`` -> 3) to ``(text, confidence)``; unmatched pages fall
    back to ``defaults``.
    """

    name = "dummy"
    version = "0.1.0"

    def __init__(
        self,
        defaults: tuple[str, float] = (
            "The scholars transmitted the hadith with care across many generations",
            95.0,
        ),
        by_page: dict[int, tuple[str, float]] | None = None,
    ) -> None:
        self.defaults = defaults
        self.by_page = by_page or {}

    def ocr_image(self, image_path: Path, languages: Sequence[str]) -> OcrSnippet:
        page = int(image_path.stem)
        text, confidence = self.by_page.get(page, self.defaults)
        return OcrSnippet(text=text, confidence=confidence, languages=languages)

    def dispose(self) -> None:
        pass


class TesseractEngine:
    """Tesseract OCR via ``pytesseract``.

    Requires the ``tesseract`` binary plus ``pytesseract``; Arabic/Urdu need
    the corresponding ``tessdata`` pack. See ``docs/ocr-setup.md``.
    """

    def __init__(self, config: OcrConfig) -> None:
        self.config = config
        self.name = "tesseract"
        self.version = self._resolve_version()

    def _resolve_version(self) -> str:
        try:
            import pytesseract  # type: ignore[import-not-found]
        except ImportError as exc:
            raise OcrEngineUnavailable(
                "pytesseract is not installed. "
                "Run `pip install pytesseract` and install the Tesseract binary "
                "(see docs/ocr-setup.md)."
            ) from exc
        try:
            return str(pytesseract.get_tesseract_version())
        except Exception as exc:  # binary missing
            raise OcrEngineUnavailable(
                "Tesseract binary not found on PATH. Install it and add its folder "
                "to PATH (see docs/ocr-setup.md)."
            ) from exc

    def ocr_image(self, image_path: Path, languages: Sequence[str]) -> OcrSnippet:
        import pytesseract
        from PIL import Image

        lang = "+".join(languages)
        available = set(pytesseract.get_languages(config=""))
        missing = [code for code in languages if code not in available]
        if missing:
            raise OcrEngineUnavailable(
                f"Tesseract lacks traineddata for: {', '.join(missing)}. "
                "Available: "
                + (", ".join(sorted(available)) or "none")
                + " (see docs/ocr-setup.md)."
            )
        config = self.config.extra_tesseract_config or f"--psm {self.config.tesseract_psm}"
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang=lang, config=config)
        confidence = _tesseract_confidence(pytesseract, image, lang, config)
        return OcrSnippet(text=text, confidence=confidence, languages=languages)

    def dispose(self) -> None:
        pass


def _tesseract_confidence(pytesseract: Any, image: Any, lang: str, config: str) -> float | None:
    """Mean word-level confidence (0-100) from ``image_to_data``."""
    try:
        data = pytesseract.image_to_data(
            image, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
    except Exception:
        return None
    confidences = [
        int(conf)
        for conf, word in zip(data["conf"], data["text"], strict=False)
        if word.strip() and int(conf) >= 0
    ]
    if not confidences:
        return None
    return sum(confidences) / len(confidences)


class EasyOcrEngine:
    """EasyOCR (PyTorch) backend with built-in Arabic/Urdu/English models.

    The ``easyocr.Reader`` is created once and reused for every page — model
    initialization is expensive (tens of seconds on CPU) and constructing a
    reader per page also lets PyTorch's allocator grow without bound over a
    long book run. :meth:`dispose` drops the cached reader so the processor
    can recycle it periodically and pin memory usage.
    """

    def __init__(self, config: OcrConfig, gpu: bool = False) -> None:
        self.config = config
        self.gpu = gpu
        self.name = "easyocr"
        self.version = self._resolve_version()
        self._reader: Any | None = None
        self._languages: tuple[str, ...] | None = None

    def _resolve_version(self) -> str:
        try:
            import importlib.metadata

            return importlib.metadata.version("easyocr")
        except Exception as exc:
            raise OcrEngineUnavailable(
                "easyocr is not installed. Run `pip install easyocr` (see docs/ocr-setup.md)."
            ) from exc

    def _ensure_reader(self, languages: Sequence[str]) -> Any:
        key = tuple(languages)
        if self._reader is not None and self._languages == key:
            return self._reader
        import easyocr  # type: ignore[import-untyped]

        try:
            reader = easyocr.Reader(list(languages), gpu=self.gpu, verbose=False)
        except Exception as exc:
            raise OcrEngineUnavailable(
                f"EasyOCR could not start for languages {list(languages)}: {exc}"
            ) from exc
        self._reader = reader
        self._languages = key
        return reader

    def ocr_image(self, image_path: Path, languages: Sequence[str]) -> OcrSnippet:
        reader = self._ensure_reader(languages)
        results = reader.readtext(str(image_path), detail=1, paragraph=False)
        text = "\n".join(content for _bbox, content, _confidence in results)
        confidences = [float(c) for _bbox, _content, c in results]
        confidence = (sum(confidences) / len(confidences) * 100) if confidences else None
        return OcrSnippet(text=text, confidence=confidence, languages=languages)

    def dispose(self) -> None:
        self._reader = None
        self._languages = None
        import gc

        gc.collect()


__all__ = [
    "DummyEngine",
    "EasyOcrEngine",
    "OcrEngine",
    "OcrEngineUnavailable",
    "OcrSnippet",
    "TesseractEngine",
    "build_engine",
]
