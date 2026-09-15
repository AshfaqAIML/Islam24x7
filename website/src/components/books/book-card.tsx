"use client";

import Link from "next/link";
import { BookOpen } from "lucide-react";
import type { Book } from "@/types/knowledge-base";
import { demoCategoryLabels } from "@/lib/demo/books";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { DemoBadge } from "@/components/common/states";
import { StarLattice } from "@/components/decor/islamic-pattern";
import { FavoriteButton } from "@/components/library/favorite-button";

/**
 * Reusable book card — links to the book detail page. Renders labeled demo
 * records until the Knowledge Base connects; the API contract is identical.
 */
export function BookCard({
  book,
  href,
  className,
}: {
  book: Book & { coverHue?: number };
  /** Override destination (defaults to the book detail page). */
  href?: string;
  className?: string;
}) {
  const hue = book.coverHue ?? 165;
  const dest = href ?? `/library/${book.id}`;

  return (
    <Card
      className={cn(
        "group relative overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md",
        className
      )}
    >
      <CardContent className="flex gap-4 p-4">
        {/* Cover (generated placeholder — real covers come from the KB) */}
        <Link
          href={dest}
          className="focus-ring relative aspect-[3/4] w-20 shrink-0 overflow-hidden rounded-md sm:w-24"
          aria-label={`Open ${book.title}`}
          tabIndex={-1}
          aria-hidden="true"
        >
          <span
            className="absolute inset-0 transition-transform duration-300 group-hover:scale-[1.04]"
            style={{
              background: `linear-gradient(145deg, oklch(0.34 0.07 ${hue}), oklch(0.48 0.09 ${hue}))`,
            }}
          />
          <StarLattice
            tile={40}
            className="absolute inset-0 h-full w-full text-white opacity-20"
          />
          <span className="absolute inset-0 flex flex-col items-center justify-center gap-1 p-1 text-white">
            <BookOpen className="h-4 w-4 opacity-80" aria-hidden="true" />
            <span className="line-clamp-2 text-center font-serif text-[10px] leading-tight opacity-95">
              {demoCategoryLabels[book.category] ?? book.category}
            </span>
          </span>
        </Link>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="mb-1 flex items-start justify-between gap-2">
            <h3 className="line-clamp-2 font-serif text-sm font-semibold leading-snug sm:text-base">
              <Link
                href={dest}
                className="focus-ring rounded-sm transition-colors hover:text-primary"
              >
                {book.title}
              </Link>
            </h3>
            {book.isDemo ? <DemoBadge className="mt-0.5 shrink-0" /> : null}
          </div>
          <p className="mb-2 line-clamp-1 text-xs text-muted-foreground sm:text-sm">
            {book.author}
            {book.translator ? ` · tr. ${book.translator}` : ""}
          </p>
          <div className="mt-auto flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="rounded-full bg-secondary px-2 py-0.5 font-medium text-secondary-foreground">
              {demoCategoryLabels[book.category] ?? book.category}
            </span>
            <span className="uppercase">{book.language}</span>
            {book.pageCount ? <span>· {book.pageCount} pages</span> : null}
          </div>
        </div>

        <FavoriteButton bookId={book.id} bookTitle={book.title} />
      </CardContent>
    </Card>
  );
}
