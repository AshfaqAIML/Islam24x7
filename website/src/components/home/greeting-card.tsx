"use client";

import { Card, CardContent } from "@/components/ui/card";
import { StarLattice } from "@/components/decor/islamic-pattern";
import { useIsClient } from "@/hooks/use-client-store";

function timeGreeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 17) return "Good afternoon";
  if (hour >= 17 && hour < 22) return "Good evening";
  return "Peaceful night";
}

function hijriDate(date: Date): string {
  try {
    return new Intl.DateTimeFormat("en-u-ca-islamic-umalqura", {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(date);
  } catch {
    return "";
  }
}

function gregorianDate(date: Date): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(date);
  } catch {
    return "";
  }
}

/**
 * Personal greeting strip — the universal salutation plus a real,
 * computed Hijri date (Umm al-Qura calendar via Intl; nothing is
 * hard-coded or fabricated). Hydration-safe via useIsClient.
 */
export function GreetingCard() {
  const isClient = useIsClient();

  const now = new Date();
  const hijri = isClient ? hijriDate(now) : "";
  const gregorian = isClient ? gregorianDate(now) : "";
  const greeting = isClient ? timeGreeting(now.getHours()) : "Welcome";

  return (
    <Card className="relative overflow-hidden border-primary/20">
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-br from-primary/12 via-transparent to-gold/10"
      />
      <StarLattice
        tile={56}
        className="absolute inset-0 h-full w-full text-primary opacity-[0.06]"
      />
      <CardContent className="relative flex flex-col gap-4 p-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-gold-foreground/80 dark:text-gold/90">
            As-salāmu ʿalaykum
          </p>
          <h2 className="mt-1 font-serif text-2xl font-semibold tracking-tight sm:text-3xl">
            {greeting}
          </h2>
        </div>
        <div className="text-left sm:text-right">
          {hijri ? (
            <p className="font-serif text-base font-medium text-primary">
              {hijri}
            </p>
          ) : null}
          <p className="mt-0.5 text-sm text-muted-foreground" suppressHydrationWarning>
            {gregorian || " "}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
