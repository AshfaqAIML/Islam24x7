import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Clock3 } from "lucide-react";
import { LibraryBrowser } from "@/components/library/library-browser";
import { BookCard } from "@/components/books/book-card";
import { DemoBadge } from "@/components/common/states";
import { Skeleton } from "@/components/ui/skeleton";
import { StarLattice } from "@/components/decor/islamic-pattern";
import { routes } from "@/config/site";
import { listBooks } from "@/services/books";

export const metadata: Metadata = {
  title: "Library",
  description:
    "Browse the Islamic library — Fiqh, Tafsir, Aqeedah, Seerah, history and more. Demo preview: real volumes arrive with the Knowledge Base.",
  alternates: { canonical: routes.library },
};

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const hasActiveFilters = Object.entries(params).some(
    ([key, value]) => key !== "page" && value !== undefined && value !== ""
  );

  // §14 — "Recently added" shelf on the unfiltered library landing view.
  const recent = hasActiveFilters ? [] : (await listBooks({ sort: "recent", page: 1, pageSize: 6 })).items;

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
        <div className="relative mx-auto max-w-6xl px-4 py-10 sm:py-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-gold-foreground/80 dark:text-gold/90">
            The Library
          </p>
          <h1 className="mt-1 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
            Browse the shelves
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground sm:text-base">
            Fiqh, Tafsir, Aqeedah, Seerah, history and more — search, filter
            and favorite. Serving labeled demo records until the Knowledge
            Base connects.
          </p>
        </div>
      </section>

      {recent.length > 0 ? (
        <section
          aria-labelledby="recently-added-heading"
          className="mx-auto max-w-6xl px-4 pt-8"
        >
          <div className="flex items-center justify-between gap-2">
            <h2
              id="recently-added-heading"
              className="flex items-center gap-2 text-sm font-semibold"
            >
              <Clock3
                className="h-4 w-4 text-gold-foreground dark:text-gold"
                aria-hidden="true"
              />
              Recently added
            </h2>
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              Newest first
              <DemoBadge />
            </span>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((book) => (
              <BookCard key={book.id} book={book} />
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Full catalogue below — or{" "}
            <Link
              href={routes.search}
              className="font-medium text-gold-foreground underline-offset-2 hover:underline dark:text-gold"
            >
              search everything
            </Link>
            .
          </p>
        </section>
      ) : null}

      <div className="mx-auto max-w-6xl px-4 py-8">
        <Suspense fallback={<BrowserSkeleton />}>
          <LibraryBrowser />
        </Suspense>
      </div>
    </main>
  );
}

function BrowserSkeleton() {
  return (
    <div className="flex flex-col gap-5" aria-hidden="true">
      <Skeleton className="h-11 w-full" />
      <div className="flex gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-24 rounded-full" />
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-36 rounded-xl" />
        ))}
      </div>
    </div>
  );
}
