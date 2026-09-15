"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { DemoBadge } from "@/components/common/states";

/**
 * Home quick-search — type and press Enter to jump straight into the
 * results page. A compact entry point for the Global Search module.
 */
export function SearchShortcutCard() {
  const router = useRouter();
  const [value, setValue] = useState("");

  const submit = () => {
    const q = value.trim();
    if (q.length < 2) return;
    router.push(`/search?q=${encodeURIComponent(q)}`);
  };

  return (
    <Card className="h-full border-gold/25 bg-gradient-to-br from-gold/[0.07] via-transparent to-transparent transition-colors hover:border-gold/40">
      <CardContent className="flex h-full flex-col gap-3 p-5">
        <div className="flex items-center justify-between gap-2">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gold/15">
            <Search
              className="h-5 w-5 text-gold-foreground dark:text-gold"
              aria-hidden="true"
            />
          </span>
          <DemoBadge />
        </div>
        <div>
          <h3 className="font-serif font-semibold">Search the sources</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Books, chapters and pages — one query across the whole index.
          </p>
        </div>
        <form
          className="relative mt-auto"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            type="search"
            enterKeyHint="search"
            autoComplete="off"
            aria-label="Quick search — opens the results page"
            placeholder="Try “structure” or “seerah”…"
            className="focus-ring h-10 w-full rounded-lg border bg-background pl-9 pr-9 text-sm outline-none placeholder:text-muted-foreground/60"
          />
          <button
            type="submit"
            aria-label="Search"
            className="focus-ring absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </form>
      </CardContent>
    </Card>
  );
}
