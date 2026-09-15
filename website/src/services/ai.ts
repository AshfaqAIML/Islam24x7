import type { Citation } from "@/types/knowledge-base";

/**
 * AI service — the ONLY place that talks to the (future) RAG backend.
 *
 * Content-integrity rule (§21): fake AI answers are never rendered. While
 * AI_API_URL is not configured the service reports `unavailable` and every
 * UI surface must show the honest "not connected" state instead of
 * simulated answers.
 */

export type AiScope =
  | "library" // Entire Library
  | "book" // Selected Book (requires bookId)
  | "chapter" // Selected Chapter (requires bookId + chapterId)
  | "quran"
  | "hadith"
  | "quran-hadith"
  | "books"; // Books only

export const aiScopes: Array<{ id: AiScope; label: string; hint?: string }> = [
  { id: "library", label: "Entire Library" },
  { id: "book", label: "Selected Book", hint: "Opened from a book page" },
  { id: "chapter", label: "Selected Chapter", hint: "Opened from a chapter" },
  { id: "quran", label: "Quran" },
  { id: "hadith", label: "Hadith" },
  { id: "quran-hadith", label: "Quran + Hadith" },
  { id: "books", label: "Books Only" },
];

export interface AskRequest {
  question: string;
  scope: AiScope;
  bookId?: string;
  chapterId?: string;
}

export type AskResponse =
  | {
      status: "connected";
      answer: string;
      citations: Citation[];
      durationMs?: number;
    }
  | { status: "unavailable"; reason: string };

/** Server-side check — is the AI/RAG backend configured? */
export function aiBackendConfigured(): boolean {
  return Boolean(process.env.AI_API_URL);
}

/** One retrieved passage as the /ask endpoint returns it. */
interface BackendAnswerSource {
  chunk_id: string;
  reference: string;
  passage: string;
  score: number;
  fts_score?: number | null;
  vector_score?: number | null;
  retrievers: string[];
}

interface BackendAskResponse {
  question: string;
  answer: string;
  grounded: boolean;
  ground_notes: string[];
  sources: BackendAnswerSource[];
  generator: string;
  model?: string | null;
  retrieval_ms: number;
  generation_ms: number;
}

/** Best-effort: turn a backend source reference into a structured citation
 *  the UI can render. Quran references look like "2:255 (Translator)" while
 *  book references carry the title/author; anything else is cited generically. */
function toCitation(source: BackendAnswerSource): Citation {
  const reference = source.reference.trim();
  const quranMatch = reference.match(/(\d+):(\d+)/);
  if (quranMatch && /quran/i.test(reference)) {
    return {
      id: source.chunk_id || reference,
      source: {
        type: "quran",
        surah: Number.parseInt(quranMatch[1], 10),
        ayah: Number.parseInt(quranMatch[2], 10),
      },
      snippet: source.passage.slice(0, 240),
    };
  }
  return {
    id: source.chunk_id || reference,
    source: {
      type: "book",
      bookId: source.chunk_id || `kb-${reference}`,
      bookTitle: reference,
    },
    snippet: source.passage.slice(0, 240),
  };
}

/**
 * Ask the Knowledge Base. Live provider POSTs to the RAG endpoint;
 * without configuration it resolves to an honest `unavailable` result.
 */
export async function askLibrary(req: AskRequest): Promise<AskResponse> {
  const endpoint = process.env.AI_API_URL;
  if (!endpoint) {
    return {
      status: "unavailable",
      reason:
        "AI Knowledge Assistant is not connected yet — AI_API_URL is not configured.",
    };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90_000);
  try {
    const res = await fetch(`${endpoint.replace(/\/$/, "")}/ask`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      // The backend scopes retrieval via language/category/source, not our
      // UI scopes; pass the question and a sensible retrieval depth.
      body: JSON.stringify({
        question: req.question,
        k: req.scope === "library" ? 6 : 4,
        language: undefined,
      }),
      signal: controller.signal,
      cache: "no-store",
    });
    if (!res.ok) {
      return {
        status: "unavailable",
        reason: `AI backend responded ${res.status}.`,
      };
    }
    const data = (await res.json()) as BackendAskResponse;
    if (!data.answer) {
      return { status: "unavailable", reason: "AI backend returned no answer." };
    }
    return {
      status: "connected",
      answer: data.answer,
      citations: (data.sources ?? []).map(toCitation),
      durationMs: (data.retrieval_ms ?? 0) + (data.generation_ms ?? 0),
    };
  } catch (error) {
    return {
      status: "unavailable",
      reason:
        error instanceof Error && error.name === "AbortError"
          ? "The AI backend did not respond in time."
          : "The AI backend could not be reached.",
    };
  } finally {
    clearTimeout(timer);
  }
}
