"""Pydantic dataset schemas for Quran and hadith seeding."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AyahPayload(BaseModel):
    number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    translation: str | None = None
    juz: int | None = Field(default=None, ge=1, le=30)
    page: int | None = Field(default=None, ge=1)


class SurahPayload(BaseModel):
    number: int = Field(..., ge=1, le=114)
    name_arabic: str = Field(..., min_length=1)
    name_en: str | None = None
    name_transliteration: str | None = None
    ayah_count: int | None = Field(default=None, ge=1)
    revelation_place: str | None = None
    ayahs: list[AyahPayload] = Field(default_factory=list)


class QuranDataset(BaseModel):
    """A curated Quran dataset: surahs, ayahs, and a named translation."""

    translator: str = Field(..., min_length=1)
    language: str = Field(default="en", pattern="^[a-z]{2,16}$")
    surahs: list[SurahPayload] = Field(default_factory=list, min_length=1)


class HadithPayload(BaseModel):
    number: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)
    text_arabic: str | None = None
    book: str | None = None
    chapter: str | None = None
    narrator: str | None = None
    grade: str | None = None


class HadithDataset(BaseModel):
    """A curated hadith dataset for one collection."""

    collection: str = Field(..., min_length=1)
    title: str | None = None
    author: str | None = None
    description: str | None = None
    hadiths: list[HadithPayload] = Field(default_factory=list, min_length=1)
