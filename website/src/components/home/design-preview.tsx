"use client";

import { ShieldCheck } from "lucide-react";
import { demoBooks } from "@/lib/demo/books";
import { BookCard } from "@/components/books/book-card";
import { SourceCitation } from "@/components/citations/source-citation";
import {
  DemoBadge,
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/common/states";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import type { Citation } from "@/types/knowledge-base";

/**
 * Design-system preview (Phase 1). Exercises the reusable components with
 * clearly-labeled demo data. No fabricated Islamic text appears anywhere —
 * citation examples show structure only, never invented verse/hadith text.
 */
export function DesignPreview() {
  const { toast } = useToast();

  const demoCitations: Citation[] = [
    {
      id: "demo-quran-ref",
      source: { type: "quran", surah: 1, ayah: 1, surahName: "Al-Fatihah" },
    },
    {
      id: "demo-book-ref",
      source: {
        type: "book",
        bookId: demoBooks[0].id,
        bookTitle: demoBooks[0].title,
        chapterTitle: "Sample Chapter — Purification",
        page: 125,
      },
    },
  ];

  return (
    <section className="border-t bg-secondary/30">
      <div className="mx-auto max-w-6xl px-4 py-14">
        <div className="mb-8 text-center">
          <div className="mb-3 flex items-center justify-center gap-2">
            <h2 className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl">
              Design system preview
            </h2>
            <DemoBadge />
          </div>
          <p className="mx-auto max-w-xl text-sm text-muted-foreground">
            The reusable building blocks (book cards, citations, states) are
            already in place. Sample records below are placeholders — no Quran
            verses, hadith or quotations are invented.
          </p>
        </div>

        {/* Book cards */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {demoBooks.map((book) => (
            <BookCard key={book.id} book={book} />
          ))}
        </div>

        {/* States + citations */}
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <EmptyState
              icon={ShieldCheck}
              title="No bookmarks yet"
              description="Bookmarks, highlights and notes arrive with the reader — and sync once you sign in."
            />
            <ErrorState
              title="The Knowledge Library is temporarily unavailable"
              description="This is exactly what users will see if the backend is unreachable. Retry is wired to a demo handler."
              onRetry={() =>
                toast({
                  title: "Demo state",
                  description:
                    "Nothing to retry yet — this preview demonstrates the error handling pattern.",
                })
              }
            />
          </div>
          <div className="space-y-4">
            <Card>
              <CardContent className="p-5">
                <p className="mb-3 text-sm font-semibold">
                  Source citations (clickable from Phase 4)
                </p>
                <div className="space-y-3">
                  {demoCitations.map((c) => (
                    <SourceCitation key={c.id} citation={c} />
                  ))}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5">
                <p className="mb-3 text-sm font-semibold">Loading states</p>
                <LoadingState variant="list" count={2} />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </section>
  );
}
