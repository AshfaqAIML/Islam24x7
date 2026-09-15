/**
 * Search service — the ONLY place that knows how search is performed.
 *
 *  - live: proxies the Knowledge Base search endpoint (KNOWLEDGE_BASE_API_URL)
 *  - demo: searches the labeled demo library (books, chapters, placeholder
 *    pages) in-memory so the search experience can be reviewed before the
 *    backend connects
 *
 * Excerpts carry <mark> highlight markers as the Knowledge Base contract
 * specifies. In demo mode every excerpt is HTML-escaped FIRST and match
 * tags are re-inserted afterwards, so the string is safe by construction.
 * Quran / Hadith / Dua scopes are NOT simulated — they return an explicit
 * "unavailable" map and the UI shows honest "Phase N" chips.
 */
import type {
  Book,
  Citation,
  SearchHit,
  SearchResponse,
  SearchScope,
} from "@/types/knowledge-base";
import { demoBooks, demoChaptersFor } from "@/lib/demo/books";
import { demoPagesFor } from "@/lib/demo/pages";
import { kbDataSource, kbFetch } from "@/services/kb";

export interface SearchParams {
  q: string;
  scope?: SearchScope;
  limit?: number;
}

export interface SearchResultPage extends SearchResponse {
  /** Where the data came from — the UI surfaces this honestly. */
  source: "live" | "demo";
  /** Server-side execution time, for the results stats line. */
  durationMs: number;
  /**
   * Scopes that cannot be searched yet (demo mode) → the phase they open
   * in. The UI renders these as locked tabs, never as fake results.
   */
  unavailableScopes: Partial<Record<SearchScope, number>>;
}

/** Which scopes the demo provider can actually search today. */
const SEARCHABLE_SCOPES: SearchScope[] = ["all", "books"];

const SCOPE_PHASE: Partial<Record<SearchScope, number>> = {
  quran: 6,
  hadith: 7,
  dua: 10,
};

/* ------------------------------ highlighting ------------------------------ */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Escape first, then wrap matched terms in <mark>. Safe by construction. */
function highlight(text: string, terms: string[]): string {
  const escaped = escapeHtml(text);
  if (terms.length === 0) return escaped;
  const pattern = terms.map(escapeRegExp).map(escapeHtml).join("|");
  try {
    return escaped.replace(new RegExp(`(${pattern})`, "gi"), "<mark>$1</mark>");
  } catch {
    return escaped;
  }
}

/** Build a windowed excerpt around the first match, with highlights. */
function excerptAround(text: string, terms: string[], radius = 90): string {
  const lower = text.toLowerCase();
  let start = -1;
  for (const term of terms) {
    const idx = lower.indexOf(term.toLowerCase());
    if (idx !== -1 && (start === -1 || idx < start)) start = idx;
  }
  if (start === -1) return highlight(text.slice(0, radius * 2), terms);

  const from = Math.max(0, start - radius);
  const to = Math.min(text.length, start + radius * 2);
  const prefix = from > 0 ? "… " : "";
  const suffix = to < text.length ? " …" : "";
  return prefix + highlight(text.slice(from, to), terms) + suffix;
}

/* --------------------------------- demo ----------------------------------- */

interface ScoredHit {
  hit: SearchHit;
  score: number;
}

function searchBooksDemo(terms: string[], limit: number): ScoredHit[] {
  const hits: ScoredHit[] = [];
  for (const book of demoBooks as Book[]) {
    const title = book.title;
    const author = book.author;
    const description = book.description ?? "";
    const haystack = `${title} ${author} ${description}`.toLowerCase();

    if (!terms.every((t) => haystack.includes(t))) continue;

    let score = 0;
    if (terms.some((t) => title.toLowerCase().includes(t))) score += 30;
    if (author.toLowerCase().includes(terms[0] ?? "")) score += 20;
    if (description.toLowerCase().includes(terms[0] ?? "")) score += 10;
    score += terms.length; // multi-term queries score slightly higher

    hits.push({
      score,
      hit: {
        citation: {
          id: `cite-${book.id}`,
          source: { type: "book", bookId: book.id, bookTitle: title },
        },
        title,
        excerpt: excerptAround(description || title, terms),
      },
    });
  }
  return hits.slice(0, limit);
}

