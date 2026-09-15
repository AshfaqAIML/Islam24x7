"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BookOpen,
  ChevronDown,
  Heart,
  Library as LibraryIcon,
  Search,
  X,
} from "lucide-react";
import type { Book, BookCategory, BookLanguage } from "@/types/knowledge-base";
import {
  demoCategoryLabels,
  demoLanguageLabels,
} from "@/lib/demo/books";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { BookCard } from "@/components/books/book-card";
import { useFavorites } from "@/hooks/use-favorites";

interface BooksApiResponse {
  items: Book[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  source: "live" | "demo";
  error?: string;
}

const PAGE_SIZE = 9;

const categoryChips: Array<{ value: BookCategory | "all"; label: string }> = [
  { value: "all", label: "All" },
  ...(Object.keys(demoCategoryLabels) as BookCategory[])
    .filter((c) => c !== "other")
    .map((c) => ({ value: c, label: demoCategoryLabels[c] })),
];

const languageOptions: Array<{ value: BookLanguage | "all"; label: string }> = [
  { value: "all", label: "All languages" },
  ...(Object.keys(demoLanguageLabels) as BookLanguage[])
    .filter((l) => l !== "other")
    .map((l) => ({ value: l, label: demoLanguageLabels[l] })),
];

export function LibraryBrowser() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const favorites = useFavorites();

  // --- filter state (deep-linkable via URL params) ---
  const qFromUrl = searchParams.get("q") ?? "";
  const categoryFromUrl = (searchParams.get("category") ?? "all") as
    | BookCategory
    | "all";
  const languageFromUrl = (searchParams.get("language") ?? "all") as
    | BookLanguage
    | "all";
  const sortFromUrl = (searchParams.get("sort") ?? "recent") as
    | "recent"
    | "title"
    | "pages";
  const favOnlyFromUrl = searchParams.get("favorites") === "1";

  const [inputValue, setInputValue] = useState(qFromUrl);
  const [data, setData] = useState<BooksApiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  /** Synchronous mirror of the applied URL params — rapid filter clicks
   *  compose correctly even before the router updates useSearchParams. */
  const paramsRef = useRef<URLSearchParams>(new URLSearchParams(qFromUrl ? `q=${encodeURIComponent(qFromUrl)}` : ""));

  useEffect(() => {
    paramsRef.current = new URLSearchParams(searchParams.toString());
  }, [searchParams]);

  const pushParams = useCallback(
    (mutate: (sp: URLSearchParams) => void) => {
      const sp = new URLSearchParams(paramsRef.current.toString());
      mutate(sp);
      paramsRef.current = sp;
      const qs = sp.toString();
      router.replace(qs ? `/library?${qs}` : "/library", { scroll: false });
    },
    [router]
  );

  const setQuery = (value: string) => {
    setInputValue(value);
    pushParams((sp) => {
      if (value) sp.set("q", value);
      else sp.delete("q");
      sp.delete("page");
    });
  };

  const setFilter = (key: string, value: string | null) => {
    pushParams((sp) => {
      if (value == null || value === "all" || value === "recent") sp.delete(key);
      else sp.set(key, value);
      sp.delete("page");
    });
  };

  const clearAll = () => {
    paramsRef.current = new URLSearchParams();
    router.replace("/library", { scroll: false });
    setInputValue("");
  };

  // Debounced search: URL param is the source of truth.
  useEffect(() => {
    const t = setTimeout(() => {
      if (inputValue !== qFromUrl) {
        pushParams((sp) => {
          if (inputValue) sp.set("q", inputValue);
          else sp.delete("q");
          sp.delete("page");
        });
      }
    }, 350);
    return () => clearTimeout(t);
  }, [inputValue, qFromUrl, pushParams]);

