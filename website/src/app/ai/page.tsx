import type { Metadata } from "next";
import { Sparkles } from "lucide-react";
import { StarLattice } from "@/components/decor/islamic-pattern";
import { AiView } from "@/components/ai/ai-view";
import { getBook } from "@/services/books";
import { aiBackendConfigured, type AiScope } from "@/services/ai";
import { brand } from "@/config/brand";

export const metadata: Metadata = {
  title: "Ask AI",
  description: `Ask the ${brand.name} library questions — every answer grounded in and cited to real sources. Foundation live; awaiting the Knowledge Base AI connection.`,
  alternates: { canonical: "/ai" },
};

/**
 * AI foundation (§21–22). The Ask flow is honestly locked until the RAG
 * backend connects; the response UI and citation deep-links are designed
 * and exercised now via clearly-labeled interface previews.
 */
export default async function AiPage({
  searchParams,
}: {
  searchParams: Promise<{ scope?: string; book?: string; chapter?: string }>;
}) {
  const { scope, book, chapter } = await searchParams;

  const bookId = typeof book === "string" ? book : undefined;
  const bookRecord = bookId ? await getBook(bookId) : null;

  return (
    <div className="flex-1">
      {/* Header band */}
      <section className="relative overflow-hidden border-b bg-gradient-to-br from-primary via-primary to-emerald-950 text-primary-foreground">
        <StarLattice
          className="absolute inset-0 text-gold opacity-[0.08]"
          tile={64}
        />
        <div className="relative mx-auto max-w-4xl px-4 py-10 sm:py-14">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-primary-foreground/70">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Research assistant
          </div>
          <h1 className="mt-3 font-serif text-3xl font-semibold sm:text-4xl">
            Ask the {brand.name} Library
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-primary-foreground/80">
            Ask in your own words — answers are retrieved from the Knowledge
            Base and every claim links back to its exact source: surah &amp;
            ayah, collection &amp; number, or book, chapter and page.
          </p>
        </div>
      </section>

      <AiView
        connected={aiBackendConfigured()}
        initialScope={(scope as AiScope) ?? undefined}
        initialBookId={bookId}
        initialBookTitle={bookRecord?.title ?? null}
        initialChapterId={typeof chapter === "string" ? chapter : undefined}
      />
    </div>
  );
}
