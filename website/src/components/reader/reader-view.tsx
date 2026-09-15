"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ListTree,
  RotateCcw,
  Settings2,
} from "lucide-react";
import type { Book, BookChapter } from "@/types/knowledge-base";
import { cn } from "@/lib/utils";
import { readerSettingsStore } from "@/lib/reader-settings-store";
import { readingProgressStore } from "@/lib/reading-progress-store";
import {
  readerTypography,
  readerSpacing,
  readerWidth,
  readerPaper,
  type ReaderFontSize,
  type ReaderSpacing,
  type ReaderWidth,
  type ReaderPaper,
} from "@/lib/reader-settings-store";
import { useReaderTypography } from "@/hooks/use-reader-settings";
import { useReadingProgress } from "@/hooks/use-reading-progress";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { DemoBadge, ErrorState } from "@/components/common/states";
import { StarLattice } from "@/components/decor/islamic-pattern";

interface BookPagesResponse {
  pages: Array<{ id: string; pageNumber: number; content: string; chapterId?: string }>;
  chapterId: string | null;
  source: "live" | "demo";
  error?: string;
}

export interface ReaderViewProps {
  book: Book;
  chapters: BookChapter[];
}

/**
 * Phase-4 reader: chapter-scoped paginated content, TOC drawer, persisted
 * typography settings, per-book progress. Demo content is clearly labeled;
 * the data flow (services → /api/books/:id/pages) is identical for live.
 */
