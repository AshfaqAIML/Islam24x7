import Link from "next/link";
import {
  ArrowRight,
  BookMarked,
  BookOpenText,
  Compass,
  HandHeart,
  Library,
  ScrollText,
  Search,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { moduleShowcase, routes } from "@/config/site";
import { Card, CardContent } from "@/components/ui/card";
import { SoonChip } from "@/components/common/states";

const iconMap: Record<string, LucideIcon> = {
  "book-open-text": BookOpenText,
  "scroll-text": ScrollText,
  library: Library,
  "book-marked": BookMarked,
  search: Search,
  sparkles: Sparkles,
  "hand-heart": HandHeart,
  compass: Compass,
};

/**
 * Honest module roadmap for the construction phase — each card states the
 * phase in which it ships. Replaced by real module entry points as they land.
 */
export function ModuleGrid() {
  return (
    <section id="modules" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-14">
      <div className="mb-8 text-center">
        <h2 className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl">
          What&apos;s inside
        </h2>
        <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
          Built phase by phase, on top of a dedicated Knowledge Base. Nothing
          here is simulated — modules activate as real data connects.
        </p>
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {moduleShowcase.map((mod) => {
          const Icon = iconMap[mod.icon] ?? BookOpenText;
          const live = "live" in mod && mod.live === true;
          const dest =
            "href" in mod && typeof mod.href === "string"
              ? mod.href
              : routes.library;
          return (
            <li key={mod.key}>
              <Card
                className={
                  live
                    ? "h-full border-primary/35 bg-gradient-to-b from-primary/[0.06] to-transparent transition-colors hover:border-primary/50"
                    : "h-full transition-colors hover:border-primary/40"
                }
              >
                <CardContent className="flex h-full flex-col gap-3 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                    <Icon
                      className="h-5 w-5 text-secondary-foreground"
                      aria-hidden="true"
                    />
                  </div>
                  <div>
                    <h3 className="font-serif font-semibold">{mod.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {mod.description}
                    </p>
                  </div>
                  <div className="mt-auto flex items-center gap-2 pt-2">
                    {live ? (
                      <Link
                        href={dest}
                        className="focus-ring inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-[11px] font-semibold text-primary-foreground transition-transform hover:-translate-y-px"
                      >
                        Explore now
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </Link>
                    ) : (
                      <SoonChip phase={mod.phase} />
                    )}
                    {live ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-primary" />
                        Live
                      </span>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