function searchChaptersDemo(terms: string[], limit: number): ScoredHit[] {
  const hits: ScoredHit[] = [];
  for (const book of demoBooks) {
    for (const chapter of demoChaptersFor(book.id)) {
      const haystack = `${chapter.title} ${book.title}`.toLowerCase();
      if (!terms.every((t) => haystack.includes(t))) continue;

      const titleMatch = terms.some((t) => chapter.title.toLowerCase().includes(t));
      hits.push({
        score: titleMatch ? 14 : 8,
        hit: {
          citation: {
            id: `cite-${chapter.id}`,
            source: {
              type: "book",
              bookId: book.id,
              bookTitle: book.title,
              chapterId: chapter.id,
              chapterTitle: chapter.title,
            },
          },
          title: chapter.title,
          excerpt: highlight(`${chapter.pageCount ?? 12} pages · in ${book.title}`, terms),
        },
      });
      if (hits.length >= limit * 2) break;
    }
  }
  return hits.slice(0, limit);
}

function searchPagesDemo(terms: string[], limit: number): ScoredHit[] {
  const hits: ScoredHit[] = [];
  for (const book of demoBooks) {
    const chapters = demoChaptersFor(book.id);
    for (const chapter of chapters) {
      const pages = demoPagesFor(book.id, chapter.id);
      for (const page of pages) {
        const haystack = page.content.toLowerCase();
        if (!terms.every((t) => haystack.includes(t))) continue;

        hits.push({
          score: 6 + (page.pageNumber <= 2 ? 1 : 0),
          hit: {
            citation: {
              id: `cite-${chapter.id}-p${page.pageNumber}`,
              source: {
                type: "book",
                bookId: book.id,
                bookTitle: book.title,
                chapterId: chapter.id,
                chapterTitle: chapter.title,
                page: page.pageNumber,
              },
            },
            title: `${book.title} — p. ${page.pageNumber}`,
            excerpt: excerptAround(page.content, terms),
          },
        });
        if (hits.length >= limit * 3) break;
      }
    }
  }
  return hits.slice(0, limit);
}

function parseTerms(q: string): string[] {
  return Array.from(new Set(q.trim().toLowerCase().split(/\s+/).filter(Boolean)));
}

function searchDemo(params: SearchParams): SearchResultPage {
  const started = Date.now();
  const scope: SearchScope = params.scope ?? "all";
  const limit = Math.min(50, Math.max(1, params.limit ?? 24));
  const terms = parseTerms(params.q);

  const unavailableScopes = Object.fromEntries(
    Object.entries(SCOPE_PHASE).filter(([key]) => key !== "all" && key !== "books")
  ) as Partial<Record<SearchScope, number>>;

  const base: SearchResultPage = {
    query: params.q.trim(),
    scope,
    total: 0,
    hits: [],
    source: "demo",
    durationMs: 0,
    unavailableScopes,
  };

  // Not-yet-built scopes return an honest empty result — never fake hits.
  if (!SEARCHABLE_SCOPES.includes(scope)) {
    base.durationMs = Date.now() - started;
    return base;
  }
  if (terms.length === 0) {
    base.durationMs = Date.now() - started;
    return base;
  }

  let scored: ScoredHit[] = [];
  if (scope === "books") {
    scored = searchBooksDemo(terms, limit);
  } else {
    scored = [
      ...searchBooksDemo(terms, limit),
      ...searchChaptersDemo(terms, limit),
      ...searchPagesDemo(terms, limit),
    ];
  }

  scored.sort((a, b) => b.score - a.score);
  const hits = scored.slice(0, limit).map((s) => s.hit);

  base.hits = hits;
  base.total = hits.length;
  base.durationMs = Date.now() - started;
  return base;
}

/* --------------------------------- live ----------------------------------- */

/** One hit as the Knowledge Base /search endpoint returns it (asdict JSON). */
interface BackendSearchHit {
  domain: string;
  rank: number;
  title: string;
  matched_text: string;
  snippet: string;
  language: string;
  book?: string | null;
  author?: string | null;
  category?: string | null;
  chapter?: string | null;
  section?: string | null;
  page?: number | null;
  citation?: string | null;
  book_id?: string | null;
  chapter_id?: string | null;
  section_id?: string | null;
  source_file_id?: string | null;
  source_sha256?: string | null;
  chunk_id?: string | null;
}

