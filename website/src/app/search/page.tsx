import type { Metadata } from "next";
import { Suspense } from "react";
import { SearchView } from "@/components/search/search-view";
import { StarLattice } from "@/components/decor/islamic-pattern";
import { routes } from "@/config/site";

export const metadata: Metadata = {
  title: "Search",
  description:
    "One search across the whole Islamic library — books, chapters and pages. Quran and Hadith scopes arrive with their phases.",
  alternates: { canonical: routes.search },
};

export default function SearchPage() {
  return (
    <main className="flex-1">
      {/* Page header */}
      <section className="relative overflow-hidden border-b">
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-b from-primary/10 via-transparent to-transparent"
        />
        <StarLattice
          tile={64}
          className="absolute inset-0 h-full w-full text-gold opacity-[0.06]"
        />
        <div className="relative mx-auto max-w-3xl px-4 py-10 text-center sm:py-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-gold-foreground/80 dark:text-gold/90">
            Global Search
          </p>
          <h1 className="mt-1 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
            Find it in the sources
          </h1>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground sm:text-base">
            One query across books, chapters and pages. Quran and Hadith join
            the index when their phases ship — never before.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-3xl px-4 py-8">
        <Suspense fallback={<SearchViewFallback />}>
          <SearchView />
        </Suspense>
      </div>
    </main>
  );
}

function SearchViewFallback() {
  return (
    <div className="flex flex-col gap-5" aria-hidden="true">
      <div className="h-14 animate-pulse rounded-xl border-2 bg-muted/50 md:h-16" />
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-8 w-20 animate-pulse rounded-full bg-muted/50" />
        ))}
      </div>
      <div className="flex flex-col gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-xl border bg-muted/30" />
        ))}
      </div>
    </div>
  );
}