export function ReaderView({ book, chapters }: ReaderViewProps) {
  const router = useRouter();
  const { fontClass, spacingClass, widthClass, paperClass, settings } =
    useReaderTypography();
  const progress = useReadingProgress(book.id);

  const [chapterId, setChapterId] = useState<string | null>(chapters[0]?.id ?? null);
  const [data, setData] = useState<BookPagesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tocOpen, setTocOpen] = useState(false);
  const [percent, setPercent] = useState(0);
  const [resumeVisible, setResumeVisible] = useState(false);
  const requestId = useRef(0);
  const articleRef = useRef<HTMLElement | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Scroll-restore applied once the article has rendered. */
  const pendingScroll = useRef<number | null>(null);

  const chapter = useMemo(
    () => chapters.find((c) => c.id === chapterId) ?? null,
    [chapters, chapterId]
  );
  const chapterIndex = chapter ? chapters.indexOf(chapter) : -1;

  const loadChapter = useCallback(
    async (id: string, opts?: { scrollPercent?: number }) => {
      const reqId = ++requestId.current;
      setLoading(true);
      setError(null);
      setPercent(opts?.scrollPercent ?? 0);
      if (!opts?.scrollPercent) setResumeVisible(false);
      pendingScroll.current = opts?.scrollPercent ?? null;
      try {
        const res = await fetch(
          `/api/books/${encodeURIComponent(book.id)}/pages?chapterId=${encodeURIComponent(id)}`
        );
        const json = (await res.json()) as BookPagesResponse;
        if (reqId !== requestId.current) return;
        if (!res.ok) throw new Error(json.error ?? "Request failed");
        setData(json);
        setChapterId(id);
        window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
      } catch (e) {
        if (reqId === requestId.current) {
          setError(e instanceof Error ? e.message : "Unable to load pages");
        }
      } finally {
        if (reqId === requestId.current) setLoading(false);
      }
    },
    [book.id]
  );

  // Apply pending scroll-restore after the article has actually rendered.
  useEffect(() => {
    if (loading || pendingScroll.current == null) return;
    const target = pendingScroll.current;
    pendingScroll.current = null;
    requestAnimationFrame(() => {
      if (target <= 3) return;
      // Percent is window-scroll fraction of the rendered chapter document.
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 0) return;
      window.scrollTo({
        top: scrollable * (target / 100),
        behavior: "instant" as ScrollBehavior,
      });
    });
  }, [loading, data]);

  // Initial chapter: URL ?chapter= → saved progress → first chapter.
  useEffect(() => {
    const urlChapter = new URLSearchParams(window.location.search).get("chapter");
    const saved = readingProgressStore.get(book.id);
    const valid =
      chapters.find((c) => c.id === urlChapter)?.id ??
      (urlChapter ? null : saved?.chapterId) ??
      chapters[0]?.id ??
      null;
    if (!valid) {
      setLoading(false);
      return;
    }
    const resuming =
      !urlChapter &&
      saved != null &&
      saved.chapterId === valid &&
      saved.percent > 3 &&
      saved.percent < 97;
    if (resuming) setResumeVisible(true);
    void loadChapter(valid, resuming ? { scrollPercent: saved.percent } : undefined);
    // Run once on mount: the initial chapter is resolved from URL + saved progress.
  }, []);

  // Keep the URL deep-linkable without re-fetching.
  useEffect(() => {
    if (!chapterId) return;
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("chapter") !== chapterId) {
      sp.set("chapter", chapterId);
      router.replace(`?${sp.toString()}`, { scroll: false });
    }
  }, [chapterId, router]);

  // Scroll → progress percent (throttled saves to localStorage).
  useEffect(() => {
    if (loading || !chapterId) return;
    const onScroll = () => {
      const el = articleRef.current;
      if (!el) return;
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const p = scrollable > 0 ? Math.min(100, Math.max(0, (window.scrollY / scrollable) * 100)) : 0;
      setPercent(p);

      // Which page section is at the reading focus?
      const focusY = window.scrollY + window.innerHeight * 0.35;
      let page: number | undefined;
      el.querySelectorAll<HTMLElement>("[data-page-number]").forEach((sec) => {
        if (sec.offsetTop <= focusY) {
          page = Number(sec.dataset.pageNumber);
        }
      });

      if (saveTimer.current) return;
      saveTimer.current = setTimeout(() => {
        saveTimer.current = null;
        readingProgressStore.save({
          bookId: book.id,
          bookTitle: book.title,
          chapterId,
          chapterTitle: chapter?.title,
          page,
          pageCount: chapter?.pageCount,
          percent: Math.round(p * 10) / 10,
        });
      }, 400);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        saveTimer.current = null;
      }
    };
  }, [loading, chapterId, book.id, chapter]);

  const goToChapter = (id: string) => {
    setTocOpen(false);
    void loadChapter(id);
  };

  const prev = chapterIndex > 0 ? chapters[chapterIndex - 1] : null;
  const next = chapterIndex >= 0 && chapterIndex < chapters.length - 1 ? chapters[chapterIndex + 1] : null;

  const paragraphs = useMemo(
    () => (data?.pages ?? []).map((p) => ({ ...p, blocks: p.content.split("\n\n") })),
    [data]
  );

  return (
    <div className="flex flex-col">
      {/* Toolbar */}
      <div className="sticky top-16 z-30 border-b bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/75">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-3 sm:px-4">
          <Button asChild variant="ghost" size="icon" aria-label="Back to book details" className="shrink-0">
            <Link href={`/library/${book.id}`}>
              <ArrowLeft className="h-4.5 w-4.5" aria-hidden="true" />
            </Link>
          </Button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold leading-tight">{book.title}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {chapter ? chapter.title : "…"}
            </p>
          </div>
          {data?.source === "demo" ? <DemoBadge className="hidden shrink-0 sm:inline-flex" /> : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setTocOpen(true)}
            className="shrink-0 gap-1.5"
            aria-haspopup="dialog"
          >
            <ListTree className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">Contents</span>
          </Button>
          <SettingsPopover />
        </div>
        {/* Reading progress hairline */}
        <div className="h-0.5 w-full bg-muted" aria-hidden="true">
          <div
            className="h-full bg-gradient-to-r from-primary to-gold transition-[width] duration-200"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Resume banner */}
      {resumeVisible && progress ? (
        <div className="border-b bg-gold/10">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2.5">
            <p className="text-xs text-muted-foreground">
              You stopped at <strong className="text-foreground">{progress.chapterTitle ?? "a chapter"}</strong>{" "}
              — {progress.percent}% through.
            </p>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => setResumeVisible(false)}>
                Start over
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Content */}
      <main className="mx-auto w-full max-w-6xl px-4 py-8">
        {loading ? (
          <div className={cn("mx-auto space-y-4", widthClass)} aria-hidden="true">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
            <div className="pt-4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-10/12" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        ) : error ? (
          <ErrorState
            title="This chapter won't open"
            description={error}
            onRetry={() => chapterId && void loadChapter(chapterId)}
          />
        ) : paragraphs.length === 0 ? (
          <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
            This chapter has no pages yet — content arrives with the Knowledge
            Base.
          </div>
        ) : (
          <article
            ref={articleRef}
            className={cn(
              "relative mx-auto overflow-hidden rounded-2xl border shadow-sm",
              paperClass
            )}
          >
            <div className={cn("mx-auto px-5 py-8 sm:px-10 sm:py-12", widthClass)}>
              {/* Chapter header */}
              <header className="mb-8 border-b pb-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                    Chapter {chapter?.number ?? "—"} of {chapters.length}
                  </p>
                  <DemoBadge />
                </div>
                <h1 className="mt-2 font-serif text-2xl font-semibold tracking-tight sm:text-3xl">
                  {chapter?.title}
                </h1>
                <p className="mt-1 text-xs text-muted-foreground">
                  {book.title} · {book.author}
                </p>
              </header>

              {/* Pages */}
              {paragraphs.map((page) => (
                <section
                  key={page.id}
                  data-page-number={page.pageNumber}
                  className={cn("scroll-mt-32", page.pageNumber > 1 && "mt-8 border-t pt-8")}
                >
                  <p className="mb-4 text-center text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground/60">
                    Page {page.pageNumber}
                  </p>
                  {page.blocks.map((block, bi) => (
                    <p
                      key={bi}
                      className={cn(
                        "mb-5 [text-wrap:pretty]",
                        fontClass,
                        spacingClass,
                        bi === 0 && page.pageNumber === 1 &&
                          "first-letter:float-left first-letter:mr-2 first-letter:font-serif first-letter:text-5xl first-letter:font-semibold first-letter:leading-[0.9] first-letter:text-primary"
                      )}
                    >
                      {block}
                    </p>
                  ))}
                </section>
              ))}

              {/* Provenance note */}
              <div className="mt-10 rounded-xl border border-dashed bg-background/40 p-4 text-xs leading-relaxed text-muted-foreground">
                Placeholder reading material so the reader experience can be
                reviewed. Real pages stream from the Knowledge Base and every
                passage becomes citable (book → chapter → page).
              </div>

              {/* Chapter pager */}
              <nav
                aria-label="Chapter navigation"
                className="mt-8 flex items-center justify-between gap-3 border-t pt-6"
              >
                {prev ? (
                  <Button
                    variant="outline"
                    onClick={() => goToChapter(prev.id)}
                    className="max-w-[45%] gap-1.5"
                  >
                    <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-[10px] text-muted-foreground">Previous</span>
                      <span className="block truncate text-xs font-medium">{prev.title}</span>
                    </span>
                  </Button>
                ) : (
                  <span />
                )}
                {next ? (
                  <Button
                    variant="outline"
                    onClick={() => goToChapter(next.id)}
                    className="max-w-[45%] gap-1.5 text-right"
                  >
                    <span className="min-w-0">
                      <span className="block text-[10px] text-muted-foreground">Next</span>
                      <span className="block truncate text-xs font-medium">{next.title}</span>
                    </span>
                    <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">End of volume</span>
                )}
              </nav>
            </div>
            <StarLattice
              tile={56}
              className="pointer-events-none absolute inset-0 h-full w-full text-primary opacity-[0.025]"
              aria-hidden="true"
            />
          </article>
        )}
      </main>

      {/* TOC sheet */}
      <Sheet open={tocOpen} onOpenChange={setTocOpen}>
        <SheetContent
          side="left"
          className="flex w-full max-w-sm flex-col gap-0 p-0 sm:max-w-xs"
        >
          <SheetHeader className="border-b px-5 py-4 text-left">
            <SheetTitle className="font-serif text-base">Table of contents</SheetTitle>
            <SheetDescription className="truncate text-xs text-muted-foreground">{book.title}</SheetDescription>
          </SheetHeader>
          <nav aria-label="Chapters" className="scrollbar-elegant flex-1 overflow-y-auto p-2">
            <ol className="space-y-0.5">
              {chapters.map((ch) => {
                const active = ch.id === chapterId;
                return (
                  <li key={ch.id}>
                    <button
                      type="button"
                      onClick={() => goToChapter(ch.id)}
                      aria-current={active ? "true" : undefined}
                      className={cn(
                        "focus-ring flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                        active ? "bg-primary/10" : "hover:bg-muted"
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md font-serif text-[11px] font-semibold",
                          active
                            ? "bg-primary text-primary-foreground"
                            : "bg-secondary text-secondary-foreground"
                        )}
                      >
                        {ch.number ?? "•"}
                      </span>
                      <span className="min-w-0">
                        <span
                          className={cn(
                            "block text-sm leading-snug",
                            active ? "font-semibold text-primary" : "font-medium"
                          )}
                        >
                          {ch.title}
                        </span>
                        {ch.pageCount ? (
                          <span className="block text-[11px] text-muted-foreground">
                            {ch.pageCount} pages
                          </span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
          <Separator />
          <div className="p-3">
            <button
              type="button"
              onClick={() => {
                readingProgressStore.clear(book.id);
                setResumeVisible(false);
                setTocOpen(false);
              }}
              className="focus-ring flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Clear reading progress for this book
            </button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

/* ------------------------------ settings UI ------------------------------ */

function SegmentedRow<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div role="group" aria-label={label} className="flex gap-1 rounded-lg bg-muted p-1">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            aria-pressed={value === opt.value}
            onClick={() => onChange(opt.value)}
            className={cn(
              "focus-ring flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
              value === opt.value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function SettingsPopover() {
  const { settings } = useReaderTypography();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          aria-label="Reader display settings"
          className="shrink-0"
        >
          <Settings2 className="h-4.5 w-4.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-4">
        <p className="font-serif text-sm font-semibold">Reading comfort</p>
        <SegmentedRow<ReaderFontSize>
          label="Type size"
          value={settings.fontSize}
          onChange={(v) => readerSettingsStore.setFontSize(v)}
          options={(Object.keys(readerTypography) as ReaderFontSize[]).map((k) => ({
            value: k,
            label: readerTypography[k].label,
          }))}
        />
        <SegmentedRow<ReaderSpacing>
          label="Line spacing"
          value={settings.spacing}
          onChange={(v) => readerSettingsStore.setSpacing(v)}
          options={(Object.keys(readerSpacing) as ReaderSpacing[]).map((k) => ({
            value: k,
            label: readerSpacing[k].label,
          }))}
        />
        <SegmentedRow<ReaderWidth>
          label="Measure"
          value={settings.width}
          onChange={(v) => readerSettingsStore.setWidth(v)}
          options={(Object.keys(readerWidth) as ReaderWidth[]).map((k) => ({
            value: k,
            label: readerWidth[k].label,
          }))}
        />
        <SegmentedRow<ReaderPaper>
          label="Paper"
          value={settings.paper}
          onChange={(v) => readerSettingsStore.setPaper(v)}
          options={(Object.keys(readerPaper) as ReaderPaper[]).map((k) => ({
            value: k,
            label: readerPaper[k].label,
          }))}
        />
        <button
          type="button"
          onClick={() => readerSettingsStore.reset()}
          className="focus-ring w-full rounded-md text-center text-[11px] font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Reset to defaults
        </button>
      </PopoverContent>
    </Popover>
  );
}
