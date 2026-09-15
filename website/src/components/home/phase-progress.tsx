import Link from "next/link";
import { Hammer } from "lucide-react";
import { buildProgress } from "@/config/site";
import { Progress } from "@/components/ui/progress";

/**
 * Honest build-progress strip: shows exactly where the platform stands in
 * its 16-phase roadmap (kept in sync with docs/ARCHITECTURE.md §6).
 */
export function PhaseProgress() {
  const pct = Math.round((buildProgress.currentPhase / buildProgress.totalPhases) * 100);

  return (
    <div className="rounded-xl border bg-card/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gold/15">
            <Hammer className="h-4 w-4 text-gold-foreground dark:text-gold" aria-hidden="true" />
          </span>
          <p className="text-sm">
            <span className="font-semibold">
              Phase {buildProgress.currentPhase} of {buildProgress.totalPhases} in
              progress
            </span>{" "}
            <span className="text-muted-foreground">— {buildProgress.phaseLabel}</span>
          </p>
        </div>
        <Link
          href="#modules"
          className="focus-ring rounded-md text-xs font-medium text-primary underline-offset-4 hover:underline"
        >
          View roadmap
        </Link>
      </div>
      <Progress
        value={pct}
        className="mt-3 h-1.5 [&>div]:bg-gradient-to-r [&>div]:from-primary [&>div]:to-gold"
        aria-label={`Build progress: ${pct} percent`}
      />
    </div>
  );
}
