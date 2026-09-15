import type { Citation } from "@/types/knowledge-base";

/**
 * §19 — universal "open the exact source" resolution.
 *
 * A citation must navigate to the precise passage, never a module homepage:
 *   Book   → /library/<bookId>/read?chapter=<id>&page=<n>   (live since P4)
 *   Quran  → /quran/<surah>?ayah=<n>                        (Phase 6)
 *   Hadith → /hadith/<collection>/<number>                  (Phase 7)
 *
 * citationHref returns null while the target module is not shipped yet;
 * callers must then surface citationUnavailableReason instead of a dead link.
 */
export function citationHref(citation: Citation): string | null {
  const { source } = citation;

  if (source.type === "book") {
    const params = new URLSearchParams();
    if (source.chapterId) params.set("chapter", source.chapterId);
    if (source.page != null) params.set("page", String(source.page));
    const qs = params.toString();
    return `/library/${source.bookId}/read${qs ? `?${qs}` : ""}`;
  }

  if (source.type === "quran") {
    // Will become `/quran/<surah>?ayah=<n>` when Phase 6 lands.
    return null;
  }

  return null;
}

export function citationUnavailableReason(citation: Citation): string {
  const { source } = citation;
  if (source.type === "quran") {
    return "Quran reading arrives with Phase 6 — this citation will then open the exact ayah.";
  }
  return "The Hadith browser arrives with Phase 7 — this citation will then open the exact hadith.";
}
