"use client";

import Link from "next/link";
import { BookMarked, BookOpen, ScrollText } from "lucide-react";
import type { Citation } from "@/types/knowledge-base";
import { cn } from "@/lib/utils";
import { citationHref, citationUnavailableReason } from "@/lib/open-citation";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";

/**
 * Reusable source citation component (Quran / Hadith / Book).
 * "Open source" resolves the citation to its exact passage via
 * open-citation.ts (book → chapter → page works today; Quran/Hadith stay
 * honestly locked until their phases land).
 */
export function SourceCitation({
  citation,
  onOpen,
  className,
}: {
  citation: Citation;
  onOpen?: (citation: Citation) => void;
  className?: string;
}) {
  const { toast } = useToast();
  const { source } = citation;

  const label =
    source.type === "quran"
      ? `Quran — Surah ${source.surahName ?? source.surah}, Ayah ${source.ayah}`
      : source.type === "hadith"
        ? `${source.collection} — Hadith ${source.hadithNumber}`
        : source.bookTitle;

  const Icon =
    source.type === "quran"
      ? BookOpen
      : source.type === "hadith"
        ? ScrollText
        : BookMarked;

  const detailLines: string[] = [];
  if (source.type === "book") {
    if (source.chapterTitle) detailLines.push(`Chapter: ${source.chapterTitle}`);
    if (source.page != null) detailLines.push(`Page: ${source.page}`);
  } else if (source.type === "hadith") {
    if (source.book) detailLines.push(`Book: ${source.book}`);
    if (source.chapter) detailLines.push(`Chapter: ${source.chapter}`);
    if (source.grading) detailLines.push(`Grading: ${source.grading}`);
  }

  const href = citationHref(citation);

  const handleOpen = () => {
    toast({
      title: "Source linking not available yet",
      description: citationUnavailableReason(citation),
    });
  };

  return (
    <div
      className={cn(
        "rounded-lg border bg-card/70 p-3 text-sm transition-colors hover:border-primary/30",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary">
          <Icon className="h-3.5 w-3.5 text-secondary-foreground" aria-hidden="true" />
        </span>
        <p className="min-w-0 flex-1 truncate font-medium">{label}</p>
        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {source.type}
        </span>
      </div>
      {detailLines.length > 0 ? (
        <ul className="mt-2 space-y-0.5 pl-9 text-xs text-muted-foreground">
          {detailLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {citation.snippet ? (
        <p className="mt-2 border-l-2 border-gold/50 pl-3 text-xs italic text-muted-foreground">
          “{citation.snippet}”
        </p>
      ) : null}
      <div className="mt-3 pl-9">
        {href ? (
          <Button asChild size="sm" variant="outline">
            <Link href={href} onClick={onOpen ? () => onOpen(citation) : undefined}>
              Open source
            </Link>
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={handleOpen}>
            Open source
          </Button>
        )}
      </div>
    </div>
  );
}
