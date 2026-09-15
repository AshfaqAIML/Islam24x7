/**
 * Knowledge Base domain types — the contract between the frontend and the
 * (external) Islam24x7 Knowledge Base backend.
 *
 * The backend is prepared separately by a Python ingestion pipeline.
 * These types describe what the frontend EXPECTS from the API; adapt the
 * service layer (src/services) to the real contract when it lands.
 */

/* ---------------------------------- Books --------------------------------- */

export type BookCategory =
  | "quran-sciences"
  | "tafsir"
  | "hadith"
  | "fiqh"
  | "aqeedah"
  | "seerah"
  | "history"
  | "ethics"
  | "family"
  | "islamic-studies"
  | "dua"
  | "other";

export type BookLanguage = "ar" | "en" | "ur" | "id" | "tr" | "bn" | "other";

export interface Book {
  id: string;
  slug?: string;
  title: string;
  author: string;
  translator?: string;
  category: BookCategory;
  language: BookLanguage;
  description?: string;
  publisher?: string;
  edition?: string;
  pageCount?: number;
  coverUrl?: string;
  license?: string;
  copyrightNote?: string;
  addedAt?: string;
  /** True when this record is a clearly-labeled development placeholder. */
  isDemo?: boolean;
}

export interface BookChapter {
  id: string;
  bookId: string;
  number?: number;
  title: string;
  parentChapterId?: string;
  pageCount?: number;
}

export interface BookPage {
  id: string;
  bookId: string;
  chapterId?: string;
  pageNumber: number;
  /** Structured content blocks — format defined by the Knowledge Base. */
  content: string;
}

/* --------------------------------- Citations ------------------------------- */

export type CitationSource =
  | { type: "quran"; surah: number; ayah: number; surahName?: string }
  | {
      type: "hadith";
      collection: string;
      hadithNumber: string;
      book?: string;
      chapter?: string;
      grading?: string;
    }
  | {
      type: "book";
      bookId: string;
      bookTitle: string;
      chapterId?: string;
      chapterTitle?: string;
      page?: number;
      passageId?: string;
    };

export interface Citation {
  id: string;
  source: CitationSource;
  /** Short quoted snippet — must come from the source, never invented. */
  snippet?: string;
}

/* ---------------------------------- Quran --------------------------------- */

export interface Surah {
  id: number;
  name: string; // transliterated, e.g. "Al-Fatihah"
  arabicName: string; // e.g. "الفاتحة"
  englishName?: string; // e.g. "The Opening"
  ayahCount: number;
  revelationPlace?: "makkah" | "madinah";
}

export interface Ayah {
  id: string;
  surahId: number;
  numberInSurah: number;
  numberInQuran?: number;
  juz?: number;
  arabicText: string;
  translations?: Array<{ language: string; translator?: string; text: string }>;
}

/* ---------------------------------- Hadith -------------------------------- */

export interface HadithCollection {
  id: string;
  name: string;
  arabicName?: string;
  hadithCount?: number;
}

export interface Hadith {
  id: string;
  collectionId: string;
  book?: string;
  chapter?: string;
  number: string;
  arabicText?: string;
  translation?: string;
  translator?: string;
  grading?: string;
  narrator?: string;
}

/* ---------------------------------- Search -------------------------------- */

export type SearchScope = "all" | "quran" | "hadith" | "books" | "dua";

export interface SearchHit {
  citation: Citation;
  title: string;
  /** Matched passage with highlight markers (<mark>) supplied by the backend. */
  excerpt: string;
  score?: number;
}

export interface SearchResponse {
  query: string;
  scope: SearchScope;
  total: number;
  hits: SearchHit[];
}

/* ----------------------------------- Duas --------------------------------- */

export interface Dua {
  id: string;
  category: string; // morning | evening | travel | food | prayer | protection | forgiveness | family | ramadan
  title: string;
  arabicText?: string;
  transliteration?: string;
  translation?: string;
  source?: Citation;
  isDemo?: boolean;
}

export interface Zikr {
  id: string;
  routine: "morning" | "evening" | "after-salah" | "sleep" | "daily";
  title: string;
  arabicText?: string;
  translation?: string;
  targetCount: number;
  source?: Citation;
  isDemo?: boolean;
}

/* ------------------------------- Personal data ----------------------------- */

export interface Bookmark {
  id: string;
  citation: CitationSource;
  label?: string;
  createdAt: string;
}

export interface Highlight {
  id: string;
  citation: CitationSource;
  color: string;
  text: string;
  note?: string;
  createdAt: string;
}

export interface ReadingProgress {
  bookId: string;
  chapterId?: string;
  pageId?: string;
  scrollPercent: number;
  updatedAt: string;
}

/* -------------------------------- Prayer times ----------------------------- */

export interface PrayerTimes {
  date: string;
  hijriDate?: string;
  location: {
    latitude: number;
    longitude: number;
    timezone?: string;
    city?: string;
  };
  times: {
    fajr: string;
    sunrise: string;
    dhuhr: string;
    asr: string;
    maghrib: string;
    isha: string;
  };
  method?: string;
}

/* -------------------------------- Pagination ------------------------------- */

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

/* ------------------------------- APK releases ------------------------------ */

export interface ApkRelease {
  version: string;
  downloadUrl: string;
  releaseDate: string;
  sizeLabel: string;
  minAndroidVersion?: string;
  changelog?: string[];
}

export interface ApkReleaseStatus {
  release: ApkRelease;
  /** Whether the artifact is actually reachable right now. */
  available: boolean;
  reason?: string;
}
