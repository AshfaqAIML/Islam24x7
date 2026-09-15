"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Clock3,
  CornerDownLeft,
  Lock,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import type { SearchHit, SearchResponse, SearchScope } from "@/types/knowledge-base";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  EmptyState,
  ErrorState,
  DemoBadge,
} from "@/components/common/states";
import {
  SearchResultCard,
  hitKind,
} from "@/components/search/search-result-card";
import type { HitKind } from "@/components/search/search-result-card";
import { useSearchHistory } from "@/hooks/use-search-history";

interface SearchApiResponse extends SearchResponse {
  source: "live" | "demo";
  durationMs: number;
  unavailableScopes: Partial<Record<SearchScope, number>>;
  error?: string;
}

const DEBOUNCE_MS = 300;
const MIN_QUERY = 2;

/* ------------------------------ scope config ------------------------------ */

type ScopeTab = {
  value: SearchScope;
  label: string;
  /** Not searchable yet — shows a lock and the phase it opens in. */
  phase?: number;
};

const scopeTabs: ScopeTab[] = [
  { value: "all", label: "All" },
  { value: "books", label: "Books" },
  { value: "quran", label: "Quran", phase: 6 },
  { value: "hadith", label: "Hadith", phase: 7 },
  { value: "dua", label: "Duas", phase: 10 },
];

const KIND_LABELS: Record<HitKind, string> = {
  book: "Books",
  chapter: "Chapters",
  page: "Pages",
  quran: "Quran",
  hadith: "Hadith",
};

const KIND_ORDER: HitKind[] = ["book", "chapter", "page", "quran", "hadith"];

const suggestionChips = [
  "seerah",
  "tafsir",
  "structure",
  "placeholder",
  "guidance",
];

