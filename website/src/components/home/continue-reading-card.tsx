"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bookmark,
  BookOpen,
  NotebookPen,
  Play,
} from "lucide-react";
import { routes } from "@/config/site";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { SoonChip } from "@/components/common/states";
import { useAllReadingProgress } from "@/hooks/use-reading-progress";
import { useIsClient } from "@/hooks/use-client-store";

function timeAgo(ts: number): string {
  const mins = Math.round((Date.now() - ts) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/**
 * "Continue reading" — shows real local reading progress (from the reader)
 * or an honest empty state until the first session. Account sync in P8.
 */
export function ContinueReadingCard() {
  const all = useAllReadingProgress();
  const isClient = useIsClient();
  const latest = all[0] ?? null;

  if (isClient && latest) {
    return (
      <Card className="h-full">
        <CardContent className="flex h-full flex-col gap-3 p-5 sm:flex-row sm:items-center sm:gap-5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10">
            <BookOpen className="h-5 w-5 text-primary" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Continue reading · {timeAgo(latest.updatedAt)}
            </p>
            <h3 className="mt-0.5 truncate font-serif font-semibold">
              {latest.bookTitle ?? "A volume on your shelf"}
            </h3>
            {latest.chapterTitle ? (
              <p className="truncate text-xs text-muted-foreground">
                {latest.chapterTitle}
              </p>
            ) : null}
            <div className="mt-2 flex items-center gap-2">
              <Progress
                value={Math.round(latest.percent)}
                className="h-1.5 flex-1 [&>div]:bg-gradient-to-r [&>div]:from-primary [&>div]:to-gold"
                aria-label={`Reading progress ${Math.round(latest.percent)} percent`}
              />
              <span className="text-xs font-semibold tabular-nums text-muted-foreground">
                {Math.round(latest.percent)}%
              </span>
            </div>
          </div>
          <Button asChild size="sm" className="shrink-0 gap-1.5">
            <Link
              href={
                latest.chapterId
                  ? `/library/${latest.bookId}/read?chapter=${latest.chapterId}`
                  : `/library/${latest.bookId}/read`
              }
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              Resume
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full border-dashed bg-transparent shadow-none">
      <CardContent className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full border border-dashed border-muted-foreground/40">
          <BookOpen className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        </span>
        <div>
          <h3 className="font-serif font-semibold">Continue reading</h3>
          <p className="mx-auto mt-1 max-w-md text-sm leading-relaxed text-muted-foreground">
            Open any volume in the reader and this card will remember your
            exact place. Bookmarks, highlights and notes sync from Phase 8.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs text-muted-foreground">
            <Bookmark className="h-3.5 w-3.5" aria-hidden="true" />
            Bookmarks
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs text-muted-foreground">
            <NotebookPen className="h-3.5 w-3.5" aria-hidden="true" />
            Notes
          </span>
          <SoonChip phase={8} />
        </div>
        <Button asChild variant="outline" size="sm" className="mt-1">
          <Link href={routes.library}>
            Browse the library
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
