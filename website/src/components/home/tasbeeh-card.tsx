"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { dhikrStore } from "@/lib/dhikr-store";
import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

const phrases = ["SubḥānAllāh", "Al-ḥamdu lillāh", "Allāhu akbar"] as const;

/**
 * Quick-dhikr counter — a working preview of the Tasbeeh module (Phase 10).
 * Real functionality: persistent tally (localStorage), 33-target ring,
 * phrase selection. Nothing is fabricated — these are the standard phrases
 * of remembrance used as labels for the counter.
 */
export function TasbeehCard() {
  const count = useSyncExternalStore(
    dhikrStore.subscribe,
    dhikrStore.getSnapshot,
    dhikrStore.getServerSnapshot
  );
  const [phraseIndex, setPhraseIndex] = useState(0);
  const target = dhikrStore.dailyTarget();
  const pct = Math.min(1, count / target);
  const R = 52;
  const C = 2 * Math.PI * R;
  const roundComplete = count > 0 && count % target === 0;

  return (
    <Card className="flex h-full flex-col">
      <CardContent className="flex h-full flex-col gap-3 p-5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-serif font-semibold">Quick dhikr</h3>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-secondary-foreground">
            Preview · Phase 10
          </span>
        </div>

        <div
          role="group"
          aria-label="Choose a phrase of remembrance"
          className="flex flex-wrap gap-1.5"
        >
          {phrases.map((phrase, i) => (
            <button
              key={phrase}
              type="button"
              onClick={() => setPhraseIndex(i)}
              aria-pressed={phraseIndex === i}
              className={cn(
                "focus-ring rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                phraseIndex === i
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              )}
            >
              {phrase}
            </button>
          ))}
        </div>

        <div className="flex flex-1 items-center justify-center py-1">
          <button
            type="button"
            onClick={() => dhikrStore.increment()}
            aria-label={`Count dhikr — current total ${count}`}
            className="focus-ring group relative flex h-[136px] w-[136px] select-none items-center justify-center rounded-full transition-transform active:scale-[0.96]"
          >
            <svg
              viewBox="0 0 120 120"
              className="absolute inset-0 h-full w-full -rotate-90"
              aria-hidden="true"
            >
              <circle
                cx="60"
                cy="60"
                r={R}
                fill="none"
                strokeWidth="7"
                className="stroke-muted"
              />
              <circle
                cx="60"
                cy="60"
                r={R}
                fill="none"
                strokeWidth="7"
                strokeLinecap="round"
                strokeDasharray={C}
                strokeDashoffset={C * (1 - pct)}
                className="stroke-primary transition-[stroke-dashoffset] duration-500 ease-out"
              />
            </svg>
            <span className="flex flex-col items-center">
              <span className="font-serif text-4xl font-semibold tabular-nums leading-none">
                {count}
              </span>
              <span className="mt-1 text-[11px] text-muted-foreground">
                of {target}
              </span>
            </span>
            <span
              aria-hidden="true"
              className="absolute inset-1 rounded-full border border-primary/15 transition-colors group-hover:border-primary/30"
            />
          </button>
        </div>

        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {roundComplete
              ? `Round of ${target} complete — ma-shāʾ Allāh`
              : `Tallying: ${phrases[phraseIndex]}`}
          </p>
          <button
            type="button"
            onClick={() => dhikrStore.reset()}
            className="focus-ring inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Reset dhikr tally"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Reset
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