export function SearchView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { items: historyItems, add: addHistory, remove: removeHistory, clear: clearHistory } =
    useSearchHistory();

  // --- URL-param state (deep-linkable) ---
  const qFromUrl = searchParams.get("q") ?? "";
  const scopeFromUrl = (searchParams.get("scope") ?? "all") as SearchScope;

  const [inputValue, setInputValue] = useState(qFromUrl);
  const [data, setData] = useState<SearchApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<HitKind | "all">("all");
  const [inputFocused, setInputFocused] = useState(false);

  const requestId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  /** Synchronous mirror of the applied URL params — rapid interactions
   *  compose correctly even before the router updates useSearchParams. */
  const paramsRef = useRef<URLSearchParams>(
    new URLSearchParams(
      qFromUrl ? `q=${encodeURIComponent(qFromUrl)}` : ""
    )
  );

  useEffect(() => {
    paramsRef.current = new URLSearchParams(searchParams.toString());
  }, [searchParams]);

  const pushParams = useCallback(
    (mutate: (sp: URLSearchParams) => void) => {
      const sp = new URLSearchParams(paramsRef.current.toString());
      mutate(sp);
      paramsRef.current = sp;
      const qs = sp.toString();
      router.replace(qs ? `/search?${qs}` : "/search", { scroll: false });
    },
    [router]
  );

  // Debounced input → URL (URL is the source of truth for fetching).
  useEffect(() => {
    const t = setTimeout(() => {
      if (inputValue !== qFromUrl) {
        pushParams((sp) => {
          const trimmed = inputValue.trim();
          if (trimmed) sp.set("q", trimmed);
          else sp.delete("q");
        });
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [inputValue, qFromUrl, pushParams]);

  // Keep the input in sync with external navigations (back/forward, tabs)
  // using the render-time adjust pattern (React docs: You Might Not Need an
  // Effect) — no cascading effect renders.
  const [lastUrlQ, setLastUrlQ] = useState(qFromUrl);
  if (qFromUrl !== lastUrlQ) {
    setLastUrlQ(qFromUrl);
    setInputValue(qFromUrl);
  }

  // Fetch whenever URL state changes (async callback — same pattern as the
  // library browser; the effect only synchronizes URL → data).
  const runSearch = useCallback(
    async (query: string, scope: SearchScope) => {
      const id = ++requestId.current;

      if (query.length < MIN_QUERY) {
        setData(null);
        setError(null);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      const sp = new URLSearchParams({ q: query });
      if (scope !== "all") sp.set("scope", scope);

      try {
        const res = await fetch(`/api/search?${sp.toString()}`);
        const json = (await res.json()) as SearchApiResponse;
        if (id !== requestId.current) return; // stale response
        if (!res.ok) throw new Error(json.error ?? "Search request failed");
        setData(json);
        addHistory(query);
      } catch (e) {
        if (id === requestId.current) {
          setError(e instanceof Error ? e.message : "Unable to search right now");
        }
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [addHistory]
  );

  useEffect(() => {
    runSearch(qFromUrl.trim(), scopeFromUrl);
  }, [runSearch, qFromUrl, scopeFromUrl]);

  // Keyboard shortcuts: "/" or Cmd/Ctrl+K focuses the field; Escape clears.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typingElsewhere =
        target != null &&
        target !== inputRef.current &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if ((e.key === "/" && !typingElsewhere) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
      if (e.key === "Escape" && target === inputRef.current && inputValue) {
        setInputValue("");
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inputValue]);

  const setScope = (scope: SearchScope) => {
    pushParams((sp) => {
      if (scope === "all") sp.delete("scope");
      else sp.set("scope", scope);
    });
  };

  const submitNow = () => {
    pushParams((sp) => {
      const trimmed = inputValue.trim();
      if (trimmed) sp.set("q", trimmed);
      else sp.delete("q");
    });
  };

  /* ------------------------------- derived ------------------------------- */

  const hits: SearchHit[] = data?.hits ?? [];
  const { availableKinds, kindCounts, typeChips } = useMemo(() => {
    const kinds = new Set<HitKind>();
    const counts: Record<HitKind, number> = {
      book: 0,
      chapter: 0,
      page: 0,
      quran: 0,
      hadith: 0,
    };
    for (const hit of hits) {
      const k = hitKind(hit);
      kinds.add(k);
      counts[k] += 1;
    }
    const chips: Array<{ value: HitKind | "all"; label: string }> = [
      { value: "all", label: "All types" },
      ...KIND_ORDER.filter((k) => kinds.has(k)).map((k) => ({
        value: k,
        label: KIND_LABELS[k],
      })),
    ];
    return { availableKinds: kinds, kindCounts: counts, typeChips: chips };
  }, [hits]);

  // The type filter self-heals: when a new search yields no hits of the
  // selected kind, fall back to "all" — no reset effect needed.
  const effectiveTypeFilter: HitKind | "all" =
    typeFilter !== "all" && !availableKinds.has(typeFilter) ? "all" : typeFilter;

  const filteredHits = useMemo(
    () =>
      effectiveTypeFilter === "all"
        ? hits
        : hits.filter((h) => hitKind(h) === effectiveTypeFilter),
    [hits, effectiveTypeFilter]
  );

  const hasQuery = qFromUrl.trim().length >= MIN_QUERY;
  const showHistory = !hasQuery && inputFocused && historyItems.length > 0;
  const showSuggestions = !hasQuery && !loading;

  return (
    <div className="flex flex-col gap-5">
      {/* ------------------------------ search field ------------------------------ */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitNow();
          }}
          type="search"
          autoFocus
          enterKeyHint="search"
          autoComplete="off"
          spellCheck={false}
          placeholder="Search the whole library…"
          aria-label="Search the library"
          aria-describedby="search-hint"
          className="h-14 rounded-xl border-2 bg-card pl-12 pr-28 text-base shadow-sm transition-shadow focus-visible:ring-primary/30 focus-visible:ring-offset-0 md:h-16 md:pl-14 md:text-lg"
        />
        <div className="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-1.5">
          {inputValue ? (
            <button
              type="button"
              onClick={() => {
                setInputValue("");
                inputRef.current?.focus();
              }}
              aria-label="Clear search"
              className="focus-ring rounded-full p-1.5 text-muted-foreground hover:bg-muted"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : null}
          <kbd
            id="search-hint"
            className="hidden rounded-md border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground sm:block"
          >
            /
          </kbd>
        </div>
      </div>

      {/* ------------------------------ scope tabs ------------------------------ */}
      <div
        role="tablist"
        aria-label="Search scope"
        className="-mx-4 flex items-center gap-1.5 overflow-x-auto px-4 pb-1 scrollbar-none sm:mx-0 sm:flex-wrap sm:px-0"
      >
        {scopeTabs.map((tab) => {
          const active = scopeFromUrl === tab.value;
          // Quran/Hadith unlock when the live Knowledge Base is reachable;
          // Duas stay gated until their content lands (Phase 10).
          const unlocked =
            tab.value === "quran" || tab.value === "hadith"
              ? data?.source === "live"
              : false;
          if (tab.phase != null && !unlocked) {
            return (
              <span
                key={tab.value}
                aria-disabled="true"
                title={`Opens in Phase ${tab.phase} — needs the Knowledge Base`}
                className="inline-flex shrink-0 cursor-default items-center gap-1.5 rounded-full border border-dashed bg-muted/40 px-3.5 py-1.5 text-xs font-medium text-muted-foreground/60"
              >
                <Lock className="h-3 w-3" aria-hidden="true" />
                {tab.label}
                <span className="text-[10px] font-semibold uppercase tracking-wide">
                  P{tab.phase}
                </span>
              </span>
            );
          }
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setScope(tab.value)}
              className={cn(
                "focus-ring shrink-0 rounded-full border px-4 py-1.5 text-xs font-medium transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground shadow-sm"
                  : "bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ---------------------------- recent searches ---------------------------- */}
      {showHistory ? (
        <Card className="border-dashed bg-card/60 shadow-none">
          <CardContent className="p-4">
            <div className="mb-2.5 flex items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
                Recent searches
              </p>
              <button
                type="button"
                onClick={clearHistory}
                className="focus-ring rounded-md text-xs font-medium text-primary underline-offset-4 hover:underline"
              >
                Clear
              </button>
            </div>
            <ul className="flex flex-wrap gap-2">
              {historyItems.map((item) => (
                <li key={item}>
                  <span className="group inline-flex items-center overflow-hidden rounded-full border bg-background text-xs transition-colors hover:border-primary/40">
                    <button
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setInputValue(item);
                        pushParams((sp) => sp.set("q", item));
                      }}
                      className="focus-ring py-1.5 pl-3.5 pr-2"
                    >
                      {item}
                    </button>
                    <button
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => removeHistory(item)}
                      aria-label={`Remove “${item}” from recent searches`}
                      className="focus-ring py-1.5 pl-1 pr-2.5 text-muted-foreground/50 hover:text-destructive"
                    >
                      <X className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2.5 text-[11px] text-muted-foreground/70">
              Stored on this device only — never uploaded.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {/* ------------------------------ suggestions ------------------------------ */}
      {showSuggestions ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Try:</span>
          {suggestionChips.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setInputValue(s);
                pushParams((sp) => sp.set("q", s));
              }}
              className="focus-ring rounded-full border border-dashed bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      {/* ------------------------------ result area ------------------------------ */}
      {loading ? (
        <SearchSkeleton />
      ) : error ? (
        <ErrorState
          title="Search is unreachable"
          description={error}
          onRetry={submitNow}
        />
      ) : hasQuery && data ? (
        data.total === 0 ? (
          <EmptyState
            icon={Search}
            title={`No results for “${data.query}”`}
            description="Check the spelling or try a broader term. Quran and Hadith text will join search once their phases ship."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setInputValue("");
                  inputRef.current?.focus();
                }}
              >
                Clear the query
              </Button>
            }
          />
        ) : (
          <>
            {/* stats + type filter */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground" aria-live="polite">
                {data.total} {data.total === 1 ? "result" : "results"} for{" "}
                <span className="font-medium text-foreground">
                  “{data.query}”
                </span>{" "}
                · {Math.max(1, Math.round(data.durationMs))} ms
                {data.source === "demo" ? (
                  <DemoBadge className="ml-2 align-middle" />
                ) : null}
              </p>

              {availableKinds.size > 1 ? (
                <div className="flex items-center gap-1.5">
                  <SlidersHorizontal
                    className="h-3.5 w-3.5 text-muted-foreground"
                    aria-hidden="true"
                  />
                  {typeChips.map((chip) => {
                    const active = effectiveTypeFilter === chip.value;
                    const disabled =
                      chip.value !== "all" && !availableKinds.has(chip.value);
                    return (
                      <button
                        key={chip.value}
                        type="button"
                        disabled={disabled}
                        aria-pressed={active}
                        onClick={() => setTypeFilter(chip.value)}
                        className={cn(
                          "focus-ring rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                          active
                            ? "border-primary bg-primary/10 text-primary"
                            : "bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
                          disabled && "cursor-not-allowed opacity-40 hover:border-border"
                        )}
                      >
                        {chip.label}
                        {chip.value !== "all" && !disabled ? (
                          <span className="ml-1 tabular-nums opacity-60">
                            {kindCounts[chip.value as HitKind]}
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>

            <ul className="flex flex-col gap-3">
              {filteredHits.map((hit, i) => (
                <SearchResultCard key={`${hit.title}-${i}`} hit={hit} />
              ))}
            </ul>

            {filteredHits.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No {typeFilter === "all" ? "" : typeFilter} results in this
                filter — try “All types”.
              </p>
            ) : null}
          </>
        )
      ) : null}

      {/* ---------------------------- provenance note ---------------------------- */}
      <Card className="border-dashed bg-transparent shadow-none">
        <CardContent className="flex items-start gap-3 p-4 text-xs leading-relaxed text-muted-foreground">
          <Search className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            {data?.source === "live" ? (
              <>
                Results come from the <strong>live Knowledge Base</strong> —
                Quran, Hadith and Book content included. Quran/Hadith "Open
                source" deep links arrive with their reader phases.
              </>
            ) : (
              <>
                Searching <strong>labeled demo records</strong> (books, chapters
                and placeholder pages) until the Knowledge Base connects. Quran,
                Hadith and Dua scopes activate in their phases — they are never
                simulated. Press{" "}
                <kbd className="rounded border bg-muted px-1 font-mono text-[10px]">
                  Enter
                </kbd>{" "}
                to search,{" "}
                <kbd className="rounded border bg-muted px-1 font-mono text-[10px]">
                  /
                </kbd>{" "}
                to refocus.
              </>
            )}
          </p>
          <CornerDownLeft
            className="ml-auto hidden h-3.5 w-3.5 shrink-0 text-muted-foreground/50 sm:block"
            aria-hidden="true"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function SearchSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border bg-card p-4 sm:p-5"
          style={{ opacity: 1 - i * 0.15 }}
        >
          <Skeleton className="h-5 w-24 rounded-full" />
          <Skeleton className="mt-3 h-4 w-3/5" />
          <Skeleton className="mt-2 h-3 w-full" />
          <Skeleton className="mt-1.5 h-3 w-4/5" />
        </div>
      ))}
      <span className="sr-only">Searching…</span>
    </div>
  );
}
