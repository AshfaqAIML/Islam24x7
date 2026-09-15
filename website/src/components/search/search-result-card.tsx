"use client";

import Link from "next/link";
import { BookOpen, FileText, ListTree, ScrollText } from "lucide-react";
import type { SearchHit } from "@/types/knowledge-base";
import { cn } from "@/lib/utils";
import { citationUnavailableReason } from "@/lib/open-citation";
import { useToast } from "@/hooks/use-toast";

export type HitKind = "book" | "chapter" | "page" | "quran" | "hadith";

/**
 * Classify a hit from its citation shape:
 *  - quran / hadith citations keep their own kind
 *  - book citation without chapter → Book
 *  - book citation with chapter, without page → Chapter
 *  - book citation with page → Page
 */
export function hitKind(hit: SearchHit): HitKind {
  const source = hit.citation.source;
  if (source.type === "quran") return "quran";
  if (source.type === "hadith") return "hadith";
  if (source.type !== "book") return "book";
  if (source.page != null) return "page";
  if (source.chapterId) return "chapter";
  return "book";
}

/** Reader deep link for a hit — book detail for books, reader for chapter/page. */
export function hitHref(hit: SearchHit): string | null {
  const source = hit.citation.source;
  if (source.type !== "book") return null;
  const { bookId, chapterId, page } = source;
  if (chapterId) {
    return `/library/${bookId}/read?chapter=${encodeURIComponent(chapterId)}${
      page != null ? `&page=${page}` : ""
    }`;
  }
  return `/library/${bookId}`;
}

const kindMeta: Record<HitKind, { label: string; icon: typeof BookOpen }> = {
  book: { label: "Book", icon: BookOpen },
  chapter: { label: "Chapter", icon: ListTree },
  page: { label: "Page", icon: FileText },
  quran: { label: "Quran", icon: BookOpen },
  hadith: { label: "Hadith", icon: ScrollText },
};

/**
 * One search result: kind chip + breadcrumb + title + highlighted excerpt.
 * The excerpt carries <mark> highlights supplied by the search service
 * (HTML-escaped by construction in demo mode; trusted KB backend in live).
 * Quran and Hadith hits render their content now and surface honest
 * "open source coming with the reader phase" instead of a dead link.
 */
export function SearchResultCard({
  hit,
  className,
}: {
  hit: SearchHit;
  className?: string;
}) {
  const { toast } = useToast();
  const kind = hitKind(hit);
  const Icon = kindMeta[kind].icon;
  const source = hit.citation.source;
  const href = hitHref(hit);

  const breadcrumb =
    source.type === "book" && kind === "page" && source.chapterTitle
      ? `${source.bookTitle} · ${source.chapterTitle}`
      : source.type === "book" && kind === "chapter"
        ? source.bookTitle
        : source.type === "quran"
          ? `Surah ${source.surahName ?? source.surah} · Ayah ${source.ayah}`
          : source.type === "hadith"
            ? `${source.collection} · Hadith ${source.hadithNumber}`
            : "";

  const kindChip = (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium",
        kind === "book" && "border-primary/30 bg-primary/5 text-primary",
        kind === "chapter" && "border-gold/40 bg-gold/10 text-gold-foreground dark:text-gold",
        kind === "page" && "border-border bg-muted/60 text-muted-foreground",
        kind === "quran" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
        kind === "hadith" && "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-400"
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {kindMeta[kind].label}
    </span>
  );

  const titleNode = (
    <h3 className="mt-2 font-serif text-base font-semibold leading-snug sm:text-lg">
      {hit.title}
    </h3>
  );

  const excerptNode = (
    <p
      className="search-excerpt mt-1.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground"
      dangerouslySetInnerHTML={{ __html: hit.excerpt }}
    />
  );

  const body = (
    <>
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        {kindChip}
        {breadcrumb ? (
          <span className="min-w-0 truncate" aria-hidden="true">
            {breadcrumb}
          </span>
        ) : null}
      </div>
      {titleNode}
      {excerptNode}
    </>
  );

  return (
    <li className={cn("list-none", className)}>
      {href ? (
        <Link
          href={href}
          className={cn(
            "focus-ring group block rounded-xl border bg-card p-4 transition-all",
            "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md sm:p-5"
          )}
        >
          {body}
        </Link>
      ) : (
        <button
          type="button"
          onClick={() =>
            toast({
              title: "Source linking not available yet",
              description: citationUnavailableReason({ id: hit.citation.id, source }),
            })
          }
          className={cn(
            "focus-ring group block w-full rounded-xl border bg-card p-4 text-left transition-all",
            "hover:border-primary/40 hover:shadow-md sm:p-5"
          )}
        >
          {body}
        </button>
      )}
    </li>
  );
}