interface BackendSearchResponse {
  query: string;
  hits: BackendSearchHit[];
}

/** Backend domains searched for each frontend scope (dua is not shipped yet). */
const SCOPE_DOMAINS: Partial<Record<SearchScope, string[]>> = {
  all: ["content", "book", "chapter", "section", "quran", "hadith"],
  books: ["content", "book", "chapter", "section"],
  quran: ["quran"],
  hadith: ["hadith"],
};

/** ts_headline emits <b>; the UI contract is <mark>. Escape, then swap tags. */
function toExcerpt(hit: BackendSearchHit): string {
  const raw = hit.snippet || hit.matched_text || "";
  return escapeHtml(raw).replace(/&lt;b&gt;/g, "<mark>").replace(/&lt;\/b&gt;/g, "</mark>");
}

function toCitation(hit: BackendSearchHit): Citation {
  if (hit.domain === "quran") {
    const base = (hit.citation ?? "0:0").split(" (")[0];
    const [s, a] = base.split(":").map((v) => Number.parseInt(v, 10));
    return {
      id: `${hit.domain}-${hit.citation ?? hit.chunk_id ?? hit.rank}`,
      source: {
        type: "quran",
        surah: Number.isFinite(s) ? s : 0,
        ayah: Number.isFinite(a) ? a : 0,
        surahName: hit.chapter ?? undefined,
      },
    };
  }
  if (hit.domain === "hadith") {
    const raw = hit.citation ?? "";
    const sep = raw.indexOf(" #");
    const collection = sep === -1 ? raw : raw.slice(0, sep);
    const hadithNumber = sep === -1 ? "" : raw.slice(sep + 2);
    return {
      id: `${hit.domain}-${hit.citation ?? hit.chunk_id ?? hit.rank}`,
      source: {
        type: "hadith",
        collection,
        hadithNumber,
        book: hit.section ?? undefined,
        chapter: hit.chapter ?? undefined,
      },
    };
  }
  return {
    id: `${hit.domain}-${hit.citation ?? hit.chunk_id ?? hit.rank}`,
    source: {
      type: "book",
      bookId: hit.book_id ?? hit.chunk_id ?? hit.source_file_id ?? `kb-${hit.rank}`,
      bookTitle: hit.title,
      chapterId: hit.chapter_id ?? undefined,
      chapterTitle: hit.chapter ?? undefined,
      page: hit.page ?? undefined,
      passageId: hit.chunk_id ?? undefined,
    },
  };
}

async function searchLive(params: SearchParams): Promise<SearchResultPage> {
  const started = Date.now();
  const scope: SearchScope = params.scope ?? "all";
  const limit = Math.min(100, Math.max(1, params.limit ?? 24));

  if (scope === "dua") {
    const startedFallback = Date.now();
    return {
      query: params.q.trim(),
      scope,
      total: 0,
      hits: [],
      source: "live",
      durationMs: Date.now() - startedFallback,
      unavailableScopes: { dua: 10 },
    };
  }

  const body = {
    query: params.q.trim(),
    domains: SCOPE_DOMAINS[scope] ?? ["content", "book", "chapter", "section", "quran", "hadith"],
    all_terms: false,
    limit,
  };
  const res = await kbFetch<BackendSearchResponse>("/search", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  const hits: SearchHit[] = res.hits.map((h) => ({
    citation: toCitation(h),
    title: h.title,
    excerpt: toExcerpt(h),
    score: h.rank,
  }));

  return {
    query: res.query,
    scope,
    total: hits.length,
    hits,
    source: "live",
    durationMs: Date.now() - started,
    unavailableScopes: {},
  };
}

/* -------------------------------- public ---------------------------------- */

export async function search(params: SearchParams): Promise<SearchResultPage> {
  if (kbDataSource() === "live") {
    try {
      return await searchLive(params);
    } catch {
      // Degrade honestly: the UI shows a "live source unreachable" note.
      return searchDemo(params);
    }
  }
  return searchDemo(params);
}