  const fetchBooks = useCallback(
    async (page: number, append: boolean) => {
      const id = ++requestId.current;
      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);
      try {
        const sp = new URLSearchParams();
        if (qFromUrl) sp.set("q", qFromUrl);
        if (categoryFromUrl !== "all") sp.set("category", categoryFromUrl);
        if (languageFromUrl !== "all") sp.set("language", languageFromUrl);
        if (sortFromUrl !== "recent") sp.set("sort", sortFromUrl);
        sp.set("page", String(page));
        sp.set("pageSize", String(PAGE_SIZE));

        const res = await fetch(`/api/books?${sp.toString()}`);
        const json = (await res.json()) as BooksApiResponse;
        if (id !== requestId.current) return; // stale response
        if (!res.ok) throw new Error(json.error ?? "Request failed");
        setData((prev) =>
          append && prev
            ? { ...json, items: [...prev.items, ...json.items] }
            : json
        );
      } catch (e) {
        if (id === requestId.current) {
          setError(e instanceof Error ? e.message : "Unable to load books");
        }
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [qFromUrl, categoryFromUrl, languageFromUrl, sortFromUrl]
  );

  useEffect(() => {
    fetchBooks(1, false);
  }, [fetchBooks]);

  const favoritesActive = favOnlyFromUrl;
  const filteredTotal = useMemo(() => {
    if (!favoritesActive || !data) return data?.total ?? 0;
    // Client-side favorites filter over currently-known items is approximate;
    // with demo data the full set is small, so count against all loaded pages.
    return data.items.filter((b) => favorites.includes(b.id)).length;
  }, [favoritesActive, data, favorites]);

  const visibleBooks = useMemo(() => {
    if (!data) return [];
    if (!favoritesActive) return data.items;
    return data.items.filter((b) => favorites.includes(b.id));
  }, [data, favoritesActive, favorites]);

  const hasActiveFilters =
    qFromUrl !== "" ||
    categoryFromUrl !== "all" ||
    languageFromUrl !== "all" ||
    sortFromUrl !== "recent" ||
    favoritesActive;

  return (
    <div className="flex flex-col gap-5">
      {/* Toolbar */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={inputValue}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search title, author or description…"
              aria-label="Search the library"
              className="h-11 pl-9 pr-9"
            />
            {inputValue ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label="Clear search"
                className="focus-ring absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            ) : null}
          </div>

          <div className="flex gap-2">
            <Select
              value={languageFromUrl}
              onValueChange={(v) => setFilter("language", v)}
            >
              <SelectTrigger
                aria-label="Filter by language"
                className="h-11 w-[150px] shrink-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {languageOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={sortFromUrl} onValueChange={(v) => setFilter("sort", v)}>
              <SelectTrigger
                aria-label="Sort books"
                className="h-11 w-[150px] shrink-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="recent">Most recent</SelectItem>
                <SelectItem value="title">Title A–Z</SelectItem>
                <SelectItem value="pages">Longest first</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Category chips + favorites toggle */}
        <div className="-mx-4 flex items-center gap-1.5 overflow-x-auto px-4 pb-1 scrollbar-none sm:mx-0 sm:px-0">
          {categoryChips.map((chip) => {
            const active = categoryFromUrl === chip.value;
            return (
              <button
                key={chip.value}
                type="button"
                onClick={() => setFilter("category", chip.value)}
                aria-pressed={active}
                className={cn(
                  "focus-ring shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors",
                  active
                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                    : "bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"
                )}
              >
                {chip.label}
              </button>
            );
          })}
          <span aria-hidden="true" className="mx-1 h-5 w-px shrink-0 bg-border" />
          <button
            type="button"
            onClick={() =>
              setFilter("favorites", favoritesActive ? null : "1")
            }
            aria-pressed={favoritesActive}
            className={cn(
              "focus-ring inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors",
              favoritesActive
                ? "border-destructive/50 bg-destructive/10 text-destructive"
                : "bg-card text-muted-foreground hover:border-destructive/40 hover:text-destructive"
            )}
          >
            <Heart
              className={cn("h-3.5 w-3.5", favoritesActive && "fill-current")}
              aria-hidden="true"
            />
            Favorites
          </button>
        </div>
      </div>

      {/* Status + results header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {loading
            ? "Loading the shelves…"
            : `${filteredTotal} ${filteredTotal === 1 ? "book" : "books"}`}
          {!loading && data?.source === "demo" ? (
            <span className="ml-2 rounded-full border border-gold/40 bg-gold/10 px-2 py-0.5 text-[11px] font-medium text-gold-foreground dark:text-gold">
              Demo data
            </span>
          ) : null}
        </p>
        {hasActiveFilters && !loading ? (
          <button
            type="button"
            onClick={clearAll}
            className="focus-ring rounded-md text-xs font-medium text-primary underline-offset-4 hover:underline"
          >
            Clear all filters
          </button>
        ) : null}
      </div>

      {/* Results */}
      {loading ? (
        <BookGridSkeleton />
      ) : error ? (
        <ErrorState
          title="The library shelves are unreachable"
          description={error}
          onRetry={() => fetchBooks(1, false)}
        />
      ) : visibleBooks.length === 0 ? (
        favoritesActive ? (
          <EmptyState
            icon={Heart}
            title="No favorites yet"
            description="Tap the heart on any book to keep it close. Favorites live on this device and will sync to your account in a later phase."
          />
        ) : (
          <EmptyState
            icon={LibraryIcon}
            title="Nothing matches those filters"
            description="Try a different search term or clear the filters to see the full shelf."
            action={
              <Button variant="outline" size="sm" onClick={clearAll}>
                Clear filters
              </Button>
            }
          />
        )
      ) : (
        <>
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visibleBooks.map((book) => (
              <li key={book.id}>
                <BookCard book={book} className="h-full" />
              </li>
            ))}
          </ul>

          {favoritesActive ? (
            <p className="text-xs text-muted-foreground">
              Showing favorites among loaded books — clear the favorites filter
              to browse everything.
            </p>
          ) : data?.hasMore ? (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                onClick={() => fetchBooks((data?.page ?? 1) + 1, true)}
                disabled={loadingMore}
                className="min-w-44"
              >
                {loadingMore ? (
                  <>
                    <ChevronDown className="h-4 w-4 animate-bounce" aria-hidden="true" />
                    Loading…
                  </>
                ) : (
                  "Load more books"
                )}
              </Button>
            </div>
          ) : (
            !hasActiveFilters && (
              <p className="pt-1 text-center text-xs text-muted-foreground">
                End of the shelf — more volumes arrive with the Knowledge Base.
              </p>
            )
          )}
        </>
      )}

      {/* Honest provenance note */}
      <Card className="border-dashed bg-transparent shadow-none">
        <CardContent className="flex items-start gap-3 p-4 text-xs leading-relaxed text-muted-foreground">
          <BookOpen className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            This library currently serves <strong>labeled demo records</strong>{" "}
            so the browsing experience can be reviewed before the Knowledge
            Base connects. No real Islamic work is being imitated — titles,
            authors and contents are placeholders, and reading opens with the
            Reader phase.{" "}
            <Link
              href="/"
              className="focus-ring rounded-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Back to home
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function BookGridSkeleton() {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, i) => (
        <li key={i}>
          <Card>
            <CardContent className="flex gap-4 p-4">
              <Skeleton className="aspect-[3/4] w-20 shrink-0 rounded-md sm:w-24" />
              <div className="flex-1 space-y-2.5 py-1">
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-3 w-2/5" />
                <div className="pt-2" />
                <Skeleton className="h-5 w-24 rounded-full" />
                <Skeleton className="h-8 w-20 rounded-md" />
              </div>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
