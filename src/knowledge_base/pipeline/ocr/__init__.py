"""OCR pipeline stage: detect, render, transcribe, and review scanned pages."""

from knowledge_base.pipeline.ocr.config import DEFAULT_OCR_CONFIG, OcrConfig
from knowledge_base.pipeline.ocr.engines import (
    DummyEngine,
    OcrEngine,
    OcrEngineUnavailable,
    OcrSnippet,
    build_engine,
)
from knowledge_base.pipeline.ocr.processor import (
    OcrResult,
    assess_quality,
    density_chars,
    ocr_all,
    ocr_file,
    plan_ocr_pages,
)

__all__ = [
    "DEFAULT_OCR_CONFIG",
    "DummyEngine",
    "OcrConfig",
    "OcrEngine",
    "OcrEngineUnavailable",
    "OcrResult",
    "OcrSnippet",
    "assess_quality",
    "build_engine",
    "density_chars",
    "ocr_all",
    "ocr_file",
    "plan_ocr_pages",
]