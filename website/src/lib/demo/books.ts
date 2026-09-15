/**
 * ⚠️ DEMO DATA — clearly-labeled development placeholders. ⚠️
 *
 * STRICT RULE: this file must NEVER contain real Quran verses, hadith text,
 * real scholar names, or real book titles/authors presented as authentic.
 * Every record is flagged `isDemo: true` and rendered with a visible
 * "Demo" badge. Production content comes exclusively from the Knowledge
 * Base backend (see docs/ARCHITECTURE.md).
 */
import type {
  Book,
  BookCategory,
  BookLanguage,
  BookChapter,
} from "@/types/knowledge-base";

export interface DemoBook extends Book {
  isDemo: true;
  coverHue: number;
}

interface DemoBookSpec {
  id: string;
  title: string;
  category: BookCategory;
  language: BookLanguage;
  pageCount: number;
  coverHue: number;
  addedAt: string;
  chapters: number;
  blurb: string;
}

const specs: DemoBookSpec[] = [
  {
    id: "demo-fiqh-1",
    title: "Sample Fiqh Handbook",
    category: "fiqh",
    language: "en",
    pageCount: 214,
    coverHue: 165,
    addedAt: "2025-11-20",
    chapters: 6,
    blurb:
      "Structure preview for a jurisprudence handbook: how chapters, pages and citations will be organised once the Knowledge Base connects.",
  },
  {
    id: "demo-tafsir-1",
    title: "Sample Tafsir Volume",
    category: "tafsir",
    language: "ar",
    pageCount: 512,
    coverHue: 42,
    addedAt: "2025-11-28",
    chapters: 8,
    blurb:
      "Layout preview for a commentary volume with long-form chapters and verse-referenced passages.",
  },
  {
    id: "demo-seerah-1",
    title: "Sample Seerah Study",
    category: "seerah",
    language: "en",
    pageCount: 340,
    coverHue: 85,
    addedAt: "2025-12-02",
    chapters: 7,
    blurb:
      "Narrative-flow preview showing how a chronological study will present chapters and reading progress.",
  },
  {
    id: "demo-aqeedah-1",
    title: "Sample Aqeedah Primer",
    category: "aqeedah",
    language: "en",
    pageCount: 128,
    coverHue: 145,
    addedAt: "2025-12-09",
    chapters: 5,
    blurb:
      "Short-book preview: compact chapters, glossary links and verse citations wired to the reader.",
  },
  {
    id: "demo-hadith-1",
    title: "Sample Hadith Studies Reader",
    category: "hadith",
    language: "en",
    pageCount: 286,
    coverHue: 12,
    addedAt: "2025-12-15",
    chapters: 6,
    blurb:
      "Academic-reader preview demonstrating grading labels, narrator notes and cross-references to the Hadith module.",
  },
  {
    id: "demo-tafsir-2",
    title: "Sample Quranic Sciences Companion",
    category: "quran-sciences",
    language: "en",
    pageCount: 364,
    coverHue: 200,
    addedAt: "2025-12-21",
    chapters: 7,
    blurb:
      "Companion-volume preview: revelation context, preservation topics and structured index pages.",
  },
  {
    id: "demo-history-1",
    title: "Sample Islamic History Chronicle",
    category: "history",
    language: "ur",
    pageCount: 430,
    coverHue: 265,
    addedAt: "2026-01-04",
    chapters: 9,
    blurb:
      "Chronicle preview with era-based parts, maps placeholders and timeline citations.",
  },
  {
    id: "demo-ethics-1",
    title: "Sample Ethics & Character Reader",
    category: "ethics",
    language: "en",
    pageCount: 190,
    coverHue: 320,
    addedAt: "2026-01-11",
    chapters: 5,
    blurb:
      "Character-focused reader preview: short reflective chapters with dua cross-links.",
  },
  {
    id: "demo-family-1",
    title: "Sample Family & Society Guide",
    category: "family",
    language: "id",
    pageCount: 232,
    coverHue: 28,
    addedAt: "2026-01-18",
    chapters: 6,
    blurb:
      "Topic-guide preview showing multi-language metadata and translator fields.",
  },
  {
    id: "demo-dua-1",
    title: "Sample Dua Collection Handbook",
    category: "dua",
    language: "ar",
    pageCount: 96,
    coverHue: 52,
    addedAt: "2026-01-25",
    chapters: 4,
    blurb:
      "Collection preview with Arabic typography, transliteration rows and source citations.",
  },
  {
    id: "demo-studies-1",
    title: "Sample Islamic Studies Workbook",
    category: "islamic-studies",
    language: "en",
    pageCount: 150,
    coverHue: 175,
    addedAt: "2026-02-01",
    chapters: 5,
    blurb:
      "Workbook preview: exercises layout, summary boxes and self-assessment pages.",
  },
  {
    id: "demo-tafsir-3",
    title: "Sample Thematic Tafsir Digest",
    category: "tafsir",
    language: "tr",
    pageCount: 278,
    coverHue: 230,
    addedAt: "2026-02-08",
    chapters: 6,
    blurb:
      "Thematic digest preview: topic clusters linking verse passages across volumes.",
  },
];

const demoBook = (spec: DemoBookSpec): DemoBook => ({
  id: spec.id,
  title: `${spec.title} (Demo)`,
  author: "Placeholder Author",
  category: spec.category,
  language: spec.language,
  pageCount: spec.pageCount,
  coverHue: spec.coverHue,
  addedAt: spec.addedAt,
  isDemo: true,
  description: `${spec.blurb} All of this is placeholder data — real books, authors and covers arrive from the Islam24x7 Knowledge Base.`,
});

export const demoBooks: DemoBook[] = specs.map(demoBook);

/** Deterministic placeholder chapters for a demo book (structure only). */
const chapterTitles = [
  "Introduction & Scope",
  "Foundations",
  "Core Principles",
  "Detailed Discussion",
  "Case Studies",
  "Practical Guidance",
  "Comparative Notes",
  "Summary & Conclusions",
];

export function demoChaptersFor(bookId: string): BookChapter[] {
  const spec = specs.find((s) => s.id === bookId);
  if (!spec) return [];
  return Array.from({ length: spec.chapters }, (_, i) => ({
    id: `${spec.id}-ch-${i + 1}`,
    bookId: spec.id,
    number: i + 1,
    title: `Chapter ${i + 1} — ${chapterTitles[i % chapterTitles.length]} (Demo)`,
    pageCount: Math.max(
      8,
      Math.round(spec.pageCount / spec.chapters) + ((i * 7) % 11) - 5
    ),
  }));
}

export const demoCategoryLabels: Record<BookCategory, string> = {
  "quran-sciences": "Quran Sciences",
  tafsir: "Tafsir",
  hadith: "Hadith",
  fiqh: "Fiqh",
  aqeedah: "Aqeedah",
  seerah: "Seerah",
  history: "History",
  ethics: "Ethics",
  family: "Family",
  "islamic-studies": "Islamic Studies",
  dua: "Dua",
  other: "Other",
};

export const demoLanguageLabels: Record<BookLanguage, string> = {
  ar: "Arabic",
  en: "English",
  ur: "Urdu",
  id: "Indonesian",
  tr: "Turkish",
  bn: "Bengali",
  other: "Other",
};
